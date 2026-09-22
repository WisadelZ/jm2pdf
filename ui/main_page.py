# -*- coding: utf-8 -*-
"""主页视图：下载任务输入、搜索、下载选项、邮件推送与日志区。

本类只负责界面呈现与输入收集，搜索 / 下载 / 配置保存等业务逻辑
统一由 :class:`jm2pdf.ui.app_ui.AppUI` 处理。
"""

import os

import flet as ft

from core.constants import ROUTE_EXPLORER, ROUTE_HELP, ROUTE_MAIN, ROUTE_SETTINGS
from utils.helpers import clamp

# 搜索结果框右侧封面缩略图尺寸（3:4，与网站封面图比例一致）
COVER_WIDTH = 78
COVER_HEIGHT = 104


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

        # ---- 操作行：PDF 开关 + 开始下载 + 状态 + 进度 ----
        self.to_pdf_switch = ft.Switch(
            label=self.t("switch_to_pdf"), value=bool(app_conf.get("to_pdf", True)),
            on_change=lambda e: app.on_conf_change())
        self.btn_start = ft.Button(self.t("btn_start"), on_click=lambda e: app.start())
        self.status_text = ft.Text(app.status_text_value, size=12, color=app.status_color, expand=True)
        self.progress = ft.ProgressRing(visible=False, width=22, height=22, stroke_width=3)

        # ---- 下载选项（折叠）----
        self.thread_image_field = ft.TextField(
            label=self.t("label_thread_image"), width=100,
            value=str(clamp(app_conf.get("thread_image", 30), 1, 50)),
            on_change=lambda e: app.on_conf_change())
        self.thread_photo_field = ft.TextField(
            label=self.t("label_thread_photo"), width=100,
            value=str(clamp(app_conf.get("thread_photo", 16), 1, 64)),
            on_change=lambda e: app.on_conf_change())
        self.username_field = ft.TextField(
            label=self.t("label_username"), expand=True, value=app_conf.get("username") or "",
            on_change=lambda e: app.on_conf_change())
        self.password_field = ft.TextField(
            label=self.t("label_password"), expand=True, password=True,
            value=app_conf.get("password") or "", on_change=lambda e: app.on_conf_change())

        opt_tile = ft.ExpansionTile(
            title=ft.Text(self.t("tile_download_options")),
            controls=[ft.Column([
                ft.Row([self.thread_image_field, self.thread_photo_field], spacing=16),
                ft.Row([self.username_field, self.password_field], spacing=16),
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

        # ---- 日志 ----
        self.log_list = ft.ListView(expand=True, auto_scroll=True, padding=6, spacing=2)
        self.log_box = ft.Container(
            content=self.log_list, border=ft.Border.all(1, "#333333"),
            border_radius=6, bgcolor="#1e1e1e", height=200, padding=2)

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
            ft.Row([self.to_pdf_switch, self.btn_start, self.status_text, self.progress],
                   spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self.opt_tile,
            self.mail_tile,
        ], scroll=ft.ScrollMode.AUTO, spacing=18, expand=True)

        # 顶部工具栏：功能按钮自左向右排列，后续新增功能继续往右追加即可
        toolbar = ft.Row([
            ft.OutlinedButton(self.t("btn_explorer"), icon=ft.Icons.FOLDER_OPEN,
                              on_click=lambda e: app.navigate(ROUTE_EXPLORER)),
            ft.OutlinedButton(self.t("btn_help"), icon=ft.Icons.HELP_OUTLINE,
                              on_click=lambda e: app.navigate(ROUTE_HELP)),
            ft.OutlinedButton(self.t("btn_settings"), icon=ft.Icons.SETTINGS,
                              on_click=lambda e: app.navigate(ROUTE_SETTINGS)),
        ], spacing=8, alignment=ft.MainAxisAlignment.START)

        # 工具栏自身保持紧凑，与表单之间仅留一段小间距，
        # 首个输入框所需的额外空间已放进 form_col 内部
        content = ft.Column([
            toolbar,
            ft.Divider(height=1),
            form_col,
            self.log_box,
        ], expand=True, spacing=8)

        view = ft.View(route=ROUTE_MAIN, controls=[content], padding=12)

        app.bind_status(self.status_text)
        app.bind_log_view(self.log_list)
        self.refresh()
        return view

    def refresh(self):
        """按全局状态刷新控件的可用性、状态文本与搜索结果。"""
        app = self.app
        self.btn_search.disabled = app.searching
        self.btn_add.disabled = not bool(app.searched_id)
        self.btn_start.disabled = app.running
        self.progress.visible = app.running
        self.status_text.value = app.status_text_value
        self.status_text.color = app.status_color
        self.result_text.spans = self._result_spans()
        self._sync_cover()
        app.update()

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
            "username": self.username_field.value or "",
            "password": self.password_field.value or "",
            # 外观与语言由设置页维护，此处原样保留
            "theme_mode": app_conf.get("theme_mode", "light"),
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
        self.ids_field.value = ""
        self.app.pending_ids_text = ""
        self.app.update()

    async def _on_browse(self, e):
        # Flet 1.0: get_directory_path 为异步方法，直接返回所选路径
        path = await self.app.picker.get_directory_path(dialog_title=self.t("label_download_dir"))
        if path:
            self.dir_field.value = os.path.normpath(path)
            self.app.on_conf_change()
            self.app.update()
