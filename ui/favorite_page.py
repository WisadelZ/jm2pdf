# -*- coding: utf-8 -*-
"""收藏列表页：网格展示账号的收藏，可按收藏夹筛选。

交互与探索页的搜索结果一致：点封面放大查看、点名称进入本子详情、上下各有一个
翻页工具；区别是把「搜索框 + 排序菜单」换成了「收藏夹筛选菜单」（全部 / 指定
收藏夹），菜单与上方翻页按钮同排。

本页实例由 :class:`AppUI` 缓存，因此从本子详情页返回时页码、筛选与列表都仍然保留。
"""

import flet as ft

from core import explore, favorite
from core.constants import (COLOR_ERR, COLOR_IDLE, COLOR_OK, ROUTE_ACCOUNT,
                            ROUTE_FAVORITE)
from core.downloader import fetch_covers

# 单个格子的封面尺寸（3:4），尺寸固定以便按窗口宽度自动换行
COVER_WIDTH = 140
COVER_HEIGHT = 187
# 名称固定两行高度，保证同一排格子对齐
NAME_HEIGHT = 34

# 界面每页条数（收藏接口每页也是 20 条，两边一致）
PAGE_SIZE = favorite.LIB_PAGE_SIZE

# 顶部一排控件的统一高度：翻页按钮与收藏夹菜单按它对齐
TOOL_HEIGHT = 40
# 收藏夹菜单与翻页按钮之间的间距（两者同排、整体居中）
FOLDER_GAP = 32
# 收藏夹菜单按钮宽度：只够放下几个字的状态名，过长省略
FOLDER_BOX_WIDTH = 110
# 收藏夹菜单项的固定宽度与勾选标记尺寸：名称贴左、勾选贴右
FOLDER_ITEM_WIDTH = 130
FOLDER_CHECK_SIZE = 15

# 放大预览时背景的虚化强度
PREVIEW_BLUR = 6


class FavoritePage:
    def __init__(self, app):
        self.app = app
        self.client = None
        self.ui_page = 1
        self.total = 0
        self.items = []
        self.folders = []            # [(fid, name), ...]，进入页面时随列表一起取到
        self.folder_id = favorite.FOLDER_ALL
        self.folder_name = ""
        self.loading = False
        self.loaded = False          # 已成功加载过：重建视图时不再重复请求
        self.load_epoch = 0          # 加载序号：离开页面后作废还在跑的请求
        self.pagers = []
        self.folder_checks = {}
        # 提示语只记文本键与参数，取词放到 hint_value 里做：
        # 本页实例被 AppUI 缓存，若在这里就存成字符串，切换语言后会一直显示旧语言
        self.hint_key = None
        self.hint_args = {}
        self.hint_visible = False
        # 控件引用在 build_view 里创建，先置空以便状态刷新方法始终可用
        self.hint_text = None
        self.grid = None
        self.overlay = None
        self.preview_holder = None
        self.content_box = None
        self.status_text = None
        self.folder_label = None
        self.folder_menu = None
        self.folder_box = None
        self.pager_top = None
        self.pager_bottom = None

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    @property
    def total_pages(self):
        return max(1, -(-self.total // PAGE_SIZE))

    @property
    def hint_value(self):
        """当前提示语：每次都按当前语言取词，避免缓存住切换前的旧语言文本。"""
        if self.hint_key is None:
            return ""
        return self.t(self.hint_key, **self.hint_args)

    def _set_hint(self, key, **kwargs):
        """记录提示语的文本键与参数（实际取词在 :attr:`hint_value` 里做）。"""
        self.hint_key = key
        self.hint_args = kwargs

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def build_view(self):
        app = self.app
        self.pagers = []
        self.status_text = ft.Text(app.status_text_value, size=12, color=app.status_color)
        self.hint_text = ft.Text(self.hint_value, size=12,
                                 color=ft.Colors.ON_SURFACE_VARIANT)
        self.grid = ft.Row(wrap=True, spacing=12, run_spacing=12,
                           vertical_alignment=ft.CrossAxisAlignment.START)
        # 收藏夹菜单与上方翻页按钮同排，先建好再交给 _build_pager
        self.folder_box = self._build_folder_menu()
        self.pager_top = self._build_pager((self.folder_box,))
        self.pager_bottom = self._build_pager()

        self.body = ft.Column([
            self.pager_top,
            self._centered(self.hint_text),
            self.grid,
            self.pager_bottom,
            self._centered(self.status_text),
        ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)

        # 内容整块模糊变暗由放大预览层控制，因此包一层容器叠在预览层下面
        self.content_box = ft.Container(content=self.body,
                                        left=0, top=0, right=0, bottom=0)
        self.overlay = self._build_overlay()

        view = ft.View(
            route=ROUTE_FAVORITE,
            appbar=ft.AppBar(
                title=ft.Text(self.t("favorite_title")),
                leading=ft.IconButton(ft.Icons.ARROW_BACK,
                                      on_click=lambda e: app.navigate(ROUTE_ACCOUNT)),
            ),
            controls=[ft.Stack([self.content_box, self.overlay], expand=True)],
            padding=12,
        )
        app.bind_status(self.status_text)
        self._refresh_folder_menu()
        if self.loaded or self.loading:
            self._render()
        else:
            self._start_load()
        return view

    @staticmethod
    def _centered(control):
        """把控件包进占满宽度的 Row 里水平居中。"""
        return ft.Row([control], alignment=ft.MainAxisAlignment.CENTER)

    def _build_pager(self, extra_controls=()):
        """翻页工具：[上一页] 页码 [下一页]；extra_controls 与它们同排、整体居中。"""
        prev_btn = ft.Button(self.t("btn_prev_page"), icon=ft.Icons.CHEVRON_LEFT,
                             height=TOOL_HEIGHT,
                             on_click=lambda e: self.goto_page(self.ui_page - 1))
        next_btn = ft.Button(self.t("btn_next_page"), icon=ft.Icons.CHEVRON_RIGHT,
                             height=TOOL_HEIGHT,
                             on_click=lambda e: self.goto_page(self.ui_page + 1))
        label = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        controls = [prev_btn, label, next_btn]
        if extra_controls:
            # 收藏夹菜单与翻页按钮之间留一段固定的距离，两者既分开又整体居中
            controls.append(ft.Container(width=FOLDER_GAP))
            controls.extend(extra_controls)
        row = ft.Row(controls, spacing=8, alignment=ft.MainAxisAlignment.CENTER,
                     vertical_alignment=ft.CrossAxisAlignment.CENTER, visible=False)
        self.pagers.append((row, prev_btn, label, next_btn))
        return row

    def _build_folder_menu(self):
        """收藏夹筛选菜单：全部 / 各收藏夹，当前项打勾。

        与探索页的排序菜单同规格：固定高度的按钮，菜单从按钮下边缘展开；
        收藏夹较多时由客户端自行限高并支持滚轮滑动。
        """
        self.folder_label = ft.Text(self.folder_text(), size=13, max_lines=1,
                                    text_align=ft.TextAlign.CENTER, expand=True,
                                    overflow=ft.TextOverflow.ELLIPSIS)
        self.folder_menu = ft.PopupMenuButton(
            content=ft.Row([self.folder_label, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18)],
                           spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            items=[],
            menu_position=ft.PopupMenuPosition.UNDER,
            padding=0,
        )
        return ft.Container(
            content=self.folder_menu, height=TOOL_HEIGHT, width=FOLDER_BOX_WIDTH,
            alignment=ft.Alignment.CENTER, padding=ft.Padding.symmetric(horizontal=8),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=8)

    def folder_text(self):
        """按钮上显示的状态名：当前筛选的收藏夹名，未筛选时为「全部」。"""
        return self.folder_name or self.t("favorite_folder_all")

    def _folder_item(self, folder_id, name):
        """一个收藏夹菜单项：名称在左、勾选标记在右（只有当前项显示勾选）。"""
        check = ft.Icon(ft.Icons.CHECK, size=FOLDER_CHECK_SIZE,
                        visible=(folder_id == self.folder_id))
        self.folder_checks[folder_id] = check
        return ft.PopupMenuItem(
            content=self._menu_row(name, check),
            on_click=lambda e, f=folder_id, n=name: self.select_folder(f, n))

    @staticmethod
    def _menu_row(label, trailing=None):
        """菜单项的统一行布局：固定宽度，保证各项文字左对齐、勾选都贴右端。"""
        controls = [ft.Text(label, size=13, max_lines=1, expand=True,
                            overflow=ft.TextOverflow.ELLIPSIS)]
        if trailing is not None:
            controls.append(trailing)
        return ft.Row(controls, spacing=4, width=FOLDER_ITEM_WIDTH,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _refresh_folder_menu(self):
        """按最新拿到的收藏夹列表重建菜单，并刷新按钮上的状态名。"""
        options = [(favorite.FOLDER_ALL, self.t("favorite_folder_all"))] + list(self.folders)
        self.folder_checks = {}
        self.folder_menu.items = [self._folder_item(fid, name) for fid, name in options]
        self.folder_label.value = self.folder_text()

    def select_folder(self, folder_id, name):
        """切换筛选的收藏夹：回到第 1 页重新加载。"""
        if self.loading or folder_id == self.folder_id:
            return
        self.folder_id = folder_id
        self.folder_name = "" if folder_id == favorite.FOLDER_ALL else name
        self.folder_label.value = self.folder_text()
        for fid, check in self.folder_checks.items():
            check.visible = (fid == folder_id)
        self.ui_page = 1
        self._start_load()

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
    # 加载与翻页
    # ------------------------------------------------------------------
    def goto_page(self, page):
        if self.loading:
            return
        page = max(1, min(self.total_pages, page))
        if page == self.ui_page and self.items:
            return
        self.ui_page = page
        self._start_load()

    def _start_load(self):
        self.loading = True
        self.load_epoch += 1
        epoch = self.load_epoch
        self.items = []
        self._set_hint("favorite_loading")
        self.hint_visible = True
        self._render()
        self.app.set_status(self.t("favorite_loading"))
        self.app.page.run_thread(self._worker, epoch)

    def _worker(self, epoch):
        error = None
        try:
            if self.client is None:
                self.client = favorite.new_client(self.app.conf)
            page = favorite.fetch_page(self.client, self.ui_page, self.folder_id)
            self.folders = favorite.folders_of(page)
            items = explore.to_items(page)
            self.total = int(page.total or 0)
            fetch_covers(items)
            self.items = items
        except Exception as exc:
            error = exc
            self.items = []
        if epoch != self.load_epoch:
            # 请求期间用户已切换筛选或离开页面：本次结果作废
            return
        if error is not None:
            self._set_hint("favorite_load_failed", error=error)
            self.hint_visible = True
        elif not self.items:
            self._set_hint("favorite_empty")
            self.hint_visible = True
        else:
            self.hint_visible = False
            self.loaded = True
        self.loading = False
        # 先渲染再报状态：界面构建出错时状态栏不能谎报「完成」
        try:
            self._refresh_folder_menu()
            self._render()
        except Exception as exc:
            self.grid.controls = []
            self._set_hint("favorite_load_failed", error=exc)
            self.hint_visible = True
            self.hint_text.value = self.hint_value
            self.hint_text.visible = True
            self.app.set_status(self.t("favorite_load_failed", error=exc), COLOR_ERR)
        else:
            if error is not None:
                self.app.set_status(self.t("status_favorite_failed"), COLOR_ERR)
            elif self.items:
                self.app.set_status(self.t("status_favorite_loaded"), COLOR_OK)
            else:
                self.app.set_status(self.t("status_favorite_loaded"), COLOR_IDLE)
        self.app.update()

    def _refresh_pager(self):
        """翻页与收藏夹菜单一起出现；筛选后没有结果时仍保留菜单，便于切回全部。"""
        total_pages = self.total_pages
        label = self.t("explore_page_info", page=self.ui_page,
                       pages=total_pages, total=self.total)
        for row, prev_btn, label_text, next_btn in self.pagers:
            if row is self.pager_top:
                # 上方那排带收藏夹菜单：即使当前筛选没有结果也要留着，否则无法切回
                row.visible = self.total > 0 or bool(self.folders)
            else:
                row.visible = self.total > 0
            label_text.value = label
            prev_btn.disabled = self.loading or self.ui_page <= 1
            next_btn.disabled = self.loading or self.ui_page >= total_pages

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
