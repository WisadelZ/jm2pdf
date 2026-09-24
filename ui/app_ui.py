# -*- coding: utf-8 -*-
"""UI 协调层：窗口设置、路由、全局状态、配置持久化、日志与业务调度。

界面视图（MainPage / SettingsPage）只负责呈现与收集输入，
所有业务动作集中在这里，便于测试与后续扩展。
"""

import copy
import logging
import threading

import flet as ft
import jmcomic
import yaml

from core import account as account_store
from core import config as conf_mod
from core import favorite
from core.config import THEME_MODES
from core.constants import (APP_VERSION, COLOR_ERR, COLOR_IDLE, COLOR_OK,
                            ROUTE_ACCOUNT, ROUTE_ALBUM, ROUTE_DOWNLOAD, ROUTE_EXPLORER,
                            ROUTE_FAVORITE, ROUTE_HELP, ROUTE_MAIN, ROUTE_SETTINGS,
                            ROUTE_TASKS, UI_FONT_FAMILY, WINDOW_HEIGHT, WINDOW_MIN_HEIGHT,
                            WINDOW_MIN_WIDTH, WINDOW_WIDTH)
from core.downloader import (album_url, build_option, fetch_cover, fetch_covers,
                             fetch_image_bytes)
from core.logging_bridge import UiLogHandler
from core.task_queue import TaskQueue
from ui.account_page import AccountPage
from ui.album_page import AlbumPage
from ui.explore_page import ExplorePage
from ui.explorer_page import ExplorerPage
from ui.favorite_page import FavoritePage
from ui.help_page import HelpPage
from ui.main_page import MainPage
from ui.settings_page import SettingsPage
from ui.task_page import TaskPage
from utils.helpers import parse_ids
from utils.i18n import LANGUAGE_NAMES, LANGUAGES, I18n

MAX_LOG_LINES = 500

# 账号页要展示的账号状态字段：登录响应里就有，登录时一并加密保存
PROFILE_KEYS = ("level", "level_name", "exp", "next_level_exp", "exp_percent",
                "favorites", "favorites_max", "coin")


class AppUI:
    SAVE_DELAY = 0.5

    def __init__(self, page: ft.Page):
        self.page = page
        self.conf = conf_mod.load_conf()
        self.i18n = I18n(self.conf["app"].get("language"))

        # 运行状态（跨视图重建保留）
        self.searching = False
        self.searched_id = ""
        self.searched_url = ""
        self.searched_cover = None      # 封面图字节，只留在内存里，不落盘
        self.search_text = ""
        self.detail_album_id = ""       # 探索页当前查看的本子 ID
        self.explore_page = None        # 缓存探索页，从详情返回时保留搜索结果
        self.favorite_page = None       # 缓存收藏页，从详情返回时保留页码与列表
        self.explorer_page = None       # 缓存资源管理器页，返回时保留搜索词与排序方式
        self.status_text_value = self.t("status_ready")
        self.status_color = COLOR_IDLE
        # 未落盘的界面输入，用于语言切换重建后还原
        self.pending_ids_text = ""
        self.pending_search_text = ""

        # 账号：登录信息从加密文件读取，凭据只留在内存里供下载层登录使用
        self.account = account_store.load_account()
        self.account_avatar = None      # 头像字节，只在内存里，不落盘
        self.logging_in = False
        self.avatar_loading = False
        self.album_page = None          # 当前展示的本子详情页（收藏后同步星号）
        self.account_page = None        # 当前展示的账号页（异步结果就地刷新）
        # 账号页的收藏预览：None 表示还没取过，[] 表示取到空
        self.account_favorites = None
        self.account_favorites_loading = False
        self.account_favorites_error = None
        # 账号状态字段（等级 / 经验 / 收藏数）的补拉状态
        self.profile_loading = False
        self.profile_checked = False
        if self.account:
            account_store.set_credentials(self.account.get("username"),
                                          self.account.get("password"))

        # 日志缓冲（跨视图重建保留）
        self.log_lines = []
        self.log_view = None
        self.status_text = None
        self.main_page = None
        self._save_timer = None

        # 下载队列：任务状态 / 进度 / 落盘都在 core.task_queue 里，界面只读它的快照
        self.task_page = None           # 缓存任务中心页，从别处返回时筛选与排序仍保留
        self._queue_busy = False        # 队列上一次的忙 / 闲状态（用于收尾提示）
        self._refresh_pending = False   # 是否已排队一次界面刷新（避免刷新任务堆积）
        self.queue = TaskQueue(conf_provider=self._queue_conf, log=self.append_log,
                               t=self.t, on_change=self._on_queue_change)

        # 目录/文件选择器：Flet 1.0 中 FilePicker 为 service，需注册到 page.services
        self.picker = ft.FilePicker()
        page.services.append(self.picker)

        self._setup_window()
        self._setup_logging()
        self._restore_queue()
        page.on_route_change = self._on_route_change
        self.build()

    # ------------------------------------------------------------------
    # 基础工具
    # ------------------------------------------------------------------
    def t(self, key, **kwargs):
        return self.i18n.t(key, **kwargs)

    def update(self):
        try:
            self.page.update()
        except Exception:
            pass

    @property
    def running(self):
        """队列里是否有排队中 / 下载中的任务。

        各页面用它来置灰按钮、决定能否重建视图；语义与旧版的「正在下载」一致，
        只是从「一个批次」变成了「队列里还有活动任务」。
        """
        return self.queue.has_active()

    def navigate(self, route):
        self.page.navigate(route)

    def _on_route_change(self, e=None):
        self.build()

    def theme_mode_value(self):
        mode = str(self.conf["app"].get("theme_mode") or "dark").lower()
        return {
            "light": ft.ThemeMode.LIGHT,
            "dark": ft.ThemeMode.DARK,
            "system": ft.ThemeMode.SYSTEM,
        }.get(mode, ft.ThemeMode.LIGHT)

    def _setup_window(self):
        page = self.page
        page.title = self.t("window_title", version=APP_VERSION)
        page.window.width = WINDOW_WIDTH
        page.window.height = WINDOW_HEIGHT
        page.window.min_width = WINDOW_MIN_WIDTH
        page.window.min_height = WINDOW_MIN_HEIGHT
        page.window.resizable = True
        # 明暗主题统一指定字体，避免默认字体下中英文混排字重忽粗忽细
        page.theme = ft.Theme(font_family=UI_FONT_FAMILY)
        page.dark_theme = ft.Theme(font_family=UI_FONT_FAMILY)
        page.theme_mode = self.theme_mode_value()
        # 队列有活动任务时拦下关窗，先落盘并询问是否退出（空闲时照常关闭）
        page.window.prevent_close = False
        page.window.on_event = self._on_window_event

    def _setup_logging(self):
        handler = UiLogHandler(self.append_log)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logger = logging.getLogger("jmcomic")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

    # ------------------------------------------------------------------
    # 视图构建与状态绑定
    # ------------------------------------------------------------------
    def build(self):
        """按当前路由重建视图树。语言切换、导入配置后都会调用。

        首页为探索页（ROUTE_MAIN），下载页是二级页（ROUTE_DOWNLOAD）。
        """
        route = self.page.route or ROUTE_MAIN
        self.log_view = None
        self.main_page = None
        self.album_page = None
        self.account_page = None
        self.page.views.clear()
        if route == ROUTE_SETTINGS:
            view = SettingsPage(self).build_view()
        elif route == ROUTE_EXPLORER:
            # 缓存本页：从浏览层返回时搜索词与排序方式仍然保留
            if self.explorer_page is None:
                self.explorer_page = ExplorerPage(self)
            view = self.explorer_page.build_view()
        elif route == ROUTE_ACCOUNT:
            # 留存本页引用：头像 / 状态 / 收藏取回后在本页内就地刷新，不重建整页
            self.account_page = AccountPage(self)
            view = self.account_page.build_view()
        elif route == ROUTE_FAVORITE:
            # 缓存本页：从本子详情返回时页码与列表仍然保留
            if self.favorite_page is None:
                self.favorite_page = FavoritePage(self)
            view = self.favorite_page.build_view()
        elif route == ROUTE_DOWNLOAD:
            # 下载页不再是首页，但 main_page 仍指向它，供配置同步与入队使用
            self.main_page = MainPage(self)
            view = self.main_page.build_view()
        elif route == ROUTE_TASKS:
            # 缓存本页：返回时筛选、排序与搜索词都保留
            if self.task_page is None:
                self.task_page = TaskPage(self)
            view = self.task_page.build_view()
        elif route == ROUTE_ALBUM:
            # 留存本页引用：收藏成功后用于把星号变实心
            self.album_page = AlbumPage(self)
            view = self.album_page.build_view()
        elif route == ROUTE_HELP:
            view = HelpPage(self).build_view()
        else:
            if self.explore_page is None:
                self.explore_page = ExplorePage(self)
            view = self.explore_page.build_view()
        self.page.views.append(view)
        self.update()

    def rebuild(self, status=None, color=None):
        """刷新窗口标题并按需重置状态文本后重建视图。"""
        self.page.title = self.t("window_title", version=APP_VERSION)
        if status is None:
            self.status_text_value = self.t("status_ready")
            self.status_color = COLOR_IDLE
        else:
            self.status_text_value = status
            self.status_color = color or COLOR_OK
        self.build()

    def bind_status(self, control):
        """视图挂载时把状态文本控件接管过来，保证跨视图状态一致。"""
        self.status_text = control
        control.value = self.status_text_value
        control.color = self.status_color

    def bind_log_view(self, control):
        """把已有的日志缓冲回填到新视图的日志区。"""
        self.log_view = control
        control.controls = [self._log_control(line) for line in self.log_lines]

    def set_status(self, text, color=None):
        self.status_text_value = text
        self.status_color = color or COLOR_IDLE
        if self.status_text is not None:
            self.status_text.value = text
            self.status_text.color = self.status_color
        self.update()

    @staticmethod
    def _log_control(message):
        return ft.Text(message, size=11, color="#dcdcdc", selectable=True)

    def append_log(self, message):
        try:
            self.log_lines.append(message)
            if len(self.log_lines) > MAX_LOG_LINES:
                del self.log_lines[0:len(self.log_lines) - MAX_LOG_LINES]
            if self.log_view is not None:
                self.log_view.controls.append(self._log_control(message))
                if len(self.log_view.controls) > MAX_LOG_LINES:
                    del self.log_view.controls[0:len(self.log_view.controls) - MAX_LOG_LINES]
            self.update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 配置持久化
    # ------------------------------------------------------------------
    def sync_conf(self):
        """把下载页上的输入同步进配置（设置页自身不缓存输入）。"""
        if self.main_page is not None:
            self.main_page.sync_conf_from_ui()

    def on_conf_change(self):
        """界面输入变更：立即同步到内存配置，延迟写盘。"""
        self.sync_conf()
        self.schedule_save()

    def schedule_save(self):
        if self._save_timer is not None:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(self.SAVE_DELAY, self.flush_conf)
        self._save_timer.daemon = True
        self._save_timer.start()

    def flush_conf(self):
        if self._save_timer is not None:
            self._save_timer.cancel()
            self._save_timer = None
        try:
            conf_mod.save_conf(self.conf)
        except OSError as exc:
            self.set_status(self.t("status_conf_save_failed", error=exc), COLOR_ERR)

    async def export_conf(self):
        """把当前配置导出到用户选择的文件。"""
        self.sync_conf()
        try:
            target = await self.picker.save_file(
                dialog_title=self.t("export_dialog_title"),
                file_name=self.t("export_file_name"),
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["yml", "yaml"],
            )
        except Exception as exc:
            self.set_status(self.t("status_export_failed", error=exc), COLOR_ERR)
            return
        if not target:
            self.set_status(self.t("status_export_canceled"), COLOR_IDLE)
            return
        try:
            conf_mod.export_conf(self.conf, target)
        except (OSError, yaml.YAMLError) as exc:
            self.set_status(self.t("status_export_failed", error=exc), COLOR_ERR)
            return
        self.set_status(self.t("status_exported", path=target), COLOR_OK)

    async def import_conf(self):
        """从用户选择的文件导入配置并立即刷新界面。"""
        if self.running:
            self.set_status(self.t("status_busy_restart"), COLOR_ERR)
            return
        try:
            files = await self.picker.pick_files(
                dialog_title=self.t("import_dialog_title"),
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["yml", "yaml"],
                allow_multiple=False,
            )
        except Exception as exc:
            self.set_status(self.t("status_import_failed", error=exc), COLOR_ERR)
            return
        source = files[0].path if files else None
        if not source:
            self.set_status(self.t("status_import_canceled"), COLOR_IDLE)
            return
        try:
            imported = conf_mod.read_conf_file(source)
            conf_mod.save_conf(imported)
        except (OSError, yaml.YAMLError, ValueError) as exc:
            self.set_status(self.t("status_import_failed", error=exc), COLOR_ERR)
            return
        self.conf = imported
        self.i18n.set_language(self.conf["app"].get("language"))
        self.page.theme_mode = self.theme_mode_value()
        self.rebuild(status=self.t("status_imported"), color=COLOR_OK)

    # ------------------------------------------------------------------
    # 外观与语言
    # ------------------------------------------------------------------
    def apply_theme(self, mode):
        if mode not in THEME_MODES:
            return
        self.conf["app"]["theme_mode"] = mode
        self.page.theme_mode = self.theme_mode_value()
        self.flush_conf()
        self.set_status(self.t("status_theme_changed", theme=self.t("theme_" + mode)), COLOR_OK)

    def apply_language(self, language):
        if language not in LANGUAGES:
            return
        changed = language != self.i18n.language
        self.conf["app"]["language"] = language
        self.i18n.set_language(language)
        self.flush_conf()
        if not changed:
            return
        if self.running:
            # 下载线程持有旧视图引用，先保存设置，重启后生效
            self.set_status(self.t("status_busy_restart"), COLOR_ERR)
            return
        self.rebuild(
            status=self.t("status_lang_changed", language=LANGUAGE_NAMES[language]),
            color=COLOR_OK)

    # ------------------------------------------------------------------
    # 账号
    # ------------------------------------------------------------------
    def login(self, username, password):
        """发起登录：网络请求放到后台线程，完成后按结果重建视图。"""
        if self.logging_in:
            return
        self.logging_in = True
        self.set_status(self.t("status_logging_in"))
        self.page.run_thread(self._login_worker, username, password)

    def _login_worker(self, username, password):
        try:
            client = build_option(self.conf, with_login=False).new_jm_client()
            resp = client.login(username, password)
            record = self._account_record(username, password,
                                          getattr(resp, "res_data", None))
            avatar = fetch_image_bytes(record["avatar_url"])
            account_store.save_account(record)
            self.account = record
            self.account_avatar = avatar
            self.favorite_page = None       # 换账号后旧的收藏数据不再有效
            self.account_favorites = None
            self.profile_checked = True     # 登录时已经拿到状态字段，不必再补拉
            status = self.t("status_login_ok", name=record["nickname"])
            color = COLOR_OK
        except Exception as exc:
            status = self.t("status_login_failed", error=exc)
            color = COLOR_ERR
        self.logging_in = False
        self.rebuild(status=status, color=color)

    def _account_record(self, username, password, profile, previous=None):
        """把登录响应的账号信息整理成待加密保存的记录。"""
        if not isinstance(profile, dict):
            profile = {}
        prev = previous or {}
        uid = str(profile.get("uid") or prev.get("uid") or "")
        record = dict(prev)
        record.update({
            "username": username,
            "password": password,
            "uid": uid,
            "nickname": (profile.get("fname") or profile.get("nickname")
                         or profile.get("username") or username),
            "avatar_url": self._avatar_url(profile.get("photo"), uid),
            "level": profile.get("level"),
            "level_name": profile.get("level_name"),
            "exp": profile.get("exp"),
            "next_level_exp": profile.get("nextLevelExp"),
            "exp_percent": profile.get("expPercent"),
            "favorites": profile.get("album_favorites"),
            "favorites_max": profile.get("album_favorites_max"),
            "coin": profile.get("coin"),
        })
        return record

    def ensure_account_profile(self):
        """账号页要展示的状态字段只有登录时才拿得到。

        旧版本存下来的记录里没有这些字段，这里补拉一次并写回加密文件；
        每个会话最多补一次，失败就继续展示已有内容，不打扰用户。
        """
        if (self.profile_checked or self.profile_loading or not self.account
                or all(self.account.get(key) is not None for key in PROFILE_KEYS)):
            return
        self.profile_checked = True
        self.profile_loading = True
        self.page.run_thread(self._profile_worker)

    def _profile_worker(self):
        try:
            username, password = account_store.get_credentials()
            client = build_option(self.conf, with_login=False).new_jm_client()
            resp = client.login(username, password)
            record = self._account_record(username, password,
                                          getattr(resp, "res_data", None),
                                          previous=self.account)
            account_store.save_account(record)
            self.account = record
        except Exception:
            pass                            # 补拉只是锦上添花，失败保持原样
        self.profile_loading = False
        if self.account_page is not None:
            self.account_page.refresh_account_info()

    def refresh_account_profile(self):
        """账号状态可能已变化（例如刚签完到）：强制补拉一次，让 J 币 / 经验跟上。"""
        if self.profile_loading or not self.account:
            return
        self.profile_loading = True
        self.page.run_thread(self._profile_worker)

    def logout(self):
        """退出登录：删除本地账号文件并清空内存中的账号信息，回到登录界面。"""
        try:
            account_store.delete_account()
        except OSError as exc:
            self.set_status(self.t("status_logout_failed", error=exc), COLOR_ERR)
            return
        self.account = None
        self.account_avatar = None
        self.favorite_page = None
        self.account_favorites = None
        self.profile_checked = False
        self.rebuild(status=self.t("status_logged_out"), color=COLOR_IDLE)

    def add_to_favorite(self, album_id, folder_id):
        """把本子加入指定收藏夹：网络请求放到后台线程。"""
        self.set_status(self.t("status_favorite_adding"))
        self.page.run_thread(self._favorite_worker, album_id, folder_id)

    def remove_favorite(self, album_id):
        """取消收藏：网络请求放到后台线程。"""
        self.set_status(self.t("status_favorite_removing"))
        self.page.run_thread(self._remove_favorite_worker, album_id)

    def _favorite_worker(self, album_id, folder_id):
        try:
            favorite.add_to_folder(self.conf, album_id, folder_id)
        except Exception as exc:
            self.set_status(self.t("status_favorite_add_failed", error=exc), COLOR_ERR)
            return
        self._after_favorite_changed(True)
        self.set_status(self.t("status_favorite_added"), COLOR_OK)

    def _remove_favorite_worker(self, album_id):
        try:
            favorite.remove_from_favorites(self.conf, album_id)
        except Exception as exc:
            self.set_status(self.t("status_favorite_remove_failed", error=exc), COLOR_ERR)
            return
        self._after_favorite_changed(False)
        self.set_status(self.t("status_favorite_removed"), COLOR_OK)

    def _after_favorite_changed(self, favorited):
        """收藏变化后：刷新详情页星号，并让缓存的收藏数据失效。"""
        if self.album_page is not None:
            self.album_page.set_favorited(favorited)
        self.favorite_page = None
        self.account_favorites = None

    def ensure_account_favorites(self):
        """账号页预览：进入页面时读取前若干本收藏（含封面字节，只在内存里）。"""
        if (self.account_favorites is not None or self.account_favorites_loading
                or not self.account):
            return
        self.account_favorites_loading = True
        self.page.run_thread(self._account_favorites_worker)

    def _account_favorites_worker(self):
        try:
            items = favorite.preview_items(self.conf)
            fetch_covers(items)
            error = None
        except Exception as exc:
            items, error = [], exc
        self.account_favorites = items
        self.account_favorites_error = error
        self.account_favorites_loading = False
        if self.account_page is not None:
            self.account_page.refresh_favorites()

    @staticmethod
    def _avatar_url(photo, uid=""):
        """把头像字段规范成完整地址；已经是完整地址时原样返回。

        接口返回的头像只是文件名，而头像挂在移动端域名的 /media/users/ 下
        （网页域名 18comic.vip 上取不到），域名复用 jmcomic 运行时维护的那一组。
        """
        photo = (photo or "").strip()
        if photo.startswith(("http://", "https://")):
            return photo
        if not photo and uid:
            photo = "%s.jpg" % uid
        domain_list = jmcomic.JmModuleConfig.DOMAIN_API_LIST or []
        if not photo or not domain_list:
            return ""
        domain = str(domain_list[0]).rstrip("/")
        if not domain.startswith(("http://", "https://")):
            domain = "https://" + domain
        return "%s/media/users/%s" % (domain, photo)

    def ensure_avatar(self):
        """账号页展示头像前取一次头像字节（内存缓存，不落盘）。"""
        if self.account_avatar is not None or self.avatar_loading or not self.account:
            return
        url = self._avatar_url(self.account.get("avatar_url"), self.account.get("uid"))
        if not url:
            return
        self.avatar_loading = True
        self.page.run_thread(self._avatar_worker, url)

    def _avatar_worker(self, url):
        self.account_avatar = fetch_image_bytes(url)
        self.avatar_loading = False
        if self.account_page is not None:
            self.account_page.set_avatar(self.account_avatar)

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def search(self):
        if self.searching:
            return
        self.sync_conf()
        aid = (self.main_page.search_field.value or "").strip()
        if not aid:
            self.set_status(self.t("status_search_need_id"), COLOR_ERR)
            return
        self.searching = True
        self.searched_id = ""
        self.searched_url = ""
        self.searched_cover = None
        self.search_text = ""
        self.main_page.refresh()
        self.set_status(self.t("status_searching"))
        self.page.run_thread(self._search_worker, aid)

    @staticmethod
    def _extract_tags(detail):
        try:
            tag_list = getattr(detail, "tags", None) or []
            if isinstance(tag_list, dict):
                flat = []
                for value in tag_list.values():
                    flat.extend(value if isinstance(value, list) else [value])
                tag_list = flat
            tags = ", ".join(str(item) for item in list(tag_list)[:10])
            if len(tag_list) > 10:
                tags += " ..."
            return tags
        except Exception:
            return ""

    def _search_worker(self, aid):
        cover = None
        try:
            option = build_option(self.conf)
            client = option.new_jm_client()
            detail = client.get_album_detail(aid)
            tags = self._extract_tags(detail)
            template = "search_info_tags" if tags else "search_info"
            text = self.t(template, id=detail.id, pages=detail.page_count,
                          chapters=len(detail), title=detail.title, tags=tags)
            ok, searched, url = True, str(detail.id), album_url(detail.id)
            # 封面只用于界面展示，失败不影响搜索结果的呈现
            cover = fetch_cover(detail.id)
        except Exception as exc:
            text, ok, searched, url = self.t("search_failed", error=exc), False, "", ""
        self.searching = False
        self.searched_id = searched
        self.searched_url = url
        self.searched_cover = cover
        self.search_text = text
        if self.main_page is not None:
            self.main_page.refresh()
        self.set_status(self.t("status_search_done") if ok else self.t("status_search_failed"),
                        COLOR_OK if ok else COLOR_ERR)
        self.append_log(self.t("search_result_log", text=text.replace("\n", " | ")))

    def add_searched(self):
        if not self.searched_id:
            self.set_status(self.t("status_add_no_result"), COLOR_ERR)
            return
        ids = parse_ids(self.main_page.ids_field.value)
        if self.searched_id in ids:
            self.set_status(self.t("status_add_exists", id=self.searched_id))
            return
        ids.append(self.searched_id)
        self.main_page.ids_field.value = ", ".join(ids)
        self.pending_ids_text = self.main_page.ids_field.value
        self.set_status(self.t("status_add_ok", id=self.searched_id), COLOR_OK)

    # ------------------------------------------------------------------
    # 探索与本子详情
    # ------------------------------------------------------------------
    def open_album(self, album_id):
        """打开本子详情页（探索页点击名称时调用）。"""
        self.detail_album_id = str(album_id)
        self.navigate(ROUTE_ALBUM)

    def append_ids(self, ids):
        """把 ID 加入主页的下载列表（返回真正新增的 ID 列表）。"""
        current = parse_ids(self.pending_ids_text)
        added = [str(album_id) for album_id in ids if str(album_id) not in current]
        if not added:
            self.set_status(self.t("status_add_exists", id=", ".join(str(i) for i in ids)))
            return []
        current.extend(added)
        self.pending_ids_text = ", ".join(current)
        if self.main_page is not None:
            self.main_page.ids_field.value = self.pending_ids_text
        self.set_status(self.t("status_added_queue", ids=", ".join(added)), COLOR_OK)
        return added

    # ------------------------------------------------------------------
    # 下载队列
    # ------------------------------------------------------------------
    def _queue_conf(self):
        """给队列取一份当前配置（深拷贝：下载中改配置不影响已在跑的任务）。"""
        return copy.deepcopy(self.conf)

    def start(self):
        """下载页「加入下载列表」：把输入框里的 ID 全部入队，随后清空输入框。"""
        if self.main_page is None:
            return
        if self.enqueue_ids(parse_ids(self.main_page.ids_field.value)):
            # 输入框只是「待入队列表」，入队后清空，避免同一批重复加入
            self.main_page.clear_ids()
            self.main_page.refresh()

    def download_ids(self, ids):
        """直接下载指定 ID（探索页与本子详情页的「直接下载」）：同样只是入队。"""
        self.enqueue_ids([str(album_id) for album_id in ids])

    def enqueue_ids(self, ids):
        """把 ID 加入下载队列，返回真正新增的 ID 列表。"""
        ids = [str(album_id).strip() for album_id in ids]
        ids = [album_id for album_id in ids if album_id]
        if not ids:
            self.set_status(self.t("status_need_ids"), COLOR_ERR)
            return []
        # 入队前把界面输入同步进配置并落盘：队列线程随后读的就是这份配置
        self.sync_conf()
        mail_conf = self.conf["mail"]
        if mail_conf.get("enable") and not (mail_conf.get("sender") and mail_conf.get("password")):
            self.set_status(self.t("status_mail_incomplete"), COLOR_ERR)
            return []
        try:
            conf_mod.save_conf(self.conf)
        except OSError:
            pass
        added, duplicated = self.queue.enqueue(ids)
        if added:
            self.set_status(self.t("status_task_enqueued", count=len(added)), COLOR_OK)
            # 详情只用于让等待中的任务也有名称与总页数，取不到不影响任务本身
            self.page.run_thread(self._prefetch_details, added)
        elif duplicated:
            self.set_status(self.t("status_task_duplicated",
                                   ids=", ".join(duplicated)), COLOR_ERR)
        return added

    def _prefetch_details(self, ids):
        """给刚入队的任务补名称与总页数（后台线程，逐个取，失败就跳过）。"""
        try:
            client = build_option(self.conf, with_login=False).new_jm_client()
        except Exception:
            return
        for album_id in ids:
            try:
                detail = client.get_album_detail(album_id)
            except Exception:
                continue
            self.queue.update_meta(album_id, getattr(detail, "name", ""),
                                   getattr(detail, "page_count", 0))

    # ------------------------------------------------------------------
    # 队列事件与界面刷新
    # ------------------------------------------------------------------
    def _on_queue_change(self):
        """队列状态 / 进度变化（可能来自下载线程）：把刷新交给页面事件循环。

        进度回调来自 jmcomic 的下载线程，直接改控件会像旧版那样「界面没反应」，
        因此统一用 ``page.run_task`` 排到页面事件循环里执行，并用待处理标记
        避免刷新任务堆积。
        """
        if self._refresh_pending:
            return
        self._refresh_pending = True
        try:
            self.page.run_task(self._apply_queue_refresh)
        except Exception:
            self._refresh_pending = False

    async def _apply_queue_refresh(self):
        """在页面事件循环里刷新与队列有关的界面。"""
        self._refresh_pending = False
        busy = self.queue.has_active()
        self._sync_close_flag(busy)
        if self.task_page is not None:
            self.task_page.refresh()
        if self.main_page is not None:
            self.main_page.refresh()
        if busy and not self._queue_busy:
            self._queue_busy = True
            self.set_status(self.t("status_downloading"))
        elif self._queue_busy and not busy:
            self._queue_busy = False
            self._set_queue_done_status()
        self.update()

    def _set_queue_done_status(self):
        """队列收尾：按本次会话的完成 / 失败情况给一句总结。"""
        session = self.queue.session()
        if session.get("failed"):
            self.set_status(self.t("status_download_retry"), COLOR_ERR)
        elif session.get("done"):
            self.set_status(self.t("status_done", count=session["done"],
                                   pdfs=session.get("pdfs", 0)), COLOR_OK)

    def _sync_close_flag(self, busy):
        """只在队列有活动任务时拦截关窗，空闲时保持系统默认的关闭行为。"""
        if bool(self.page.window.prevent_close) != bool(busy):
            self.page.window.prevent_close = bool(busy)

    def _restore_queue(self):
        """启动时恢复上次未完成的任务（不自动开跑，交给用户决定何时继续）。"""
        try:
            restored = self.queue.load()
        except Exception:
            return
        if restored:
            self.append_log(self.t("log_queue_restored", count=restored))

    # ------------------------------------------------------------------
    # 关窗
    # ------------------------------------------------------------------
    def _on_window_event(self, e):
        """关窗事件：队列有活动任务时先落盘并询问，避免悄悄丢掉进度。"""
        if getattr(e, "type", None) != ft.WindowEventType.CLOSE:
            return
        count = self.queue.unfinished_count()
        if not count:
            self.queue.shutdown()
            self._destroy_window()
            return
        dialog = ft.AlertDialog(
            title=ft.Text(self.t("exit_confirm_title")),
            content=ft.Text(self.t("exit_confirm_body", count=count), size=12,
                            selectable=True),
            actions=[
                ft.TextButton(self.t("btn_cancel"),
                              on_click=lambda e: self.page.pop_dialog()),
                ft.TextButton(self.t("btn_exit_keep"),
                              on_click=lambda e: self._exit_keep_queue()),
            ],
        )
        self.page.show_dialog(dialog)

    def _exit_keep_queue(self):
        """确认退出：先落盘再关窗，未完成任务下次启动可继续。"""
        self.page.pop_dialog()
        self.queue.shutdown()
        self._destroy_window()

    def _destroy_window(self):
        self.page.run_task(self._close_window)

    async def _close_window(self):
        try:
            await self.page.window.destroy()
        except Exception:
            pass
