# -*- coding: utf-8 -*-
"""任务中心页：展示下载队列里每个任务的状态、页数进度、速度与剩余时间。

- 顶部一行搜索栏（本子 ID / 名称），点搜索按钮或回车才过滤（与探索页一致）
- 第二行是排序菜单 + 升降序 + 取消排序 + 状态筛选菜单 + 计数
- 队列级操作（暂停全部 / 继续全部 / 清空已完成）放在顶栏右上角，
  不额外占用一行，窗口高度本来就有限
- 每个任务一张卡片：状态、进度条、页数 / 速度 / 剩余时间、以及该状态下的操作按钮

控件规格（高度、描边、圆角、字号、菜单展开方向）都对齐探索页与资源管理器；
本页实例由 :class:`AppUI` 缓存，返回时筛选、排序与搜索词仍然保留。
"""

import flet as ft

from core import library, task_queue
from core.config import resolve_path
from core.constants import (COLOR_ERR, COLOR_IDLE, COLOR_OK, ROUTE_DOWNLOAD, ROUTE_TASKS)

# 以下尺寸与探索页 / 资源管理器的工具控件保持一致（高 40、描边 + 圆角 8）
TOOL_HEIGHT = 40
SORT_ITEM_WIDTH = 110
SORT_CHECK_SIZE = 15
# 两个菜单按钮的宽度：比探索页的 84 略宽（本页有「加入顺序」这类四字状态名），
# 与收藏页菜单放宽到 110 是同一个理由，两个菜单取同一宽度以便左右对齐
MENU_BOX_WIDTH = 96

# 任务卡片里的图标按钮：资源管理器那套小方框图标的紧凑版
CARD_BUTTON_SIZE = 30
CARD_BUTTON_ICON = 16
# 任务卡片的进度条高度
CARD_BAR_HEIGHT = 6

# 状态 -> 标签颜色：完成 / 失败沿用全局语义色，其余用主题的中性色（比 COLOR_IDLE 亮，
# 在深色底上更清楚）
STATUS_COLORS = {
    task_queue.STATUS_WAITING: ft.Colors.ON_SURFACE_VARIANT,
    task_queue.STATUS_RUNNING: COLOR_OK,
    task_queue.STATUS_PAUSED: ft.Colors.ON_SURFACE_VARIANT,
    task_queue.STATUS_DONE: COLOR_OK,
    task_queue.STATUS_FAILED: COLOR_ERR,
    task_queue.STATUS_CANCELED: ft.Colors.ON_SURFACE_VARIANT,
}

# 顶栏图标之间的间距与右侧留白（图标按钮自带 8px 内边距，再补 4px 即可与页面对齐）
APPBAR_ICON_GAP = 4
# 详情文字不超过这个长度就不挂 tooltip：短文本挂 tooltip 只会频繁浮在相邻卡片上
DETAIL_TOOLTIP_MIN = 36


class TaskPage:
    def __init__(self, app):
        self.app = app
        self.keyword = ""
        self.status_filter = task_queue.FILTER_ALL
        self.sort_key = task_queue.DEFAULT_SORT_KEY
        self.sort_desc = task_queue.SORT_DESC_DEFAULT[self.sort_key]
        self.filter_checks = {}      # 筛选菜单项上的勾选标记
        self.sort_checks = {}        # 排序菜单项上的勾选标记
        self.rows = {}               # task.id -> 该行的进度控件引用
        self._built_ids = []
        self._built_states = []
        self._built_marks = []       # [(是否请求取消, 是否请求暂停)]，用于判断要不要重建行

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def build_view(self):
        app = self.app
        self.rows = {}
        self._built_ids = []
        self._built_states = []
        self._built_marks = []
        self.status_text = ft.Text(app.status_text_value, size=12, color=app.status_color)
        self.list_view = ft.ListView(expand=True, spacing=6, padding=6)
        self.count_text = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT)
        # 队列级操作：放顶栏右上角，不额外占行，窗口高度本来就有限；
        # 图标之间与最右侧各补一点空隙，避免三个按钮挤在一起、也避免贴到窗口边缘
        self.btn_pause_all = ft.IconButton(ft.Icons.PAUSE, tooltip=self.t("btn_pause_all"),
                                           on_click=lambda e: self._on_pause_all())
        self.btn_resume_all = ft.IconButton(ft.Icons.PLAY_ARROW,
                                            tooltip=self.t("btn_resume_all"),
                                            on_click=lambda e: self._on_resume_all())
        self.btn_clear_done = ft.IconButton(ft.Icons.CLEAR_ALL,
                                            tooltip=self.t("btn_clear_done"),
                                            on_click=lambda e: self._on_clear_done())

        left = ft.Column([
            self._build_search_bar(),
            ft.Row([self._build_sort_menu(), self._build_order_button(),
                    self._build_reset_button(), self._build_filter_menu(),
                    self.count_text], spacing=8,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1),
            ft.Container(content=self.list_view, expand=True, border_radius=6,
                         border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)),
            self.status_text,
        ], expand=True, spacing=8)

        view = ft.View(
            route=ROUTE_TASKS,
            appbar=ft.AppBar(
                title=ft.Text(self.t("tasks_title")),
                # 返回下载页（任务中心的入口就在下载页顶栏），而不是回首页
                leading=ft.IconButton(ft.Icons.ARROW_BACK,
                                      on_click=lambda e: app.navigate(ROUTE_DOWNLOAD)),
                actions=[self._appbar_slot(self.btn_pause_all),
                         self._appbar_slot(self.btn_resume_all),
                         self._appbar_slot(self.btn_clear_done, trailing=True)],
            ),
            controls=[left],
            padding=12,
        )
        app.bind_status(self.status_text)
        self.refresh()
        return view

    # ---- 搜索栏与菜单（规格对齐探索页 / 资源管理器）

    def _build_search_bar(self):
        """搜索栏：输入关键词后点搜索按钮或按回车才过滤（不做输入即搜）。"""
        self.search_field = ft.TextField(
            value=self.keyword, hint_text=self.t("task_search_hint"),
            expand=True, dense=True, border=ft.NoInputBorder(),
            on_submit=lambda e: self._apply_filter())
        self.btn_clear = ft.IconButton(ft.Icons.CLEAR, tooltip=self.t("btn_clear"),
                                       on_click=lambda e: self._on_clear_keyword())
        self.btn_search = ft.IconButton(ft.Icons.SEARCH, tooltip=self.t("btn_search"),
                                        on_click=lambda e: self._apply_filter())
        return ft.Container(
            content=ft.Row([self.search_field, self.btn_clear, self.btn_search],
                           spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8, padding=ft.Padding.only(left=10, right=4, top=2, bottom=2))

    def _build_sort_menu(self):
        """排序菜单：加入顺序 / 本子 ID / 名称 / 进度，当前项右侧打勾。"""
        self.sort_label = ft.Text(self.sort_label_text(), size=13, max_lines=1,
                                 text_align=ft.TextAlign.CENTER, expand=True,
                                 overflow=ft.TextOverflow.ELLIPSIS)
        self.sort_checks = {}
        self.sort_menu = ft.PopupMenuButton(
            content=ft.Row([self.sort_label, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18)],
                           spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            items=[self._sort_item(key) for key in task_queue.TASK_SORT_KEYS],
            # 从按钮下边缘展开，避免菜单盖住按钮本身（与探索页一致）
            menu_position=ft.PopupMenuPosition.UNDER,
            padding=0,
        )
        return self._tool_box(self.sort_menu, MENU_BOX_WIDTH)

    def _build_filter_menu(self):
        """状态筛选菜单：全部 / 等待中 / 下载中 / 已暂停 / 已完成 / 失败。"""
        self.filter_label = ft.Text(self.filter_label_text(), size=13, max_lines=1,
                                    text_align=ft.TextAlign.CENTER, expand=True,
                                    overflow=ft.TextOverflow.ELLIPSIS)
        self.filter_checks = {}
        options = (task_queue.FILTER_ALL,) + task_queue.TASK_STATUSES
        self.filter_menu = ft.PopupMenuButton(
            content=ft.Row([self.filter_label, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18)],
                           spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            items=[self._filter_item(key) for key in options],
            menu_position=ft.PopupMenuPosition.UNDER,
            padding=0,
        )
        return self._tool_box(self.filter_menu, MENU_BOX_WIDTH)

    def _build_order_button(self):
        """升序 / 降序按钮：图标显示当前方向，紧挨着排序菜单。"""
        self.order_btn = self._icon_box_button(self._order_icon(), self._order_tooltip(),
                                              self._toggle_sort_desc)
        return self._tool_box(self.order_btn, TOOL_HEIGHT, pad=ft.Padding.all(0))

    def _build_reset_button(self):
        """取消排序按钮：恢复默认排序（加入顺序）。"""
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
        """把控件包成与排序菜单同档的小方框（高度 / 描边 / 圆角一致）。"""
        return ft.Container(
            content=control, height=TOOL_HEIGHT, width=width,
            alignment=ft.Alignment.CENTER,
            padding=pad if pad is not None else ft.Padding.symmetric(horizontal=8),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=8)

    @staticmethod
    def _appbar_slot(control, trailing=False):
        """给顶栏图标补间距：彼此之间留一点空隙，最后一个再补右侧留白。"""
        return ft.Container(
            content=control,
            padding=ft.Padding.only(left=APPBAR_ICON_GAP,
                                    right=APPBAR_ICON_GAP if trailing else 0))

    def _sort_item(self, key):
        """一个排序菜单项：名称在左、勾选标记在右（只有当前字段显示勾选）。"""
        check = ft.Icon(ft.Icons.CHECK, size=SORT_CHECK_SIZE, visible=(key == self.sort_key))
        self.sort_checks[key] = check
        return ft.PopupMenuItem(content=self._menu_row(self.t("task_sort_" + key), check),
                                on_click=lambda e, k=key: self._select_sort(k))

    def _filter_item(self, key):
        """一个筛选菜单项：名称在左、勾选标记在右（只有当前项显示勾选）。"""
        check = ft.Icon(ft.Icons.CHECK, size=SORT_CHECK_SIZE,
                        visible=(key == self.status_filter))
        self.filter_checks[key] = check
        return ft.PopupMenuItem(content=self._menu_row(self._filter_text(key), check),
                                on_click=lambda e, k=key: self._select_filter(k))

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
        return self.t("task_sort_" + self.sort_key)

    def filter_label_text(self):
        return self._filter_text(self.status_filter)

    def _filter_text(self, key):
        if key == task_queue.FILTER_ALL:
            return self.t("task_filter_all")
        return self.t("task_status_" + key)

    def _order_icon(self):
        """当前排序方向的图标：降序向下、升序向上。"""
        return ft.Icons.ARROW_DOWNWARD if self.sort_desc else ft.Icons.ARROW_UPWARD

    def _order_tooltip(self):
        """方向按钮的提示：显示「点了会变成什么」。"""
        return self.t("explorer_order_to_asc" if self.sort_desc
                      else "explorer_order_to_desc")

    def _is_default_sort(self):
        return (self.sort_key == task_queue.DEFAULT_SORT_KEY
                and self.sort_desc == task_queue.SORT_DESC_DEFAULT[self.sort_key])

    # ------------------------------------------------------------------
    # 列表刷新
    # ------------------------------------------------------------------
    def refresh(self):
        """刷新列表：任务集合或状态变化才重建行，否则只就地更新进度。"""
        tasks = self.app.queue.tasks()
        visible = task_queue.sort_tasks(
            task_queue.filter_tasks(tasks, self.keyword, self.status_filter),
            self.sort_key, self.sort_desc)
        ids = [task.id for task in visible]
        states = [task.status for task in visible]
        # 暂停 / 取消的请求标记也要参与比较：它一变化就要重建该行，好把按钮置灰
        marks = [(task.cancel_requested, task.pause_requested) for task in visible]
        if ids != self._built_ids or states != self._built_states \
                or marks != self._built_marks:
            self._rebuild(visible)
        else:
            for task in visible:
                self._update_row(task)
        self._refresh_count(len(visible), len(tasks))
        self._refresh_toolbar()
        self.app.update()

    def _rebuild(self, visible):
        """按当前筛选结果重建整份列表（任务增删、状态或中止请求变化时）。"""
        self.rows = {}
        if not visible:
            # 区分「队列本来就是空的」与「只是没匹配上筛选条件」
            key = "tasks_no_match" if (self.keyword or self.status_filter != task_queue.FILTER_ALL) \
                else "tasks_empty"
            self.list_view.controls = [ft.Container(
                content=ft.Text(self.t(key), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                padding=12)]
        else:
            self.list_view.controls = [self._card(task) for task in visible]
        self._built_ids = [task.id for task in visible]
        self._built_states = [task.status for task in visible]
        self._built_marks = [(task.cancel_requested, task.pause_requested)
                             for task in visible]

    def _refresh_count(self, shown, total):
        if self.keyword or self.status_filter != task_queue.FILTER_ALL:
            self.count_text.value = self.t("tasks_count_filtered", shown=shown, total=total)
        else:
            self.count_text.value = self.t("tasks_count", count=total)

    def _refresh_toolbar(self):
        """同步菜单上的状态名、勾选位置与顶栏按钮的可用性。"""
        self.sort_label.value = self.sort_label_text()
        self.filter_label.value = self.filter_label_text()
        for key, check in self.sort_checks.items():
            check.visible = (key == self.sort_key)
        for key, check in self.filter_checks.items():
            check.visible = (key == self.status_filter)
        self.order_btn.icon = self._order_icon()
        self.order_btn.tooltip = self._order_tooltip()
        self.reset_btn.disabled = self._is_default_sort()

        stats = self.app.queue.stats()
        self.btn_pause_all.disabled = not (stats.get("waiting") or stats.get("running"))
        # 队列处于暂停态时也要能点「继续全部」：即使此刻列表里没有已暂停的任务，
        # 用户也得有办法把暂停解除，否则新加的任务会永远停在「等待中」
        self.btn_resume_all.disabled = not (stats.get("paused")
                                           or self.app.queue.is_paused())
        self.btn_clear_done.disabled = not (stats.get("done") or stats.get("canceled"))

    # ------------------------------------------------------------------
    # 任务卡片
    # ------------------------------------------------------------------
    def _card(self, task):
        status_text = ft.Text(self.t("task_status_" + task.status), size=11,
                              color=STATUS_COLORS.get(task.status,
                                                      ft.Colors.ON_SURFACE_VARIANT))
        bar = ft.ProgressBar(value=self._bar_value(task), height=CARD_BAR_HEIGHT,
                             border_radius=CARD_BAR_HEIGHT / 2)
        detail_text = self._detail_text(task)
        detail = ft.Text(detail_text, size=11,
                         color=ft.Colors.ON_SURFACE_VARIANT, expand=True, max_lines=1,
                         overflow=ft.TextOverflow.ELLIPSIS,
                         tooltip=self._detail_tooltip(detail_text))
        row = ft.Row([detail, ft.Row(self._actions(task), spacing=2,
                                     vertical_alignment=ft.CrossAxisAlignment.CENTER)],
                     spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.rows[task.id] = {"bar": bar, "status": status_text, "detail": detail,
                              "state": task.status, "card": None}
        title = task.name or task.album_id
        card = ft.Container(
            content=ft.Column([
                ft.Row([ft.Text("#%04d" % task.seq, size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text(title, size=13, max_lines=1, expand=True,
                                overflow=ft.TextOverflow.ELLIPSIS, tooltip=title),
                        status_text], spacing=6,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bar,
                row,
            ], spacing=6),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8, padding=ft.Padding.symmetric(horizontal=10, vertical=8))
        self.rows[task.id]["card"] = card
        return card

    def _update_row(self, task):
        """就地更新一行（只有进度 / 时间在变，控件不重建）。"""
        row = self.rows.get(task.id)
        if row is None:
            return
        row["bar"].value = self._bar_value(task)
        row["status"].value = self.t("task_status_" + task.status)
        row["status"].color = STATUS_COLORS.get(task.status,
                                                ft.Colors.ON_SURFACE_VARIANT)
        text = self._detail_text(task)
        row["detail"].value = text
        row["detail"].tooltip = self._detail_tooltip(text)

    @staticmethod
    def _bar_value(task):
        """进度条取值。

        只有「下载中且总页数还没取到」才用不定态（表示正在跑、进度未知）；
        等待 / 暂停 / 失败 / 取消这些静止状态一律显示 0，避免动画让人误以为在下载。
        """
        if task.status == task_queue.STATUS_RUNNING and not task.pages_total:
            return None
        value = task.progress()
        if value is not None:
            return value
        return 1 if task.status == task_queue.STATUS_DONE else 0

    @staticmethod
    def _detail_tooltip(text):
        """详情文字较长（可能被省略）时才挂 tooltip，短文本不挂以免浮层遮挡邻行。"""
        return text if len(text) > DETAIL_TOOLTIP_MIN else None

    def _pages_text(self, task):
        if not task.pages_total:
            return self.t("task_pages_unknown")
        # 页数正常不会超过总数（每轮从 0 起算），这里只做兜底，避免显示出「600/512 页」
        done = min(task.pages_done, task.pages_total)
        return self.t("task_pages_progress", done=done, total=task.pages_total)

    def _detail_text(self, task):
        """卡片上的详情行：进度、速度、剩余时间或失败原因。"""
        if task.status == task_queue.STATUS_FAILED:
            return task.error or self.t("status_error")
        parts = []
        if task.status == task_queue.STATUS_WAITING:
            parts.append(self.t("task_status_waiting"))
            if task.pages_total:
                parts.append(self.t("task_pages_total", pages=task.pages_total))
        elif task.status == task_queue.STATUS_RUNNING:
            parts.append(self._pages_text(task))
            rate = task.byte_rate
            if rate:
                parts.append(self.t("task_speed", speed=task_queue.format_size(rate)))
            eta = task.eta
            parts.append(self.t("task_eta", eta=task_queue.format_duration(eta))
                         if eta is not None else self.t("task_eta_unknown"))
        else:
            parts.append(self._pages_text(task))
            if task.status == task_queue.STATUS_DONE and task.pdfs:
                parts.append(self.t("task_pdf_count", count=len(task.pdfs)))
        # 刚暂停 / 取消时，上一轮可能还在收尾（已经发出的网络请求没法瞬间掐断），
        # 这里如实说明，免得用户以为「点了没反应」
        if task.inflight and task.status in (task_queue.STATUS_PAUSED,
                                             task_queue.STATUS_WAITING):
            parts.append(self.t("task_wrap_up"))
        return " · ".join(part for part in parts if part)

    def _actions(self, task):
        """按状态给出可用的操作按钮（都是卡片里的紧凑图标按钮）。"""
        status = task.status
        buttons = []
        if status == task_queue.STATUS_WAITING:
            buttons.append(self._card_button(ft.Icons.CLOSE, self.t("btn_cancel_task"),
                                             lambda e, t=task: self._on_cancel_task(t)))
        elif status == task_queue.STATUS_RUNNING:
            buttons.append(self._card_button(ft.Icons.PAUSE, self.t("btn_pause"),
                                             lambda e, t=task: self._on_pause_task(t)))
            buttons.append(self._card_button(ft.Icons.CLOSE, self.t("btn_cancel_task"),
                                             lambda e, t=task: self._on_cancel_task(t)))
        elif status == task_queue.STATUS_PAUSED:
            buttons.append(self._card_button(ft.Icons.PLAY_ARROW, self.t("btn_resume"),
                                             lambda e, t=task: self._on_resume_task(t)))
            buttons.append(self._card_button(ft.Icons.CLOSE, self.t("btn_cancel_task"),
                                             lambda e, t=task: self._on_cancel_task(t)))
        elif status in (task_queue.STATUS_FAILED, task_queue.STATUS_CANCELED):
            buttons.append(self._card_button(ft.Icons.REFRESH, self.t("btn_retry"),
                                             lambda e, t=task: self._on_retry_task(t)))
            buttons.append(self._card_button(ft.Icons.DELETE_OUTLINE, self.t("btn_remove"),
                                             lambda e, t=task: self._on_remove_task(t)))
        else:
            buttons.append(self._card_button(ft.Icons.FOLDER_OPEN, self.t("btn_open_folder"),
                                             lambda e, t=task: self._on_open_folder(t)))
            buttons.append(self._card_button(ft.Icons.DELETE_OUTLINE, self.t("btn_remove"),
                                             lambda e, t=task: self._on_remove_task(t)))
        return buttons

    @staticmethod
    def _card_button(icon, tooltip, on_click):
        """任务卡片里的图标按钮：小方框图标的紧凑版（30x30，居中）。"""
        return ft.IconButton(icon=icon, icon_size=CARD_BUTTON_ICON, padding=0,
                             width=CARD_BUTTON_SIZE, height=CARD_BUTTON_SIZE,
                             tooltip=tooltip, on_click=on_click)

    # ------------------------------------------------------------------
    # 搜索 / 排序 / 筛选
    # ------------------------------------------------------------------
    def _apply_filter(self):
        self.keyword = (self.search_field.value or "").strip()
        self.refresh()

    def _on_clear_keyword(self):
        self.search_field.value = ""
        self._apply_filter()

    def _select_sort(self, key):
        if key == self.sort_key:
            return
        self.sort_key = key
        self.sort_desc = task_queue.SORT_DESC_DEFAULT[key]
        self.refresh()

    def _toggle_sort_desc(self, e=None):
        self.sort_desc = not self.sort_desc
        self.refresh()

    def _reset_sort(self):
        if self._is_default_sort():
            return
        self.sort_key = task_queue.DEFAULT_SORT_KEY
        self.sort_desc = task_queue.SORT_DESC_DEFAULT[self.sort_key]
        self.refresh()

    def _select_filter(self, key):
        self.status_filter = key or task_queue.FILTER_ALL
        self.refresh()

    # ------------------------------------------------------------------
    # 队列操作
    # ------------------------------------------------------------------
    def _on_pause_all(self):
        self.app.queue.pause_all()
        self.app.set_status(self.t("status_queue_paused"), COLOR_IDLE)

    def _on_resume_all(self):
        self.app.queue.resume_all()
        self.app.set_status(self.t("status_queue_resumed"), COLOR_OK)

    def _on_clear_done(self):
        removed = self.app.queue.clear_finished()
        if removed:
            self.app.set_status(self.t("status_task_removed_count", count=removed))

    def _on_pause_task(self, task):
        """暂停单个任务：状态立刻变为已暂停（正在跑的那一轮在卡片上显示「正在收尾…」）。"""
        if self.app.queue.pause_task(task.id):
            self.app.set_status(self.t("status_task_paused", id=task.album_id), COLOR_IDLE)

    def _on_resume_task(self, task):
        if self.app.queue.resume_task(task.id):
            self.app.set_status(self.t("status_task_resumed", id=task.album_id), COLOR_OK)

    def _on_retry_task(self, task):
        if self.app.queue.retry_task(task.id):
            self.app.set_status(self.t("status_task_retried", id=task.album_id), COLOR_OK)

    def _on_remove_task(self, task):
        if self.app.queue.remove_task(task.id):
            self.app.set_status(self.t("status_task_removed", id=task.album_id))

    def _on_cancel_task(self, task):
        """取消任务：会清掉本轮已下载的内容，所以下载中 / 已暂停的都先确认一次。"""
        if task.status == task_queue.STATUS_WAITING:
            self._cancel_task(task)      # 还没开始下，没有东西可清，不必确认
            return
        dialog = ft.AlertDialog(
            title=ft.Text(self.t("task_confirm_cancel_title")),
            content=ft.Text(self.t("task_confirm_cancel_body", id=task.album_id),
                            size=12, selectable=True),
            actions=[
                ft.TextButton(self.t("btn_cancel"),
                              on_click=lambda e: self.app.page.pop_dialog()),
                ft.TextButton(self.t("btn_confirm"),
                              on_click=lambda e: self._cancel_task(task, close=True)),
            ],
        )
        self.app.page.show_dialog(dialog)

    def _cancel_task(self, task, close=False):
        if close:
            self.app.page.pop_dialog()
        if self.app.queue.cancel_task(task.id):
            self.app.set_status(self.t("status_task_canceled", id=task.album_id))

    def _on_open_folder(self, task):
        """打开产物目录（任务完成后用）。"""
        path = task.output_dir
        if not path:
            path = resolve_path(self.app.conf["app"].get("download_dir"))
        try:
            library.open_path(path)
        except OSError as exc:
            self.app.set_status(self.t("status_open_failed", error=exc), COLOR_ERR)
