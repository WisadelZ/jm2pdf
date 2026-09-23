# -*- coding: utf-8 -*-
"""资源管理器页：按漫画归组管理下载目录里的 PDF 与图片文件夹。

同一本漫画的 PDF 与图片文件夹用折叠菜单归在一起；勾选后可以打开、浏览或删除
（删除为移入回收站）。勾选 PDF 时右侧边栏展示该 PDF 里的漫画元数据。

只勾选一项时才能「打开」「浏览」；勾选多项时只保留「删除」。
「浏览」在页面上叠一层阅读界面（背景模糊变暗），浏览文件夹时自动打开里面的图片。
"""

import os

import flet as ft

from core import library, pdf_metadata, reader
from core.config import resolve_path
from core.constants import COLOR_ERR, ROUTE_EXPLORER, ROUTE_MAIN
from ui.reader_view import ReaderView

# 右侧边栏宽度（窗口默认 660，留给列表的宽度仍然充足）
PANEL_WIDTH = 250

# 元数据字段缺失时的占位符
EMPTY_VALUE = "—"


class ExplorerPage:
    def __init__(self, app):
        self.app = app
        self.base_dir = ""
        self.boxes = {}          # 路径 -> 勾选框控件
        self.meta_pdf = None     # 当前在边栏展示元数据的 PDF

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def build_view(self):
        app = self.app
        self.base_dir = resolve_path(app.conf["app"].get("download_dir"))
        self.status_text = ft.Text(app.status_text_value, size=12, color=app.status_color)
        self.path_text = ft.Text(self.t("explorer_dir", path=self.base_dir), size=11,
                                 color=ft.Colors.ON_SURFACE_VARIANT, selectable=True, expand=True)
        self.list_view = ft.ListView(expand=True, spacing=2, padding=6)
        self.panel_box = ft.Container(
            width=PANEL_WIDTH, padding=12, border_radius=8,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT))

        # 只勾选一项时才可操作，初始没有任何勾选
        self.btn_open = ft.Button(self.t("btn_open_selected"), icon=ft.Icons.OPEN_IN_NEW,
                                  disabled=True, on_click=self._on_open)
        self.btn_browse = ft.Button(self.t("btn_browse"), icon=ft.Icons.AUTO_STORIES,
                                    disabled=True, on_click=self._on_browse)
        self.btn_delete = ft.Button(self.t("btn_delete_selected"), icon=ft.Icons.DELETE_OUTLINE,
                                    on_click=self._on_delete)

        left = ft.Column([
            ft.Row([self.path_text,
                    ft.Button(self.t("btn_refresh"), icon=ft.Icons.REFRESH,
                              on_click=lambda e: self.reload())], spacing=8),
            ft.Divider(height=1),
            ft.Container(content=self.list_view, expand=True, border_radius=6,
                         border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)),
            ft.Row([self.btn_open, self.btn_browse, self.btn_delete], spacing=10),
            self.status_text,
        ], expand=True, spacing=8)

        row = ft.Row([left, self.panel_box], expand=True, spacing=12,
                     vertical_alignment=ft.CrossAxisAlignment.STRETCH)
        # 内容整块模糊变暗由浏览层控制，因此包一层容器叠在浏览层下面
        self.content_box = ft.Container(content=row, left=0, top=0, right=0, bottom=0)
        self.browser = ReaderView(app, self.content_box)

        view = ft.View(
            route=ROUTE_EXPLORER,
            appbar=ft.AppBar(
                title=ft.Text(self.t("explorer_title")),
                leading=ft.IconButton(ft.Icons.ARROW_BACK,
                                      on_click=lambda e: app.navigate(ROUTE_MAIN)),
            ),
            controls=[ft.Stack([self.content_box, self.browser.build()], expand=True)],
            padding=12,
        )
        self.browser.attach(view)
        app.bind_status(self.status_text)
        self.reload()
        return view

    def reload(self):
        """重新扫描下载目录，重建列表与边栏状态。"""
        self.boxes = {}
        self.meta_pdf = None
        try:
            entries = library.scan_library(self.base_dir)
        except OSError as exc:
            entries = []
            self.app.set_status(self.t("explorer_scan_failed", error=exc), COLOR_ERR)
        self.list_view.controls = self._build_rows(entries)
        self._refresh_panel()
        self._refresh_actions()
        self.app.update()

    def _build_rows(self, entries):
        if not entries:
            return [ft.Container(
                content=ft.Text(self.t("explorer_empty"), size=12,
                                color=ft.Colors.ON_SURFACE_VARIANT),
                padding=12)]
        rows = []
        for entry in entries:
            children = []
            if entry["folder"]:
                children.append(self._item_row(entry["folder"], self.t("explorer_type_folder"),
                                               ft.Icons.FOLDER))
            if entry["pdf"]:
                children.append(self._item_row(entry["pdf"], self.t("explorer_type_pdf"),
                                               ft.Icons.PICTURE_AS_PDF))
            if len(children) == 1:
                # 只有 PDF 或只有图片文件夹时直接平铺，不再多套一层折叠菜单
                rows.append(children[0])
            else:
                rows.append(ft.ExpansionTile(
                    title=ft.Text(entry["name"], size=13, max_lines=1,
                                  overflow=ft.TextOverflow.ELLIPSIS),
                    controls=children,
                    controls_padding=ft.Padding.only(left=8, right=8, bottom=6),
                ))
        return rows

    def _item_row(self, path, type_label, icon):
        checkbox = ft.Checkbox(value=False, data=path, on_change=self._on_check)
        self.boxes[path] = checkbox
        return ft.ListTile(
            leading=checkbox,
            title=ft.Text(os.path.basename(path), size=12, max_lines=1,
                          overflow=ft.TextOverflow.ELLIPSIS),
            subtitle=ft.Row([ft.Icon(icon, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                             ft.Text(type_label, size=11, color=ft.Colors.ON_SURFACE_VARIANT)],
                            spacing=4),
            dense=True,
            content_padding=ft.Padding.only(left=4, right=4),
        )

    # ------------------------------------------------------------------
    # 元数据边栏
    # ------------------------------------------------------------------
    def _refresh_panel(self):
        self.panel_box.content = self._build_panel()
        self.app.update()

    def _build_panel(self):
        rows = [ft.Text(self.t("panel_meta_title"), size=14, weight=ft.FontWeight.BOLD)]
        if self.meta_pdf is None:
            rows.append(ft.Text(self.t("panel_meta_hint"), size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT))
            return ft.Column(rows, spacing=10, scroll=ft.ScrollMode.AUTO)

        rows.append(ft.Text(os.path.basename(self.meta_pdf), size=11,
                            color=ft.Colors.ON_SURFACE_VARIANT, selectable=True))
        try:
            meta = pdf_metadata.read_metadata(self.meta_pdf)
        except Exception as exc:      # 文件损坏 / 被加密等
            rows.append(ft.Text(self.t("panel_meta_failed", error=exc), size=11,
                                color=COLOR_ERR, selectable=True))
            return ft.Column(rows, spacing=10, scroll=ft.ScrollMode.AUTO)
        if meta is None:
            rows.append(ft.Text(self.t("panel_meta_none"), size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT))
            return ft.Column(rows, spacing=10, scroll=ft.ScrollMode.AUTO)

        for key, value in (("meta_title", meta["title"]), ("meta_album_id", meta["album_id"]),
                           ("meta_author", meta["author"]), ("meta_tags", meta["tags"]),
                           ("meta_pages", meta["pages"]), ("meta_chapter", meta["chapter"])):
            rows.append(self._meta_row(self.t(key), value))
        return ft.Column(rows, spacing=10, scroll=ft.ScrollMode.AUTO)

    def _meta_row(self, label, value):
        return ft.Column([
            ft.Text(label, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(value or EMPTY_VALUE, size=12, selectable=True),
        ], spacing=2)

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _checked_paths(self):
        return [path for path, box in self.boxes.items() if box.value]

    def _on_check(self, e):
        path = e.control.data
        if e.control.value and path.lower().endswith(library.PDF_SUFFIX):
            self.meta_pdf = path          # 勾选 PDF 即展示其元数据
        elif not e.control.value and path == self.meta_pdf:
            self.meta_pdf = None
        self._refresh_panel()
        self._refresh_actions()

    def _refresh_actions(self):
        """勾选多项时只保留「删除」，「打开」与「浏览」都不可点。"""
        single = len(self._checked_paths()) == 1
        self.btn_open.disabled = not single
        self.btn_browse.disabled = not single
        self.app.update()

    def _on_open(self, e):
        paths = self._checked_paths()
        if not paths:
            self.app.set_status(self.t("explorer_need_selection"), COLOR_ERR)
            return
        try:
            for path in paths:
                library.open_path(path)
        except OSError as exc:
            self.app.set_status(self.t("status_open_failed", error=exc), COLOR_ERR)
            return
        self.app.set_status(
            self.t("status_opened", name=", ".join(os.path.basename(p) for p in paths)))

    def _on_browse(self, e):
        """浏览选中的 PDF 或图片文件夹；空的图片文件夹只提示，不打开浏览层。"""
        paths = self._checked_paths()
        if len(paths) != 1:
            self.app.set_status(self.t("explorer_need_selection"), COLOR_ERR)
            return
        path = paths[0]
        if os.path.isdir(path) and not reader.list_images(path):
            self.app.set_status(self.t("explorer_no_images"), COLOR_ERR)
            return
        self.browser.open(path)

    def _on_delete(self, e):
        paths = self._checked_paths()
        if not paths:
            self.app.set_status(self.t("explorer_need_selection"), COLOR_ERR)
            return
        names = "\n".join(os.path.basename(path) for path in paths)
        dialog = ft.AlertDialog(
            title=ft.Text(self.t("delete_dialog_title")),
            content=ft.Text(self.t("delete_dialog_body", count=len(paths), items=names),
                            size=12, selectable=True),
            actions=[
                ft.TextButton(self.t("btn_cancel"),
                              on_click=lambda e: self.app.page.pop_dialog()),
                ft.TextButton(self.t("btn_confirm_delete"),
                              on_click=lambda e: self._confirm_delete(paths)),
            ],
        )
        self.app.page.show_dialog(dialog)

    def _confirm_delete(self, paths):
        self.app.page.pop_dialog()
        try:
            library.delete_to_recycle_bin(paths)
        except OSError as exc:
            self.app.set_status(self.t("status_delete_failed", error=exc), COLOR_ERR)
            return
        self.app.set_status(self.t("status_deleted", count=len(paths)))
        self.reload()
