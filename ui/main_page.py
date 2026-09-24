# -*- coding: utf-8 -*-
"""下载页视图：下载任务输入、搜索、下载选项、邮件推送与日志区。

首页（探索页）顶栏的「下载」按钮进入本页；本页只负责界面呈现与输入收集，
搜索 / 下载 / 配置保存等业务逻辑统一由 :class:`jm2pdf.ui.app_ui.AppUI` 处理。
"""

import os

import flet as ft

from core.constants import ROUTE_DOWNLOAD, ROUTE_MAIN, ROUTE_TASKS
from utils.helpers import clamp

# 搜索结果框右侧封面缩略图尺寸（3:4，与网站封面图比例一致）
COVER_WIDTH = 78
COVER_HEIGHT = 104

# 日志区上方的队列概览：细进度条宽度 + 概览文本颜色（贴合日志区的深底）
OVERVIEW_BAR_WIDTH = 80
OVERVIEW_BAR_HEIGHT = 4
OVERVIEW_TEXT_COLOR = "#9a9a9a"
# 展开下载日志后的日志框高度
LOG_BOX_HEIGHT = 200
LOG_BOX_BGCOLOR = "#1e1e1e"

# 顶栏右侧留白：图标按钮自带 8px 内边距，这里再补 4px，使图标视觉上距右边缘约 12px，
# 与页面其余控件的 12px 边距一致
APPBAR_RIGHT_GAP = 4


class MainPage:
    def __init__(self, app):
        self.app = app
        self._build_controls()

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    # ------------------------------------------------------------------
    # 控件构建
    # ------------------------------------------------------------------
    def _build_controls(self):
        app = self.app
        app_conf = app.conf["app"]
        mail_conf = app.conf["mail"]

        # ---- 下载任务 ----
        self.ids_field = ft.TextField(
            label=self.t("label_ids"), hint_text=self.t("hint_ids"), expand=True,
            value=app.pending_ids_text, on_change=self._on_ids_change)
        self.btn_clear_ids = ft.Button(self.t("btn_clear"), on_click=self._on_clear_ids)

        self.dir_field = ft.TextField(
            label=self.t("label_download_dir"), expand=True,
            value=str(app_conf.get("download_dir") or "./download"),
            on_change=lambda e: app.on_conf_change())
        self.btn_browse = ft.Button(self.t("btn_browse"), on_click=self._on_browse)

        # ---- 搜索 ----
        self.search_field = ft.TextField(
            label=self.t("label_search_id"), expand=True, value=app.pending_search_text,
            on_change=self._on_search_text_change,
            on_submit=lambda e: app.search())
        self.btn_search = ft.Button(self.t("btn_search"), on_click=lambda e: app.search())

        self.result_text = ft.Text(spans=[], selectable=True, size=12)
        # 搜索结果框右侧的封面缩略图：内容按需填充，没有封面时整块留空
        self.cover_holder = ft.Container(width=COVER_WIDTH, height=COVER_HEIGHT,
                                         alignment=ft.Alignment.CENTER)
        self._cover_key = None
        self.result_box = ft.Container(
            content=ft.Row([
                ft.ListView(controls=[self.result_text], padding=6, expand=True),
                ft.Container(content=self.cover_holder,
                             padding=ft.Padding.only(right=6, top=6, bottom=6)),
            ], spacing=6),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=6,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            height=COVER_HEIGHT + 16, expand=True, padding=2)
        self.btn_add = ft.Button(self.t("btn_add"), on_click=lambda e: app.add_searched())

        # ---- 操作行：PDF 开关 + 加入队列 + 状态 ----
        # 这里不再放不定态进度环：队列里每个任务的确定进度都在任务中心展示，
        # 状态文本独占剩余宽度，操作行不被挤满
        self.to_pdf_switch = ft.Switch(
            label=self.t("switch_to_pdf"), value=bool(app_conf.get("to_pdf", True)),
            on_change=lambda e: app.on_conf_change())
        self.btn_start = ft.Button(self.t("btn_add_to_queue"), on_click=lambda e: app.start())
        self.status_text = ft.Text(app.status_text_value, size=12, color=app.status_color, expand=True)

        # ---- 下载选项（折叠）----
        self.thread_image_field = ft.TextField(
            label=self.t("label_thread_image"), width=100,
            value=str(clamp(app_conf.get("thread_image", 30), 1, 50)),
            on_change=lambda e: app.on_conf_change())
        self.thread_photo_field = ft.TextField(
            label=self.t("label_thread_photo"), width=100,
            value=str(clamp(app_conf.get("thread_photo", 16), 1, 64)),
            on_change=lambda e: app.on_conf_change())
        # 同时下载几个本子（队列级并发）：与上面两个字段同一档尺寸
        self.task_concurrency_field = ft.TextField(
            label=self.t("label_task_concurrency"), width=100,
            value=str(clamp(app_conf.get("task_concurrency", 2), 1, 4)),
            on_change=lambda e: app.on_conf_change())

        opt_tile = ft.ExpansionTile(
            title=ft.Text(self.t("tile_download_options")),
            controls=[ft.Column([
                ft.Row([self.thread_image_field, self.thread_photo_field,
                        self.task_concurrency_field], spacing=16),
            ], spacing=14)],
            controls_padding=ft.Padding.only(left=8, right=8, top=14, bottom=8),
        )

        # ---- 邮件推送（折叠）----
        self.mail_enable_switch = ft.Switch(
            label=self.t("switch_mail_enable"), value=bool(mail_conf.get("enable", False)),
            on_change=lambda e: app.on_conf_change())
        self.mail_server_field = ft.TextField(
            label=self.t("label_mail_server"), expand=True,
            value=mail_conf.get("server") or "smtp.qq.com",
            on_change=lambda e: app.on_conf_change())
        self.mail_port_field = ft.TextField(
            label=self.t("label_mail_port"), width=80, value=str(mail_conf.get("port", 465)),
            on_change=lambda e: app.on_conf_change())
        self.mail_sender_field = ft.TextField(
            label=self.t("label_mail_sender"), expand=True, value=mail_conf.get("sender") or "",
            on_change=lambda e: app.on_conf_change())
        self.mail_password_field = ft.TextField(
            label=self.t("label_mail_password"), expand=True, password=True,
            value=mail_conf.get("password") or "", on_change=lambda e: app.on_conf_change())
        self.mail_receiver_field = ft.TextField(
            label=self.t("label_mail_receiver"), expand=True,
            value=mail_conf.get("receiver") or "", on_change=lambda e: app.on_conf_change())
        self.mail_subject_field = ft.TextField(
            label=self.t("label_mail_subject"), expand=True, value=mail_conf.get("subject") or "",
            on_change=lambda e: app.on_conf_change())
        self.mail_body_field = ft.TextField(
            label=self.t("label_mail_body"), expand=True, value=mail_conf.get("body") or "",
            on_change=lambda e: app.on_conf_change())

        mail_tile = ft.ExpansionTile(
            title=ft.Text(self.t("tile_mail")),
            controls=[ft.Column([
                self.mail_enable_switch,
                ft.Row([self.mail_server_field, self.mail_port_field], spacing=10),
                ft.Row([self.mail_sender_field, self.mail_password_field], spacing=10),
                self.mail_receiver_field,
                self.mail_subject_field,
                self.mail_body_field,
            ], spacing=14)],
            controls_padding=ft.Padding.only(left=8, right=8, top=14, bottom=8),
        )

        self.opt_tile = opt_tile
        self.mail_tile = mail_tile

        # ---- 下载日志（折叠面板，默认收起：日志不再长期占着页面）----
        self.log_list = ft.ListView(expand=True, auto_scroll=True, padding=6, spacing=2)
        # 队列概览作为折叠面板的副标题：收起时也能一眼看到「走到哪了」
        self.overview_bar = ft.ProgressBar(
            value=0, width=OVERVIEW_BAR_WIDTH, height=OVERVIEW_BAR_HEIGHT,
            visible=False, border_radius=OVERVIEW_BAR_HEIGHT / 2)
        self.overview_text = ft.Text(
            "", size=11, color=OVERVIEW_TEXT_COLOR, expand=True, max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS)
        self.overview_row = ft.Row(
            [self.overview_bar, self.overview_text], spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.log_box = ft.Container(
            content=self.log_list,
            border=ft.Border.all(1, "#333333"),
            border_radius=6, bgcolor=LOG_BOX_BGCOLOR, height=LOG_BOX_HEIGHT,
            padding=6)
        self.log_tile = ft.ExpansionTile(
            title=ft.Text(self.t("tile_download_log")),
            subtitle=self.overview_row,
            controls=[self.log_box],
            controls_padding=ft.Padding.only(left=8, right=8, top=14, bottom=8),
        )

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def build_view(self):
        app = self.app
        # 表单区可滚动：展开折叠面板时内容超出窗口高度时出现右侧滚动条，
        # 无需手动拉高窗口；spacing 加大避免输入框标签与上一个输入框贴在一起
        form_col = ft.Column([
            # 首个输入框上方的留白必须放在滚动容器内部：滚动容器会裁剪越界内容，
            # 放在外面的留白留不住它，浮动标签「本子 ID」的上半部分会被齐整切掉
            ft.Container(
                content=ft.Row([self.ids_field, self.btn_clear_ids], spacing=8),
                margin=ft.Margin.only(top=16),
            ),
            ft.Row([self.dir_field, self.btn_browse], spacing=8),
            ft.Row([self.search_field, self.btn_search], spacing=8),
            ft.Row([self.result_box, self.btn_add], spacing=8),
            ft.Row([self.to_pdf_switch, self.btn_start, self.status_text],
                   spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self.opt_tile,
            self.mail_tile,
            self.log_tile,
        ], scroll=ft.ScrollMode.AUTO, spacing=18, expand=True)

        # 下载页与资源管理器 / 帮助 / 设置页一样依附于首页：
        # 左上角是返回首页（探索页）的按钮，因此不再放工具栏
        content = ft.Column([form_col], expand=True, spacing=8)

        view = ft.View(
            route=ROUTE_DOWNLOAD,
            appbar=ft.AppBar(
                title=ft.Text(self.t("btn_download")),
                leading=ft.IconButton(ft.Icons.ARROW_BACK,
                                      on_click=lambda e: app.navigate(ROUTE_MAIN)),
                # 任务中心入口放顶栏右上角：不占操作行宽度，也不会挤压状态文本；
                # 末尾补一个与页面内边距相当的空位，避免图标贴到窗口右边缘
                actions=[ft.IconButton(ft.Icons.LIST_ALT, tooltip=self.t("btn_tasks"),
                                       on_click=lambda e: app.navigate(ROUTE_TASKS)),
                         ft.Container(width=APPBAR_RIGHT_GAP)],
            ),
            controls=[content],
            padding=12,
        )

        app.bind_status(self.status_text)
        app.bind_log_view(self.log_list)
        self.refresh()
        return view

    def refresh(self):
        """按全局状态刷新控件的可用性、状态文本、队列概览与搜索结果。"""
        app = self.app
        self.btn_search.disabled = app.searching
        self.btn_add.disabled = not bool(app.searched_id)
        self.status_text.value = app.status_text_value
        self.status_text.color = app.status_color
        self._refresh_overview()
        self.result_text.spans = self._result_spans()
        self._sync_cover()
        app.update()

    def _refresh_overview(self):
        """刷新日志上方的队列概览：统计各状态任务数，并给一条整体进度。

        「整体进度」按已完成 / 已结束计数算，只作粗略参考；每个任务的精确页数
        进度在任务中心里看。
        """
        stats = self.app.queue.stats()
        waiting, running = stats.get("waiting", 0), stats.get("running", 0)
        done, failed = stats.get("done", 0), stats.get("failed", 0)
        busy = bool(waiting or running)
        self.overview_bar.visible = busy
        if busy:
            ended = done + failed + waiting + running
            self.overview_bar.value = (done / float(ended)) if ended else 0
            self.overview_text.value = self.t("tasks_overview", total=stats.get("total", 0),
                                              waiting=waiting, running=running,
                                              failed=failed)
        elif stats.get("total"):
            self.overview_bar.value = 0
            self.overview_text.value = self.t("tasks_overview_idle",
                                              total=stats.get("total", 0))
        else:
            self.overview_bar.value = 0
            self.overview_text.value = self.t("tasks_overview_empty")

    def _sync_cover(self):
        """按搜索结果同步封面图；只在结果变化时重建，避免刷新时重复加载。"""
        if self.app.searched_id == self._cover_key:
            return
        self._cover_key = self.app.searched_id
        cover = self.app.searched_cover
        if not cover:
            self.cover_holder.content = None
            return
        self.cover_holder.content = ft.Image(
            src=cover, width=COVER_WIDTH, height=COVER_HEIGHT,
            fit=ft.BoxFit.COVER, border_radius=4,
            error_content=ft.Icon(ft.Icons.BROKEN_IMAGE, size=20,
                                  color=ft.Colors.ON_SURFACE_VARIANT,
                                  tooltip=self.t("cover_load_failed")))

    def _result_spans(self):
        """搜索结果文本；搜索成功时在末尾附上可点击的网页链接。"""
        app = self.app
        spans = [ft.TextSpan(app.search_text)]
        if app.searched_url:
            spans.append(ft.TextSpan("\n%s " % self.t("search_link")))
            spans.append(ft.TextSpan(
                app.searched_url, url=app.searched_url,
                style=ft.TextStyle(color=ft.Colors.PRIMARY,
                                   decoration=ft.TextDecoration.UNDERLINE)))
        return spans

    # ------------------------------------------------------------------
    # 输入收集
    # ------------------------------------------------------------------
    def sync_conf_from_ui(self):
        """把界面上的输入同步进 AppUI.conf（不触发保存）。"""
        conf = self.app.conf
        app_conf = conf["app"]
        conf["app"] = {
            "download_dir": (self.dir_field.value or "").strip() or "./download",
            "to_pdf": bool(self.to_pdf_switch.value),
            "thread_image": self._field_int(self.thread_image_field, 30),
            "thread_photo": self._field_int(self.thread_photo_field, 16),
            "task_concurrency": clamp(self._field_int(self.task_concurrency_field, 2), 1, 4),
            # 外观与语言由设置页维护，此处原样保留
            "theme_mode": app_conf.get("theme_mode", "dark"),
            "language": app_conf.get("language", "zh_cn"),
        }
        conf["mail"] = {
            "enable": bool(self.mail_enable_switch.value),
            "server": (self.mail_server_field.value or "").strip() or "smtp.qq.com",
            "port": self._field_int(self.mail_port_field, 465),
            "sender": (self.mail_sender_field.value or "").strip(),
            "password": self.mail_password_field.value or "",
            "receiver": (self.mail_receiver_field.value or "").strip(),
            "subject": self.mail_subject_field.value or "",
            "body": self.mail_body_field.value or "",
        }

    @staticmethod
    def _field_int(field, default):
        try:
            return int(str(field.value).strip())
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _on_ids_change(self, e):
        # 语言切换会重建界面，这里缓存输入以免内容丢失
        self.app.pending_ids_text = self.ids_field.value or ""

    def _on_search_text_change(self, e):
        self.app.pending_search_text = self.search_field.value or ""

    def _on_clear_ids(self, e):
        self.clear_ids()
        self.app.update()

    def clear_ids(self):
        """清空本子 ID 输入框。

        输入框只用来收集「待入队」的 ID：入队成功后由 :meth:`AppUI.start` 调用，
        因此不必担心清掉还没入队的内容。
        """
        self.ids_field.value = ""
        self.app.pending_ids_text = ""

    async def _on_browse(self, e):
        # Flet 1.0: get_directory_path 为异步方法，直接返回所选路径
        path = await self.app.picker.get_directory_path(dialog_title=self.t("label_download_dir"))
        if path:
            self.dir_field.value = os.path.normpath(path)
            self.app.on_conf_change()
            self.app.update()
