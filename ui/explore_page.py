# -*- coding: utf-8 -*-
"""探索页：按关键词（作品 / 作者 / 标签 / 角色）搜索本子，网格展示封面与名称。

- 每页展示 20 个结果，格子尺寸固定，按窗口宽度自动换行
- 点击封面放大查看（背景虚化变暗，右上角关闭）
- 点击名称进入本子详情页
- 结果上下各有一个翻页工具

本页实例由 :class:`AppUI` 缓存，因此从详情页返回时搜索结果仍然保留；
视图重建时通过 :meth:`ExplorePage._render` 依据页面状态还原。
"""

from concurrent.futures import ThreadPoolExecutor

import flet as ft

from core import explore
from core.constants import COLOR_ERR, COLOR_IDLE, COLOR_OK, ROUTE_EXPLORE, ROUTE_MAIN
from core.downloader import fetch_cover

# 单个格子的封面尺寸（3:4），尺寸固定以便按窗口宽度自动换行
COVER_WIDTH = 140
COVER_HEIGHT = 187
# 名称固定两行高度，保证同一排格子对齐
NAME_HEIGHT = 34

# 界面每页条数；库每页 80 条，因此 4 个界面页共用一个库页
PAGE_SIZE = 20
UI_PAGES_PER_LIB_PAGE = max(1, explore.LIB_PAGE_SIZE // PAGE_SIZE)

# 封面并发取图线程数（只在内存中，不落盘）
COVER_WORKERS = 8

# 搜索框整体宽度（居中显示）
SEARCH_BAR_WIDTH = 470

# 放大预览时背景的虚化强度
PREVIEW_BLUR = 6


class ExplorePage:
    def __init__(self, app):
        self.app = app
        self.client = None
        self.keyword = ""
        self.mode = explore.DEFAULT_MODE
        self.ui_page = 1
        self.total = 0
        self.items = []
        self.page_cache = {}       # 库页号 -> 该页条目列表（含已取到的封面字节）
        self.searching = False
        self.hint_value = app.t("explore_hint")
        self.hint_visible = True
        self.pagers = []           # 上下两个翻页工具，统一刷新
        # 控件引用在 build_view 里创建，先置空以便状态刷新方法始终可用
        self.hint_text = None
        self.grid = None
        self.overlay = None
        self.content_box = None
        self.btn_search = None

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    @property
    def total_pages(self):
        return max(1, -(-self.total // PAGE_SIZE))

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def build_view(self):
        app = self.app
        self.pagers = []
        self.status_text = ft.Text(app.status_text_value, size=12, color=app.status_color)
        self.hint_text = ft.Text(self.hint_value, size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.grid = ft.Row(wrap=True, spacing=12, run_spacing=12,
                           vertical_alignment=ft.CrossAxisAlignment.START)
        self.pager_top = self._build_pager()
        self.pager_bottom = self._build_pager()

        # 上下两个翻页工具都在滚动区内：从上方读完可用上面的翻页，滚到底可用下面的
        self.scroll_col = ft.Column([
            ft.Row([self._build_search_bar()], alignment=ft.MainAxisAlignment.CENTER),
            self.pager_top,
            self.hint_text,
            self.grid,
            self.pager_bottom,
            self.status_text,
        ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        self.content_box = ft.Container(content=self.scroll_col,
                                        left=0, top=0, right=0, bottom=0)
        self.overlay = self._build_overlay()

        view = ft.View(
            route=ROUTE_EXPLORE,
            appbar=ft.AppBar(
                title=ft.Text(self.t("explore_title")),
                leading=ft.IconButton(ft.Icons.ARROW_BACK,
                                      on_click=lambda e: app.navigate(ROUTE_MAIN)),
            ),
            controls=[ft.Stack([self.content_box, self.overlay], expand=True)],
            padding=12,
        )
        app.bind_status(self.status_text)
        self._render()
        return view

    def _build_search_bar(self):
        """搜索框：左侧选择搜索方式，中间输入关键词，右侧搜索按钮。"""
        self.mode_dropdown = ft.Dropdown(
            value=self.mode, width=104, dense=True, border=ft.NoInputBorder(),
            options=[ft.dropdown.Option(key=key, text=self.t("explore_mode_" + key))
                     for key in explore.SEARCH_MODES],
            on_select=self._on_mode_change)
        self.keyword_field = ft.TextField(
            value=self.keyword, hint_text=self.t("explore_search_hint"),
            expand=True, dense=True, border=ft.NoInputBorder(),
            on_submit=lambda e: self.search())
        self.btn_search = ft.IconButton(ft.Icons.SEARCH, tooltip=self.t("btn_search"),
                                        disabled=self.searching, on_click=lambda e: self.search())
        return ft.Container(
            content=ft.Row([self.mode_dropdown, self.keyword_field, self.btn_search],
                           spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            width=SEARCH_BAR_WIDTH, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8, padding=ft.Padding.only(left=10, right=4, top=2, bottom=2))

    def _build_pager(self):
        prev_btn = ft.Button(self.t("btn_prev_page"), icon=ft.Icons.CHEVRON_LEFT,
                             on_click=lambda e: self.goto_page(self.ui_page - 1))
        next_btn = ft.Button(self.t("btn_next_page"), icon=ft.Icons.CHEVRON_RIGHT,
                             on_click=lambda e: self.goto_page(self.ui_page + 1))
        label = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        row = ft.Row([prev_btn, label, next_btn], spacing=8,
                     alignment=ft.MainAxisAlignment.CENTER, visible=False)
        self.pagers.append((row, prev_btn, label, next_btn))
        return row

    def _build_overlay(self):
        """封面放大层：背景虚化变暗，右上方关闭按钮。

        图片控件在打开预览时才创建：Image 的 src 不能为空，否则会触发客户端校验错误。
        """
        self.preview_holder = ft.Container(alignment=ft.Alignment.CENTER, expand=True)
        close_btn = ft.IconButton(ft.Icons.CLOSE, icon_size=28,
                                  tooltip=self.t("btn_close"),
                                  on_click=lambda e: self._close_preview())
        return ft.Container(
            visible=False, left=0, top=0, right=0, bottom=0, padding=16,
            bgcolor=ft.Colors.with_opacity(0.78, ft.Colors.BLACK),
            content=ft.Column([
                ft.Row([close_btn], alignment=ft.MainAxisAlignment.END),
                self.preview_holder,
            ], spacing=0, expand=True))

    def _tile(self, item):
        cover = item.get("cover")
        if cover:
            cover_control = ft.Image(src=cover, width=COVER_WIDTH, height=COVER_HEIGHT,
                                     fit=ft.BoxFit.COVER, border_radius=4)
        else:
            cover_control = ft.Container(
                width=COVER_WIDTH, height=COVER_HEIGHT, border_radius=4,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(ft.Icons.BROKEN_IMAGE, size=24,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                tooltip=self.t("cover_load_failed")))
        return ft.Column([
            # 用 GestureDetector 承载点击与手型光标：Container 没有 mouse_cursor 参数
            ft.GestureDetector(content=cover_control, mouse_cursor=ft.MouseCursor.CLICK,
                               on_tap=lambda e: self._open_preview(item)),
            ft.GestureDetector(
                content=ft.Container(
                    content=ft.Text(item["name"], size=12, max_lines=2,
                                    tooltip=item["name"] or None,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                    width=COVER_WIDTH, height=NAME_HEIGHT),
                mouse_cursor=ft.MouseCursor.CLICK,
                on_tap=lambda e: self.app.open_album(item["id"])),
        ], width=COVER_WIDTH, spacing=6, alignment=ft.MainAxisAlignment.START)

    def _render(self):
        """按当前状态刷新提示、网格与翻页控件（视图重建后也用它还原）。"""
        if self.hint_text is not None:
            self.hint_text.value = self.hint_value
            self.hint_text.visible = self.hint_visible
        if self.grid is not None:
            self.grid.controls = [self._tile(item) for item in self.items]
        self._refresh_pager()

    # ------------------------------------------------------------------
    # 搜索与翻页
    # ------------------------------------------------------------------
    def search(self):
        """按输入框内容重新搜索（回到第 1 页）。"""
        if self.searching:
            return
        keyword = (self.keyword_field.value or "").strip()
        if not keyword:
            self.app.set_status(self.t("status_search_need_keyword"), COLOR_ERR)
            return
        self.keyword = keyword
        self.mode = self.mode_dropdown.value or explore.DEFAULT_MODE
        self.page_cache = {}
        self.total = 0
        self.ui_page = 1
        self._start_load()

    def goto_page(self, page):
        """翻页：沿用上一次搜索的关键词与方式。"""
        if self.searching or not self.keyword:
            return
        page = max(1, min(self.total_pages, page))
        if page == self.ui_page and self.items:
            return
        self.ui_page = page
        self._start_load()

    def _on_mode_change(self, e):
        self.mode = self.mode_dropdown.value or explore.DEFAULT_MODE

    def _start_load(self):
        self.searching = True
        self.items = []
        self.hint_value = self.t("status_searching")
        self.hint_visible = True
        if self.btn_search is not None:
            self.btn_search.disabled = True
        self._render()
        self.app.set_status(self.t("status_searching"))
        self.app.page.run_thread(self._worker)

    def _worker(self):
        error = None
        try:
            lib_page = (self.ui_page - 1) // UI_PAGES_PER_LIB_PAGE + 1
            items = self.page_cache.get(lib_page)
            if items is None:
                if self.client is None:
                    self.client = explore.new_client(self.app.conf)
                page = explore.search(self.client, self.mode, self.keyword, lib_page)
                items = explore.to_items(page)
                self.total = int(page.total or 0)
                # 只保留最近两个库页，避免把封面字节一直堆在内存里
                self.page_cache[lib_page] = items
                while len(self.page_cache) > 2:
                    self.page_cache.pop(next(iter(self.page_cache)))
            offset = ((self.ui_page - 1) % UI_PAGES_PER_LIB_PAGE) * PAGE_SIZE
            self.items = items[offset:offset + PAGE_SIZE]
            self._load_covers(self.items)
        except Exception as exc:
            error = exc
            self.items = []
        if error is not None:
            self.hint_value = self.t("explore_search_failed", error=error)
            self.hint_visible = True
        elif not self.items:
            self.hint_value = self.t("explore_no_result")
            self.hint_visible = True
        else:
            self.hint_visible = False
        self.searching = False
        if self.btn_search is not None:
            self.btn_search.disabled = False
        # 先渲染再报状态：界面构建出错时状态栏不能谎报「完成」
        try:
            self._render()
        except Exception as exc:
            self.grid.controls = []
            self.hint_value = self.t("explore_search_failed", error=exc)
            self.hint_visible = True
            self.hint_text.value = self.hint_value
            self.hint_text.visible = True
            self.app.set_status(self.t("status_search_failed"), COLOR_ERR)
        else:
            if error is not None:
                self.app.set_status(self.t("status_search_failed"), COLOR_ERR)
            elif self.items:
                self.app.set_status(self.t("status_search_done"), COLOR_OK)
            else:
                self.app.set_status(self.t("status_search_done"), COLOR_IDLE)
        self.app.update()

    @staticmethod
    def _load_covers(items):
        """并发取封面图字节（只在内存中，不落盘）；取不到的项保持 None。"""
        pending = [item for item in items if not item.get("cover")]
        if not pending:
            return
        with ThreadPoolExecutor(max_workers=COVER_WORKERS) as pool:
            covers = list(pool.map(lambda item: fetch_cover(item["id"]), pending))
        for item, cover in zip(pending, covers):
            item["cover"] = cover

    def _refresh_pager(self):
        show = bool(self.keyword) and self.total > 0
        total_pages = self.total_pages
        label = self.t("explore_page_info", page=self.ui_page,
                       pages=total_pages, total=self.total)
        for row, prev_btn, label_text, next_btn in self.pagers:
            row.visible = show
            label_text.value = label
            prev_btn.disabled = self.searching or self.ui_page <= 1
            next_btn.disabled = self.searching or self.ui_page >= total_pages

    # ------------------------------------------------------------------
    # 封面放大
    # ------------------------------------------------------------------
    def _open_preview(self, item):
        cover = item.get("cover")
        if not cover or self.overlay is None:
            return
        self.preview_holder.content = ft.Image(src=cover, fit=ft.BoxFit.CONTAIN, expand=True)
        self.overlay.visible = True
        self.content_box.blur = PREVIEW_BLUR
        self.app.update()

    def _close_preview(self):
        self.overlay.visible = False
        self.content_box.blur = None
        self.preview_holder.content = None
        self.app.update()
