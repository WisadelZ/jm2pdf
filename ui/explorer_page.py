# -*- coding: utf-8 -*-
"""资源管理器页：按漫画归组管理下载目录里的 PDF 与图片文件夹。

同一本漫画的 PDF 与图片文件夹用折叠菜单归在一起；勾选后可以打开、浏览或删除
（删除为移入回收站）。勾选 PDF 时右侧边栏展示该 PDF 里的漫画元数据。

只勾选一项时才能「打开」「浏览」；勾选多项时只保留「删除」。
「浏览」在页面上叠一层阅读界面（背景模糊变暗），浏览文件夹时自动打开里面的图片。

搜索与排序都作用在扫描结果上（纯内存，不重新读盘）：
- 搜索栏可切换搜索方式：全部 / 名称 / 作者 / 标签 / 本子 ID，后四种按 PDF 元数据匹配
- 关键词输入后点搜索按钮或按回车才过滤（与探索页一致，不做输入即搜）
- 排序可按 名称 / 时间 / 大小 / 页数；旁边的按钮切换升序 / 降序，另一个按钮取消排序恢复默认
- 需要元数据（按作者等搜索、或按页数排序）时才后台读取并缓存，列表先保持原样
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

# 搜索方式下拉的宽度（与探索页的搜索方式下拉一致）
MODE_DROPDOWN_WIDTH = 104

# 排序菜单与控件高度：与探索页保持一致
TOOL_HEIGHT = 40
SORT_BOX_WIDTH = 84
SORT_ITEM_WIDTH = 110
SORT_CHECK_SIZE = 15


class ExplorerPage:
    def __init__(self, app):
        self.app = app
        self.base_dir = ""
        self.boxes = {}          # 路径 -> 勾选框控件
        self.meta_pdf = None     # 当前在边栏展示元数据的 PDF
        self.entries = []        # 最近一次扫描的完整结果
        self.keyword = ""        # 搜索关键词
        self.mode = library.DEFAULT_SEARCH_MODE      # 搜索方式
        self.sort_key = library.DEFAULT_SORT_KEY     # 排序字段
        self.sort_desc = library.SORT_DESC_DEFAULT[self.sort_key]   # 是否降序
        self.checked = set()     # 已勾选的路径（重建列表时据此还原勾选）
        self.info_cache = {}     # PDF 路径 -> read_pdf_info 结果（None 表示读不到）
        self.reading = False     # 是否正在后台读元数据
        self.sort_checks = {}    # 排序字段 -> 菜单项上的勾选标记

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
        self.count_text = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT)
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
            self._build_search_bar(),
            ft.Row([self._build_sort_menu(), self._build_order_button(),
                    self._build_reset_button(), self.count_text], spacing=8,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
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
        """重新扫描下载目录，并保留当前的搜索词与排序方式。"""
        try:
            self.entries = library.scan_library(self.base_dir)
        except OSError as exc:
            self.entries = []
            self.app.set_status(self.t("explorer_scan_failed", error=exc), COLOR_ERR)
        # 文件可能已被外部删除：把缓存与勾选收敛到现存项上
        alive = self._all_paths()
        self.info_cache = {path: value for path, value in self.info_cache.items()
                           if path in alive}
        self.checked &= alive
        if self.meta_pdf and self.meta_pdf not in alive:
            self.meta_pdf = None
        self._refresh_list()

    def _all_paths(self):
        """当前扫描结果里所有存在的路径（PDF 与图片文件夹）。"""
        paths = set()
        for entry in self.entries:
            paths.update(path for path in (entry["pdf"], entry["folder"]) if path)
        return paths

    # ------------------------------------------------------------------
    # 搜索栏与排序菜单（样式与探索页保持一致）
    # ------------------------------------------------------------------
    def _build_search_bar(self):
        """搜索栏：左侧选择搜索方式，中间输入关键词，右侧依次是清除与搜索按钮。

        与探索页的搜索栏同款：输入后点搜索按钮或按回车才过滤。
        """
        self.mode_dropdown = ft.Dropdown(
            value=self.mode, width=MODE_DROPDOWN_WIDTH, dense=True,
            border=ft.NoInputBorder(),
            options=[ft.dropdown.Option(key=key, text=self.t("explorer_mode_" + key))
                     for key in library.SEARCH_MODES],
            on_select=self._on_mode_change)
        self.search_field = ft.TextField(
            value=self.keyword, hint_text=self.t("explorer_search_hint"),
            expand=True, dense=True, border=ft.NoInputBorder(),
            on_submit=lambda e: self._apply_filter())
        # 叉号清空输入框与关键词，随即恢复完整列表
        self.btn_clear = ft.IconButton(ft.Icons.CLEAR, tooltip=self.t("btn_clear"),
                                       on_click=lambda e: self._on_clear_keyword())
        self.btn_search = ft.IconButton(ft.Icons.SEARCH, tooltip=self.t("btn_search"),
                                        on_click=lambda e: self._apply_filter())
        return ft.Container(
            content=ft.Row([self.mode_dropdown, self.search_field,
                            self.btn_clear, self.btn_search],
                           spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8, padding=ft.Padding.only(left=10, right=4, top=2, bottom=2))

    def _build_sort_menu(self):
        """排序菜单：名称 / 时间 / 大小 / 页数，当前字段右侧打勾。

        与探索页的排序菜单同构（同一档尺寸与展开方向）；升序 / 降序与取消排序
        由旁边的两个独立按钮控制，不放进菜单里。
        """
        self.sort_label = ft.Text(self._sort_label_text(), size=13, max_lines=1,
                                  text_align=ft.TextAlign.CENTER, expand=True,
                                  overflow=ft.TextOverflow.ELLIPSIS)
        self.sort_checks = {}
        items = [self._sort_item(key) for key in library.SORT_KEYS]
        self.sort_menu = ft.PopupMenuButton(
            content=ft.Row([self.sort_label, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18)],
                           spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            items=items,
            # 从按钮下边缘展开，避免菜单盖住按钮本身（与探索页一致）
            menu_position=ft.PopupMenuPosition.UNDER,
            padding=0,
        )
        return self._tool_box(self.sort_menu, SORT_BOX_WIDTH)

    def _build_order_button(self):
        """升序 / 降序按钮：图标显示当前方向，紧挨着排序菜单。"""
        self.order_btn = self._icon_box_button(self._order_icon(), self._order_tooltip(),
                                              self._toggle_sort_desc)
        return self._tool_box(self.order_btn, TOOL_HEIGHT, pad=ft.Padding.all(0))

    def _build_reset_button(self):
        """取消排序按钮：恢复默认排序（名称升序）。"""
        self.reset_btn = self._icon_box_button(ft.Icons.RESTART_ALT,
                                              self.t("explorer_sort_reset"),
                                              lambda e: self._reset_sort())
        return self._tool_box(self.reset_btn, TOOL_HEIGHT, pad=ft.Padding.all(0))

    @staticmethod
    def _icon_box_button(icon, tooltip, on_click):
        """小方框里的图标按钮：显式定尺寸并去掉自带内边距，保证图标居中。"""
        return ft.IconButton(icon=icon, icon_size=18, padding=0,
                             width=TOOL_HEIGHT, height=TOOL_HEIGHT,
                             tooltip=tooltip, on_click=on_click)

    def _tool_box(self, control, width, pad=None):
        """把控件包成与排序菜单同档的小方框（高度 / 描边 / 圆角一致）。

        图标按钮用 pad=0 单独指定：IconButton 自带内边距，容器再加一层会挤得装不下
        按钮本身，图标就偏到一边了。
        """
        return ft.Container(
            content=control, height=TOOL_HEIGHT, width=width,
            alignment=ft.Alignment.CENTER,
            padding=pad if pad is not None else ft.Padding.symmetric(horizontal=8),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=8)

    def _sort_item(self, key):
        """一个排序菜单项：名称在左、勾选标记在右（只有当前字段显示勾选）。"""
        check = ft.Icon(ft.Icons.CHECK, size=SORT_CHECK_SIZE,
                        visible=(key == self.sort_key))
        self.sort_checks[key] = check
        return ft.PopupMenuItem(content=self._menu_row(self.t("explorer_sort_" + key), check),
                                on_click=lambda e, k=key: self._select_sort(k))

    @staticmethod
    def _menu_row(label, trailing=None):
        """菜单项的统一行布局：固定宽度，保证各项文字左对齐、勾选都贴右端。"""
        controls = [ft.Text(label, size=13, max_lines=1, expand=True,
                            overflow=ft.TextOverflow.ELLIPSIS)]
        if trailing is not None:
            controls.append(trailing)
        return ft.Row(controls, spacing=4, width=SORT_ITEM_WIDTH,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _sort_label_text(self):
        """排序菜单按钮上显示的当前排序字段（升序 / 降序由旁边的按钮表示）。"""
        return self.t("explorer_sort_" + self.sort_key)

    def _order_icon(self):
        """当前排序方向的图标：降序向下、升序向上。"""
        return ft.Icons.ARROW_DOWNWARD if self.sort_desc else ft.Icons.ARROW_UPWARD

    def _order_tooltip(self):
        """方向按钮的提示：显示「点了会变成什么」，用户不必猜当前是升还是降。"""
        return self.t("explorer_order_to_asc" if self.sort_desc
                      else "explorer_order_to_desc")

    def _is_default_sort(self):
        """当前是否就是默认排序（名称升序）——取消排序按钮据此置灰。"""
        return (self.sort_key == library.DEFAULT_SORT_KEY
                and self.sort_desc == library.SORT_DESC_DEFAULT[self.sort_key])

    def _refresh_sort_controls(self):
        """把排序这几个控件的显示状态同步到当前排序。

        改动后立即生效，不必退出页面再进来；读取元数据期间统一置灰并显示提示文字。
        """
        self.sort_label.value = (self.t("explorer_reading") if self.reading
                                 else self._sort_label_text())
        self.order_btn.icon = self._order_icon()
        self.order_btn.tooltip = self._order_tooltip()
        self.order_btn.disabled = self.reading
        self.reset_btn.disabled = self.reading or self._is_default_sort()
        for key, check in self.sort_checks.items():
            check.visible = (key == self.sort_key)

    # ------------------------------------------------------------------
    # 搜索与排序的交互
    # ------------------------------------------------------------------
    def _on_mode_change(self, e):
        self.mode = self.mode_dropdown.value or library.DEFAULT_SEARCH_MODE
        self._refresh_list()

    def _apply_filter(self):
        """按输入框里的关键词过滤（点搜索按钮或按回车触发）。"""
        self.keyword = (self.search_field.value or "").strip()
        self._refresh_list()

    def _on_clear_keyword(self):
        """叉号：清空输入框与关键词，随即恢复完整列表。"""
        self.search_field.value = ""
        self._apply_filter()

    def _select_sort(self, key):
        if self.reading or key == self.sort_key:
            return
        self.sort_key = key
        # 换字段时套用该字段的默认方向（名称升序，其余降序）
        self.sort_desc = library.SORT_DESC_DEFAULT[key]
        self._refresh_list()

    def _toggle_sort_desc(self, e=None):
        if self.reading:
            return
        self.sort_desc = not self.sort_desc
        self._refresh_list()

    def _reset_sort(self):
        """取消排序：恢复默认的排序字段与方向（名称升序）。"""
        if self.reading or self._is_default_sort():
            return
        self.sort_key = library.DEFAULT_SORT_KEY
        self.sort_desc = library.SORT_DESC_DEFAULT[self.sort_key]
        self._refresh_list()

    def _refresh_list(self):
        """按当前搜索词与排序方式重建列表（纯内存操作，不重新扫盘）。"""
        self._refresh_sort_controls()
        if not self._ensure_info():
            return                       # 元数据还在读，读完会自动再刷新
        visible = library.sort_entries(
            library.filter_entries(self.entries, self.keyword, self.mode, self.info_cache),
            self.sort_key, self.sort_desc, self.info_cache)
        # 过滤后不可见的项必须取消勾选，否则「删除」会误伤看不见的项
        keep = {path for entry in visible for path in (entry["pdf"], entry["folder"]) if path}
        self.checked &= keep
        if self.meta_pdf and self.meta_pdf not in keep:
            self.meta_pdf = None
        self.boxes = {}
        self.list_view.controls = self._build_rows(visible)
        self.count_text.value = self._count_text(len(visible))
        self._refresh_panel()
        self._refresh_actions()
        self.app.update()

    def _count_text(self, shown):
        if self.keyword:
            return self.t("explorer_count_filtered", shown=shown, total=len(self.entries))
        return self.t("explorer_count", count=len(self.entries))

    def _needs_info(self):
        """是否需要 PDF 元数据：按作者 / 标签 / ID / 全部搜索，或按页数排序。"""
        if self.sort_key == "pages":
            return True
        return library.mode_needs_metadata(self.mode) and bool(self.keyword)

    def _ensure_info(self):
        """需要元数据时后台补读并缓存。

        已就绪返回 True；正在读取则返回 False（列表保持原样，读完自动再刷新一次）。
        """
        if self.reading:
            return False
        if not self._needs_info():
            return True
        missing = [entry["pdf"] for entry in self.entries
                   if entry["pdf"] and entry["pdf"] not in self.info_cache]
        if not missing:
            return True
        self.reading = True
        self._refresh_sort_controls()          # 先把界面切成「正在读取元数据…」
        self.app.update()
        self.app.page.run_thread(self._read_info_worker, missing)
        return False

    def _read_info_worker(self, paths):
        for path in paths:
            self.info_cache[path] = library.read_pdf_info(path)
        self.reading = False
        self._refresh_list()                   # 内部会同步排序控件的显示状态

    def _build_rows(self, entries):
        if not entries:
            # 区分「下载目录本来就是空的」和「只是没匹配上搜索条件」
            key = "explorer_empty" if not self.entries else "explorer_no_match"
            return [ft.Container(
                content=ft.Text(self.t(key), size=12,
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
        # 重建列表（搜索 / 排序）时按已勾选集合还原，排序不会把勾选弄丢
        checkbox = ft.Checkbox(value=path in self.checked, data=path,
                               on_change=self._on_check)
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
        if e.control.value:
            self.checked.add(path)
            if path.lower().endswith(library.PDF_SUFFIX):
                self.meta_pdf = path          # 勾选 PDF 即展示其元数据
        else:
            self.checked.discard(path)
            if path == self.meta_pdf:
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
