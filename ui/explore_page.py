# -*- coding: utf-8 -*-
"""探索页（程序首页）：按关键词（作品 / 作者 / 标签 / 角色）搜索本子，网格展示封面与名称。

- 每页展示 20 个结果，格子尺寸固定，按窗口宽度自动换行
- 点击封面放大查看（背景虚化变暗，右上角关闭）
- 点击名称进入本子详情页
- 结果上下各有一个翻页工具

布局分两态，由「首次点击搜索」这一动作触发一次切换，之后不再变化：

- 居中态（启动时）：菜单栏与搜索区之间留白，欢迎语 + 搜索框 + 指引整体垂直居中
- 置顶态（首次搜索后，与搜索结果无关）：搜索框紧贴菜单栏下方，下方为翻页与结果网格

本页实例由 :class:`AppUI` 缓存，因此从详情页返回时搜索结果仍然保留；
视图重建时通过 :meth:`ExplorePage._render` 与 :meth:`ExplorePage._apply_layout`
依据页面状态还原。
"""

import flet as ft

from core import explore
from core.constants import (COLOR_ERR, COLOR_IDLE, COLOR_OK, ROUTE_ACCOUNT, ROUTE_DOWNLOAD,
                            ROUTE_EXPLORER, ROUTE_HELP, ROUTE_MAIN, ROUTE_SETTINGS)
from core.downloader import fetch_covers

# 单个格子的封面尺寸（3:4），尺寸固定以便按窗口宽度自动换行
COVER_WIDTH = 140
COVER_HEIGHT = 187
# 名称固定两行高度，保证同一排格子对齐
NAME_HEIGHT = 34

# 界面每页条数；库每页 80 条，因此 4 个界面页共用一个库页
PAGE_SIZE = 20
UI_PAGES_PER_LIB_PAGE = max(1, explore.LIB_PAGE_SIZE // PAGE_SIZE)

# 搜索框整体宽度（居中显示）
SEARCH_BAR_WIDTH = 470

# 顶部翻页按钮与排序菜单之间的间距（两者同排、整体居中）
SORT_GAP = 32

# 顶部一排控件的统一高度：翻页按钮与排序菜单按它对齐
TOOL_HEIGHT = 40

# 排序菜单按钮宽度：只够放下 2~3 个字的状态名（排序方式或时间筛选方式）
SORT_BOX_WIDTH = 84

# 排序菜单项的固定宽度与勾选标记尺寸：五项两端对齐（名称贴左、勾选贴右）
SORT_ITEM_WIDTH = 110
SORT_CHECK_SIZE = 15

# 「按日期筛选」窗口的固定尺寸：只包住标题、四个选项与两个按钮，
# 上下左右都按内容限制，且不随主窗口变化
DATE_DIALOG_WIDTH = 150
DATE_DIALOG_HEIGHT = 192

# 放大预览时背景的虚化强度
PREVIEW_BLUR = 6

# 首页欢迎语：居中态显示在搜索框上方，字号略大于正文
WELCOME_FONT_SIZE = 25
# 欢迎语与下方搜索框之间额外留出的间距（外层 Column 本身还有一个间距）
WELCOME_GAP = 10


class ExplorePage:
    def __init__(self, app):
        self.app = app
        self.client = None
        self.keyword = ""
        self.mode = explore.DEFAULT_MODE
        self.sort = explore.DEFAULT_SORT
        self.time = explore.DEFAULT_TIME
        self.ui_page = 1
        self.total = 0
        self.items = []
        self.page_cache = {}       # 库页号 -> 该页条目列表（含已取到的封面字节）
        self.searching = False
        self.searched_once = False  # 是否已发起过首次搜索：决定搜索区居中还是置顶
        self.load_epoch = 0         # 加载序号：点「返回」后用它作废还在跑的搜索
        # 提示语只记文本键与参数，取词放到 hint_value 里做：
        # 本页实例被 AppUI 缓存，若在这里就存成字符串，切换语言后会一直显示旧语言
        self.hint_key = "explore_hint"
        self.hint_args = {}
        self.hint_visible = True
        self.pagers = []           # 上下两个翻页工具，统一刷新
        # 控件引用在 build_view 里创建，先置空以便状态刷新方法始终可用
        self.hint_text = None
        self.grid = None
        self.overlay = None
        self.content_box = None
        self.btn_search = None
        self.btn_back = None
        self.back_wrap = None
        self.btn_clear = None
        self.sort_box = None
        self.sort_menu = None
        self.sort_label = None
        self.sort_checks = {}
        self.toolbar = None
        self.body = None
        self.search_wrap = None
        self.welcome_text = None
        self.welcome_wrap = None
        self.hint_wrap = None
        self.status_wrap = None
        self.spacer_top = None
        self.spacer_bottom = None

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    @property
    def total_pages(self):
        return max(1, -(-self.total // PAGE_SIZE))

    @property
    def hint_value(self):
        """当前提示语：每次都按当前语言取词，避免缓存住切换前的旧语言文本。"""
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
        self.hint_text = ft.Text(self.hint_value, size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.grid = ft.Row(wrap=True, spacing=12, run_spacing=12,
                           vertical_alignment=ft.CrossAxisAlignment.START)
        # 排序菜单与顶部翻页按钮同排，先建好再交给 _build_pager
        self.sort_box = self._build_sort_menu()
        self.pager_top = self._build_pager((self.sort_box,))
        self.pager_bottom = self._build_pager()

        # 顶栏菜单：首位是下载页入口（原下载页「探索」按钮所在的位置）
        self.toolbar = ft.Column([self._build_toolbar(), ft.Divider(height=1)], spacing=8)
        # 欢迎语、搜索框、指引与状态各自包一层居中 Row，居中态下水平对齐由它保证
        self.welcome_text = ft.Text(self.t("home_welcome"), size=WELCOME_FONT_SIZE)
        # 底部留出额外间距，让欢迎语与搜索框之间不那么挤
        self.welcome_wrap = self._centered(
            ft.Container(content=self.welcome_text,
                         padding=ft.Padding.only(bottom=WELCOME_GAP)))
        # 返回按钮独占一行靠左上，这样搜索框那一行仍是纯居中、不会被按钮挤偏
        self.btn_back = ft.IconButton(ft.Icons.ARROW_BACK, tooltip=self.t("btn_back"),
                                      visible=False, on_click=lambda e: self.reset_search())
        self.back_wrap = ft.Row([self.btn_back], alignment=ft.MainAxisAlignment.START)
        self.search_wrap = self._centered(self._build_search_bar())
        self.hint_wrap = self._centered(self.hint_text)
        self.status_wrap = self._centered(self.status_text)
        # 居中态用的上下弹性留白：置顶态下不进入控件树，因此不会占位
        self.spacer_top = ft.Container(expand=True)
        self.spacer_bottom = ft.Container(expand=True)

        # 控件顺序由 _apply_layout 按状态排列，这里只建容器
        self.body = ft.Column(spacing=12, expand=True)
        self.content_box = ft.Container(content=self.body,
                                        left=0, top=0, right=0, bottom=0)
        self.overlay = self._build_overlay()
        self._apply_layout()

        view = ft.View(
            route=ROUTE_MAIN,
            controls=[ft.Stack([self.content_box, self.overlay], expand=True)],
            padding=12,
        )
        app.bind_status(self.status_text)
        self._render()
        return view

    @staticmethod
    def _centered(control):
        """把控件包进占满宽度的 Row 里水平居中（Column 的交叉轴对齐保持默认）。"""
        return ft.Row([control], alignment=ft.MainAxisAlignment.CENTER)

    def _build_toolbar(self):
        """顶栏菜单：下载 / 账号 / 资源管理器 / 帮助 / 设置。"""
        app = self.app
        return ft.Row([
            ft.OutlinedButton(self.t("btn_download"), icon=ft.Icons.DOWNLOAD,
                              on_click=lambda e: app.navigate(ROUTE_DOWNLOAD)),
            ft.OutlinedButton(self.t("btn_account"), icon=ft.Icons.PERSON_OUTLINE,
                              on_click=lambda e: app.navigate(ROUTE_ACCOUNT)),
            ft.OutlinedButton(self.t("btn_explorer"), icon=ft.Icons.FOLDER_OPEN,
                              on_click=lambda e: app.navigate(ROUTE_EXPLORER)),
            ft.OutlinedButton(self.t("btn_help"), icon=ft.Icons.HELP_OUTLINE,
                              on_click=lambda e: app.navigate(ROUTE_HELP)),
            ft.OutlinedButton(self.t("btn_settings"), icon=ft.Icons.SETTINGS,
                              on_click=lambda e: app.navigate(ROUTE_SETTINGS)),
        ], spacing=8, alignment=ft.MainAxisAlignment.START)

    def _apply_layout(self):
        """按「是否已发起过首次搜索」排列控件顺序与滚动方式（控件实例始终不变）。

        居中态用上下两个弹性留白把欢迎语 / 搜索框 / 指引一起推到窗口中央；
        置顶态改为可滚动，并收起留白与欢迎语，把返回按钮与搜索框移到菜单栏下方。
        """
        self.btn_back.visible = self.searched_once
        if self.searched_once:
            self.body.scroll = ft.ScrollMode.AUTO
            self.body.controls = [self.toolbar, self.back_wrap, self.search_wrap,
                                  self.pager_top, self.hint_wrap, self.grid,
                                  self.pager_bottom, self.status_wrap]
        else:
            self.body.scroll = None
            self.body.controls = [self.toolbar, self.spacer_top, self.welcome_wrap,
                                  self.search_wrap, self.hint_wrap, self.status_wrap,
                                  self.spacer_bottom]

    def _build_search_bar(self):
        """搜索框：左侧选择搜索方式，中间输入关键词，右侧依次是清除关键词与搜索按钮。"""
        self.mode_dropdown = ft.Dropdown(
            value=self.mode, width=104, dense=True, border=ft.NoInputBorder(),
            options=[ft.dropdown.Option(key=key, text=self.t("explore_mode_" + key))
                     for key in explore.SEARCH_MODES],
            on_select=self._on_mode_change)
        self.keyword_field = ft.TextField(
            value=self.keyword, hint_text=self.t("explore_search_hint"),
            expand=True, dense=True, border=ft.NoInputBorder(),
            on_submit=lambda e: self.search())
        # 叉号只清输入框，不动已经出来的结果
        self.btn_clear = ft.IconButton(ft.Icons.CLEAR, tooltip=self.t("btn_clear"),
                                       on_click=lambda e: self._on_clear_keyword())
        self.btn_search = ft.IconButton(ft.Icons.SEARCH, tooltip=self.t("btn_search"),
                                        disabled=self.searching, on_click=lambda e: self.search())
        return ft.Container(
            content=ft.Row([self.mode_dropdown, self.keyword_field,
                            self.btn_clear, self.btn_search],
                           spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            width=SEARCH_BAR_WIDTH, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8, padding=ft.Padding.only(left=10, right=4, top=2, bottom=2))

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
            # 排序菜单与翻页按钮之间留一段固定的距离，两者既分开又整体居中
            controls.append(ft.Container(width=SORT_GAP))
            controls.extend(extra_controls)
        # 整体居中：两端留白由 alignment 处理，不用换行（换行会破坏居中）
        row = ft.Row(controls, spacing=8, alignment=ft.MainAxisAlignment.CENTER,
                     vertical_alignment=ft.CrossAxisAlignment.CENTER, visible=False)
        self.pagers.append((row, prev_btn, label, next_btn))
        return row

    def _build_sort_menu(self):
        """排序菜单：最新 / 观看数 / 图片数 / 点赞数，末尾是「按日期筛选」入口。

        用弹出式菜单按钮而不是下拉框：按钮上要显示的状态既可能是排序方式
        （未筛选时），也可能是时间筛选方式（已筛选时），文字与箭头的位置都要自己控制。
        菜单项做成固定宽度的行：左端是名称、右端是勾选标记，五项两端都对齐；
        勾选标在当前排序方式上 —— 按钮显示时间筛选方式时，也能看出它基于哪种排序。
        """
        # 文字在左侧剩余空间里居中，箭头贴右侧，两者垂直居中
        self.sort_label = ft.Text(self.sort_label_text(), size=13, max_lines=1,
                                  text_align=ft.TextAlign.CENTER, expand=True,
                                  overflow=ft.TextOverflow.ELLIPSIS)
        self.sort_checks = {}
        items = [self._sort_item(key) for key in explore.SORT_MODES]
        items.append(ft.PopupMenuItem(
            content=self._menu_row(self.t("explore_sort_date")),
            on_click=lambda e: self.open_date_dialog()))
        self.sort_menu = ft.PopupMenuButton(
            content=ft.Row([self.sort_label, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18)],
                           spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            items=items,
            # 从按钮下边缘展开，避免菜单盖住按钮本身（默认 OVER 会浮在按钮上）
            menu_position=ft.PopupMenuPosition.UNDER,
            # 注意：bgcolor 指的是「弹出菜单」的底色，不能设成透明，否则菜单会浮在结果图上；
            # 按钮自身不需要底色（外层容器已经有边框）。
            padding=0,
        )
        # 外层容器固定成与翻页按钮相同的高度，两者在那一排里上下对齐
        return ft.Container(
            content=self.sort_menu, height=TOOL_HEIGHT, width=SORT_BOX_WIDTH,
            alignment=ft.Alignment.CENTER, padding=ft.Padding.symmetric(horizontal=8),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=8)

    def _sort_item(self, key):
        """一个排序菜单项：名称在左、勾选标记在右（只有当前排序显示勾选）。"""
        check = ft.Icon(ft.Icons.CHECK, size=SORT_CHECK_SIZE, visible=(key == self.sort))
        self.sort_checks[key] = check
        return ft.PopupMenuItem(content=self._menu_row(self.t("explore_sort_" + key), check),
                                on_click=lambda e, k=key: self.select_sort(k))

    @staticmethod
    def _menu_row(label, trailing=None):
        """菜单项的统一行布局：固定宽度，保证各项文字左对齐、勾选都贴右端。"""
        controls = [ft.Text(label, size=13, max_lines=1, expand=True,
                            overflow=ft.TextOverflow.ELLIPSIS)]
        if trailing is not None:
            controls.append(trailing)
        return ft.Row(controls, spacing=4, width=SORT_ITEM_WIDTH,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def sort_label_text(self):
        """按钮上显示的状态：设了时间筛选就显示筛选方式，否则显示排序方式。"""
        if self.time != explore.DEFAULT_TIME:
            return self.t("explore_time_" + self.time)
        return self.t("explore_sort_" + self.sort)

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

    def select_sort(self, key):
        """选择排序方式：与「按日期筛选」互斥，换排序即取消时间筛选。

        时间筛选只在「最新」排序下有意义（其它排序配时间筛选会失去筛选意义），
        所以两者解绑：选了排序就不保留时间筛选，选了时间筛选则排序固定用「最新」。
        """
        self.sort = key or explore.DEFAULT_SORT
        self.time = explore.DEFAULT_TIME
        self._refresh_sort_label()
        self.reload_from_first_page()

    def _refresh_sort_label(self):
        """刷新按钮上的状态名与菜单里的勾选位置。

        勾选标在当前排序方式上而不是按钮显示的那一项：按钮上显示时间筛选方式时，
        用户仍能看出这次筛选是基于哪种排序。
        """
        if self.sort_label is not None:
            self.sort_label.value = self.sort_label_text()
        for key, check in self.sort_checks.items():
            check.visible = (key == self.sort)
        self.app.update()

    def open_date_dialog(self):
        """按日期筛选：今天是 / 本周 / 本月 / 全部，下方为取消与确认。"""
        radios = ft.RadioGroup(
            value=self.time,
            content=ft.Column([
                ft.Radio(value=key, label=self.t("explore_time_" + key),
                         label_style=ft.TextStyle(size=13))
                for key in explore.TIME_MODES
            ], spacing=0))
        # 内容按固定尺寸限制：窗口紧紧包住内容并居中，不随主窗口变宽变高
        dialog = ft.AlertDialog(
            title=ft.Text(self.t("explore_sort_date"), size=16),
            content=ft.Container(content=radios, width=DATE_DIALOG_WIDTH,
                                 height=DATE_DIALOG_HEIGHT, alignment=ft.Alignment.TOP_LEFT),
            title_padding=ft.Padding.only(left=16, right=16, top=12, bottom=0),
            content_padding=ft.Padding.only(left=16, right=16, top=6, bottom=0),
            actions_padding=ft.Padding.only(left=8, right=8, top=0, bottom=6),
            actions=[
                ft.TextButton(self.t("btn_cancel"),
                              on_click=lambda e: self.app.page.pop_dialog()),
                ft.TextButton(self.t("btn_confirm"),
                              on_click=lambda e: self.apply_time(radios.value)),
            ],
        )
        self.app.page.show_dialog(dialog)

    def apply_time(self, value):
        """确认时间筛选：固定基于「最新」排序，窗口关闭后按所选范围重新加载。"""
        self.app.page.pop_dialog()
        self.time = value or explore.DEFAULT_TIME
        if self.time != explore.DEFAULT_TIME:
            # 时间筛选只在「最新」（时间排序）下有意义：这里把排序拉回「最新」
            self.sort = explore.DEFAULT_SORT
        self._refresh_sort_label()
        self.reload_from_first_page()

    def reload_from_first_page(self):
        """换排序 / 换时间筛选后：清空页缓存，回到第 1 页重新搜索。"""
        if self.searching or not self.keyword:
            return
        self.page_cache = {}
        self.total = 0
        self.ui_page = 1
        self._start_load()

    def _on_clear_keyword(self):
        """叉号：只清空输入框，已经出来的搜索结果保持不变。"""
        self.keyword_field.value = ""
        self.app.update()

    def reset_search(self):
        """返回开屏态：清空关键词与搜索结果，搜索区重新回到窗口中央。"""
        self.load_epoch += 1        # 作废可能还在跑的搜索，避免它把结果写回界面
        self.searching = False
        self.keyword_field.value = ""
        self.keyword = ""
        self.items = []
        self.total = 0
        self.ui_page = 1
        self.page_cache = {}
        self._set_hint("explore_hint")
        self.hint_visible = True
        self.searched_once = False
        if self.btn_search is not None:
            self.btn_search.disabled = False
        self._apply_layout()
        self._render()
        self.app.set_status(self.t("status_ready"), COLOR_IDLE)

    def _start_load(self):
        self.searching = True
        self.load_epoch += 1
        epoch = self.load_epoch
        self.items = []
        self._set_hint("status_searching")
        self.hint_visible = True
        # 首次点击搜索即切到置顶布局，与搜索结果无关；此后不再变化
        if not self.searched_once:
            self.searched_once = True
            self._apply_layout()
        if self.btn_search is not None:
            self.btn_search.disabled = True
        self._render()
        self.app.set_status(self.t("status_searching"))
        self.app.page.run_thread(self._worker, epoch)

    def _worker(self, epoch):
        error = None
        try:
            lib_page = (self.ui_page - 1) // UI_PAGES_PER_LIB_PAGE + 1
            items = self.page_cache.get(lib_page)
            if items is None:
                if self.client is None:
                    self.client = explore.new_client(self.app.conf)
                page = explore.search(self.client, self.mode, self.keyword, lib_page,
                                      self.sort, self.time)
                items = explore.to_items(page)
                self.total = int(page.total or 0)
                # 只保留最近两个库页，避免把封面字节一直堆在内存里
                self.page_cache[lib_page] = items
                while len(self.page_cache) > 2:
                    self.page_cache.pop(next(iter(self.page_cache)))
            offset = ((self.ui_page - 1) % UI_PAGES_PER_LIB_PAGE) * PAGE_SIZE
            self.items = items[offset:offset + PAGE_SIZE]
            fetch_covers(self.items)
        except Exception as exc:
            error = exc
            self.items = []
        if epoch != self.load_epoch:
            # 搜索期间用户点了「返回」：本次结果作废，
            # 界面与按钮状态由 reset_search 负责，这里什么都不碰
            return
        if error is not None:
            self._set_hint("explore_search_failed", error=error)
            self.hint_visible = True
        elif not self.items:
            self._set_hint("explore_no_result")
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
            self._set_hint("explore_search_failed", error=exc)
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

    def _refresh_pager(self):
        """翻页与排序菜单一起出现：有结果时才显示，搜索过程中不提前露出。"""
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
