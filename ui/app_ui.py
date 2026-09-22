# -*- coding: utf-8 -*-
"""UI 协调层：窗口设置、路由、全局状态、配置持久化、日志与业务调度。

界面视图（MainPage / SettingsPage）只负责呈现与收集输入，
所有业务动作集中在这里，便于测试与后续扩展。
"""

import copy
import logging
import os
import threading
import traceback

import flet as ft
import jmcomic
import yaml

from core import config as conf_mod
from core.config import THEME_MODES
from core.constants import (APP_VERSION, COLOR_ERR, COLOR_IDLE, COLOR_OK,
                            ROUTE_EXPLORER, ROUTE_HELP, ROUTE_MAIN,
                            ROUTE_SETTINGS, UI_FONT_FAMILY, WINDOW_HEIGHT,
                            WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH, WINDOW_WIDTH)
from core.downloader import (album_url, build_option, collect_pdfs, fetch_cover,
                             send_mail)
from core.logging_bridge import UiLogHandler
from ui.explorer_page import ExplorerPage
from ui.help_page import HelpPage
from ui.main_page import MainPage
from ui.settings_page import SettingsPage
from utils.helpers import parse_ids
from utils.i18n import LANGUAGE_NAMES, LANGUAGES, I18n

MAX_LOG_LINES = 500


class AppUI:
    SAVE_DELAY = 0.5

    def __init__(self, page: ft.Page):
        self.page = page
        self.conf = conf_mod.load_conf()
        self.i18n = I18n(self.conf["app"].get("language"))

        # 运行状态（跨视图重建保留）
        self.running = False
        self.searching = False
        self.searched_id = ""
        self.searched_url = ""
        self.searched_cover = None      # 封面图字节，只留在内存里，不落盘
        self.search_text = ""
        self.status_text_value = self.t("status_ready")
        self.status_color = COLOR_IDLE
        # 未落盘的界面输入，用于语言切换重建后还原
        self.pending_ids_text = ""
        self.pending_search_text = ""

        # 日志缓冲（跨视图重建保留）
        self.log_lines = []
        self.log_view = None
        self.status_text = None
        self.main_page = None
        self._save_timer = None

        # 目录/文件选择器：Flet 1.0 中 FilePicker 为 service，需注册到 page.services
        self.picker = ft.FilePicker()
        page.services.append(self.picker)

        self._setup_window()
        self._setup_logging()
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

    def navigate(self, route):
        self.page.navigate(route)

    def _on_route_change(self, e=None):
        self.build()

    def theme_mode_value(self):
        mode = str(self.conf["app"].get("theme_mode") or "light").lower()
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
        """按当前路由重建视图树。语言切换、导入配置后都会调用。"""
        route = self.page.route or ROUTE_MAIN
        self.log_view = None
        self.main_page = None
        self.page.views.clear()
        if route == ROUTE_SETTINGS:
            view = SettingsPage(self).build_view()
        elif route == ROUTE_EXPLORER:
            view = ExplorerPage(self).build_view()
        elif route == ROUTE_HELP:
            view = HelpPage(self).build_view()
        else:
            self.main_page = MainPage(self)
            view = self.main_page.build_view()
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
        """把主页上的输入同步进配置（设置页自身不缓存输入）。"""
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
    # 下载
    # ------------------------------------------------------------------
    def start(self):
        if self.running:
            return
        ids = parse_ids(self.main_page.ids_field.value)
        if not ids:
            self.set_status(self.t("status_need_ids"), COLOR_ERR)
            return
        self.sync_conf()
        conf = copy.deepcopy(self.conf)
        mail_conf = conf["mail"]
        if mail_conf.get("enable") and not (mail_conf.get("sender") and mail_conf.get("password")):
            self.set_status(self.t("status_mail_incomplete"), COLOR_ERR)
            return
        try:
            conf_mod.save_conf(self.conf)
        except OSError:
            pass
        self.running = True
        self.main_page.refresh()
        self.set_status(self.t("status_downloading"))
        self.page.run_thread(self._run_task, ids, conf)

    def _run_task(self, ids, conf):
        try:
            download_dir = conf_mod.resolve_path(conf["app"].get("download_dir"))
            os.makedirs(download_dir, exist_ok=True)
            option = build_option(conf)
            self.append_log(self.t("log_start", count=len(ids), ids=", ".join(ids)))
            self.append_log(self.t("log_download_dir", path=download_dir))
            result = jmcomic.download_album(ids, option)
            failed = getattr(result, "failed", {}) or {}
            pdfs = collect_pdfs(result)
            for jmid, err in failed.items():
                self.append_log(self.t("log_download_failed", id=jmid, error=err))
            if conf["app"].get("to_pdf", True):
                if pdfs:
                    self.append_log(self.t("log_pdf_total", count=len(pdfs)))
                    for path in pdfs:
                        self.append_log("  %s" % path)
                else:
                    self.append_log(self.t("log_no_pdf"))
            else:
                self.append_log(self.t("log_skip_pdf"))
            mail_conf = conf["mail"]
            if mail_conf.get("enable"):
                if pdfs:
                    self.append_log(self.t("log_sending_mail"))
                    try:
                        send_mail(mail_conf, pdfs, self.append_log, self.t)
                        self.append_log(self.t("log_mail_sent"))
                    except Exception as exc:
                        self.append_log(self.t("log_mail_failed", error=exc))
                else:
                    self.append_log(self.t("log_no_pdf_for_mail"))
            if not failed:
                self._finish(True, self.t("status_done",
                                          count=len(ids) - len(failed), pdfs=len(pdfs)))
            else:
                self._finish(False, self.t("status_done_with_errors"))
        except Exception:
            self.append_log(self.t("log_error", error=traceback.format_exc()))
            self._finish(False, self.t("status_error"))

    def _finish(self, ok, status):
        self.running = False
        if self.main_page is not None:
            self.main_page.refresh()
        self.set_status(status, COLOR_OK if ok else COLOR_ERR)
