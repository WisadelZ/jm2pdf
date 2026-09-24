# -*- coding: utf-8 -*-
"""账号页：登录账号并展示账号信息与账号相关功能入口。

未登录时页面中央自上而下依次是提示语、账号输入框、密码输入框与登录按钮，
三者各自占据一行并居中。

登录后左上角展示头像与昵称（昵称在头像右侧），下方依次是：
收藏列表（折叠式：标题可点击展开 / 收起，右侧「查看更多」进入完整收藏页，
展开后展示「全部」收藏夹里最前面的若干本）、退出登录。

账号信息由 :mod:`core.account` 加密保存在程序同级目录，界面不落盘任何明文。
"""

import flet as ft

from core import checkin
from core.constants import (COLOR_ERR, COLOR_OK, ROUTE_ACCOUNT, ROUTE_FAVORITE,
                            ROUTE_MAIN)

# 提示语字号：与首页欢迎语接近，内容更长所以略小一号
PROMPT_FONT_SIZE = 22
# 输入框 / 登录按钮宽度：三者等宽，居中后视觉上对齐成一条竖线
FIELD_WIDTH = 320
# 头像半径与昵称字号（登录后展示，比原先略小一点）
AVATAR_RADIUS = 36
NICKNAME_FONT_SIZE = 16
# 昵称与头像同排：昵称宽度固定，过长时省略号收尾，整块宽度保持稳定
NICKNAME_WIDTH = 180
AVATAR_GAP = 10
# 账号状态（等级 / 经验 / 收藏数）：标签定宽，三行左端对齐成一列
INFO_LABEL_WIDTH = 44
INFO_GAP = 6
# 收藏数与 J 币在同一行，中间留一段固定间隔
COIN_GAP = 24
# 经验进度条尺寸
EXP_BAR_WIDTH = 150
EXP_BAR_HEIGHT = 8
# 字段缺失时的占位符
EMPTY_VALUE = "—"
# 功能入口按钮：统一尺寸，比其它页面的按钮稍大，左边界与头像对齐
BUTTON_WIDTH = 200
BUTTON_HEIGHT = 46
# 退出登录按钮的红色底色（与全局错误色同一个红）
DANGER_BGCOLOR = COLOR_ERR

# 收藏预览的格子尺寸：与收藏页一致，默认窗口宽度下正好 4 本一行、两行
COVER_WIDTH = 140
COVER_HEIGHT = 187
NAME_HEIGHT = 34
PREVIEW_GAP = 12
# 「收藏列表」标题字号
SECTION_TITLE_SIZE = 20
# 签到结果弹窗：尺寸固定（按最多 5 行内容算），不随内容或窗口变化
CHECKIN_DIALOG_WIDTH = 260
CHECKIN_DIALOG_HEIGHT = 220
# 行的值默认单行省略（完整内容放 tooltip）；出错原因这类长文本才允许多行
CHECKIN_VALUE_MAX_LINES = 1
CHECKIN_ERROR_MAX_LINES = 4
# 展开 / 收起的箭头图标
ARROW_EXPANDED = ft.Icons.EXPAND_MORE
ARROW_COLLAPSED = ft.Icons.CHEVRON_RIGHT


def _int_text(value):
    """把接口返回的数字格式化成带千位分隔符的文本；解析不出来时给占位符。"""
    try:
        return format(int(float(str(value).strip())), ",")
    except (TypeError, ValueError):
        return EMPTY_VALUE


def _percent(value):
    """经验百分比：接口给的是 0~100 的数，进度条要 0~1。"""
    try:
        return max(0.0, min(1.0, float(value) / 100.0))
    except (TypeError, ValueError):
        return 0.0


def _percent_text(value):
    try:
        return "%.1f%%" % float(value)
    except (TypeError, ValueError):
        return EMPTY_VALUE


class AccountPage:
    def __init__(self, app):
        self.app = app
        self.favorites_expanded = True   # 收藏列表默认展开
        self.checking_in = False         # 是否正在签到
        self.checkin_dialog = None       # 当前签到弹窗（避免重复叠加）
        self.fav_arrow = None
        self.fav_body = None
        self.btn_checkin = None
        self.avatar_holder = None        # 头像容器：异步取到后就地替换
        self.info_holder = None          # 账号状态容器：异步刷新时就地替换

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def build_view(self):
        app = self.app
        self.status_text = ft.Text(app.status_text_value, size=12, color=app.status_color,
                                   text_align=ft.TextAlign.CENTER)
        if app.account:
            # 登录后有收藏预览，内容会超出窗口高度，因此整列可滚动
            content = ft.Column([self._logged_view(), self.status_text], expand=True,
                                spacing=PREVIEW_GAP, scroll=ft.ScrollMode.AUTO,
                                horizontal_alignment=ft.CrossAxisAlignment.START)
        else:
            body = self._login_view()
            content = ft.Column([body, self.status_text], expand=True, spacing=8,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        view = ft.View(
            route=ROUTE_ACCOUNT,
            appbar=ft.AppBar(
                title=ft.Text(self.t("account_title")),
                leading=ft.IconButton(ft.Icons.ARROW_BACK,
                                      on_click=lambda e: app.navigate(ROUTE_MAIN)),
            ),
            controls=[content],
            padding=12,
        )
        app.bind_status(self.status_text)
        app.ensure_avatar()
        app.ensure_account_favorites()
        app.ensure_account_profile()
        return view

    @staticmethod
    def _centered(body):
        """把内容块推到页面正中央：上下各留一块等高的弹性留白。"""
        return ft.Column([ft.Container(expand=True), body, ft.Container(expand=True)],
                         expand=True, spacing=0,
                         horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _login_view(self):
        self.username_field = ft.TextField(
            label=self.t("label_account"), width=FIELD_WIDTH,
            on_submit=lambda e: self._on_login())
        self.password_field = ft.TextField(
            label=self.t("label_password"), width=FIELD_WIDTH, password=True,
            on_submit=lambda e: self._on_login())
        self.btn_login = ft.Button(
            self.t("btn_login"), width=FIELD_WIDTH, disabled=self.app.logging_in,
            on_click=lambda e: self._on_login())
        body = ft.Column([
            ft.Text(self.t("account_login_prompt"), size=PROMPT_FONT_SIZE,
                    text_align=ft.TextAlign.CENTER),
            self.username_field,
            self.password_field,
            self.btn_login,
        ], spacing=18, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        return self._centered(body)

    def _logged_view(self):
        account = self.app.account or {}
        nickname = account.get("nickname") or account.get("username") or ""
        self.avatar_holder = ft.Container(content=self._avatar_control(self.app.account_avatar))
        self.info_holder = ft.Container(content=self._account_info(account))
        # 头像在左、昵称与账号状态在右，同一块；整块与下面的按钮都以左边界对齐
        header = ft.Row([
            self.avatar_holder,
            ft.Column([
                ft.Text(nickname, size=NICKNAME_FONT_SIZE, width=NICKNAME_WIDTH,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                        tooltip=nickname or None),
                self.info_holder,
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.START),
        ], spacing=AVATAR_GAP, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        return ft.Column([
            header,
            self._favorites_section(),
            ft.Row([self._checkin_button(), self._logout_button()], spacing=12),
        ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.START)

    @staticmethod
    def _avatar_control(avatar):
        if avatar:
            return ft.CircleAvatar(radius=AVATAR_RADIUS, foreground_image_src=avatar)
        return ft.CircleAvatar(
            radius=AVATAR_RADIUS,
            content=ft.Icon(ft.Icons.PERSON, size=AVATAR_RADIUS,
                            color=ft.Colors.ON_SURFACE_VARIANT))

    # ------------------------------------------------------------------
    # 异步结果的就地刷新（这些数据是后台线程取回来的，重建整页会与
    # 弹窗 / 点击事件抢时序，所以只替换对应容器里的内容）
    # ------------------------------------------------------------------
    def set_avatar(self, avatar):
        """头像取回来后替换头像控件。"""
        if self.avatar_holder is None:
            return
        self.avatar_holder.content = self._avatar_control(avatar)
        self.app.update()

    def refresh_account_info(self):
        """账号状态（等级 / 经验 / 收藏数 / J 币）变化后就地刷新。"""
        if self.info_holder is None:
            return
        self.info_holder.content = self._account_info(self.app.account or {})
        self.app.update()

    def refresh_favorites(self):
        """收藏预览取回来后就地刷新。"""
        if self.fav_body is None:
            return
        self.fav_body.content = self._favorites_body()
        self.app.update()

    def _checkin_button(self):
        self.btn_checkin = self._feature_button(
            self.t("btn_checkin"), ft.Icons.CALENDAR_MONTH, lambda e: self._on_checkin())
        return self.btn_checkin

    def _logout_button(self):
        return self._feature_button(self.t("btn_logout"), ft.Icons.LOGOUT,
                                    lambda e: self.app.logout(), danger=True)

    def _account_info(self, account):
        """账号状态：等级称号、经验进度（进度条 + 数值）、收藏数与 J 币。"""
        level, title = account.get("level"), str(account.get("level_name") or "").strip()
        if level is None and not title:
            level_text = EMPTY_VALUE
        else:
            level_text = ("Lv.%s %s" % (EMPTY_VALUE if level is None else level,
                                        title)).strip()
        exp_text = self.t("account_exp_value", exp=_int_text(account.get("exp")),
                          next=_int_text(account.get("next_level_exp")),
                          percent=_percent_text(account.get("exp_percent")))
        return ft.Column([
            self._info_row(self.t("account_level"), ft.Text(level_text, size=13)),
            self._info_row(self.t("account_exp"), ft.Row([
                ft.ProgressBar(value=_percent(account.get("exp_percent")),
                               width=EXP_BAR_WIDTH, height=EXP_BAR_HEIGHT,
                               border_radius=EXP_BAR_HEIGHT),
                ft.Text(exp_text, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)),
            # 收藏数与 J 币同一行，中间留一段固定间隔
            self._info_row(self.t("account_favorites_count"), ft.Row([
                ft.Text(self.t("account_favorites_value",
                               count=_int_text(account.get("favorites")),
                               total=_int_text(account.get("favorites_max"))), size=13),
                ft.Container(width=COIN_GAP),
                ft.Text(self.t("account_coin"), size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(_int_text(account.get("coin")), size=13),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)),
        ], spacing=INFO_GAP, horizontal_alignment=ft.CrossAxisAlignment.START)

    def _info_row(self, label, value_control):
        return ft.Row([
            ft.Text(label, size=12, width=INFO_LABEL_WIDTH,
                    color=ft.Colors.ON_SURFACE_VARIANT),
            value_control,
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _favorites_section(self):
        """折叠式收藏列表：标题行（点击展开 / 收起）+ 右侧「查看更多」+ 下方预览。

        标题行占满页面宽度，「查看更多」就落在页面固定的右边距上；预览网格按
        页面可用宽度自动换行，默认尺寸下正好一行 4 本。
        """
        self.fav_arrow = ft.Icon(self._arrow_icon(), size=24)
        title = ft.Row([self.fav_arrow,
                        ft.Text(self.t("favorite_title"), size=SECTION_TITLE_SIZE)],
                       spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        # 标题区域占据剩余宽度（整行空白处都可点击），按钮留在最右侧
        toggle = ft.GestureDetector(content=title, expand=True,
                                    mouse_cursor=ft.MouseCursor.CLICK,
                                    on_tap=lambda e: self.toggle_favorites())
        self.btn_view_more = ft.Button(
            self.t("btn_view_more"), icon=ft.Icons.CHEVRON_RIGHT,
            visible=self.favorites_expanded,
            on_click=lambda e: self.app.navigate(ROUTE_FAVORITE))
        head = ft.Row([toggle, self.btn_view_more],
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.fav_body = ft.Container(content=self._favorites_body(),
                                     visible=self.favorites_expanded)
        return ft.Column([head, self.fav_body], spacing=8,
                         horizontal_alignment=ft.CrossAxisAlignment.START)

    def _arrow_icon(self):
        return ARROW_EXPANDED if self.favorites_expanded else ARROW_COLLAPSED

    def toggle_favorites(self):
        """折叠 / 展开收藏预览：收起时同时隐藏「查看更多」。"""
        self.favorites_expanded = not self.favorites_expanded
        self.fav_body.visible = self.favorites_expanded
        self.btn_view_more.visible = self.favorites_expanded
        self.fav_arrow.icon = self._arrow_icon()
        self.app.update()

    def _favorites_body(self):
        """收藏预览内容：读取中 / 读取失败 / 空 / 前若干本的封面网格。"""
        app = self.app
        if app.account_favorites is None:
            return ft.Text(self.t("favorite_loading"), size=12,
                           color=ft.Colors.ON_SURFACE_VARIANT)
        if app.account_favorites_error is not None:
            return ft.Text(self.t("favorite_load_failed", error=app.account_favorites_error),
                           size=12, color=COLOR_ERR, selectable=True)
        if not app.account_favorites:
            return ft.Text(self.t("favorite_empty"), size=12,
                           color=ft.Colors.ON_SURFACE_VARIANT)
        # 按页面可用宽度自动换行：默认尺寸下正好一行 4 本
        return ft.Row(wrap=True, spacing=PREVIEW_GAP, run_spacing=PREVIEW_GAP,
                      vertical_alignment=ft.CrossAxisAlignment.START,
                      controls=[self._preview_tile(item)
                                for item in app.account_favorites])

    def _preview_tile(self, item):
        """预览格子：封面 + 名称，点击进入本子详情。"""
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
        open_album = lambda e: self.app.open_album(item["id"])   # noqa: E731
        return ft.Column([
            ft.GestureDetector(content=cover_control, mouse_cursor=ft.MouseCursor.CLICK,
                               on_tap=open_album),
            ft.GestureDetector(
                content=ft.Container(
                    content=ft.Text(item["name"], size=12, max_lines=2,
                                    tooltip=item["name"] or None,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                    width=COVER_WIDTH, height=NAME_HEIGHT),
                mouse_cursor=ft.MouseCursor.CLICK, on_tap=open_album),
        ], width=COVER_WIDTH, spacing=6, alignment=ft.MainAxisAlignment.START)

    @staticmethod
    def _feature_button(label, icon, on_click, danger=False):
        """功能入口按钮：独立一行，尺寸统一，左边界与头像对齐。"""
        return ft.Button(
            label, icon=icon, width=BUTTON_WIDTH, height=BUTTON_HEIGHT,
            bgcolor=DANGER_BGCOLOR if danger else None,
            color=ft.Colors.WHITE if danger else None,
            on_click=on_click)

    # ------------------------------------------------------------------
    # 签到
    # ------------------------------------------------------------------
    def _on_checkin(self):
        """执行每日签到；网络请求放到后台线程，完成后弹窗展示结果。"""
        if self.checking_in:
            return
        self.checking_in = True
        self.btn_checkin.disabled = True
        self.app.set_status(self.t("status_checking_in"))
        self.app.page.run_thread(self._checkin_worker)

    def _checkin_worker(self):
        try:
            result, error = checkin.check_in(self.app.conf), None
        except Exception as exc:
            result, error = None, exc
        self.checking_in = False
        self.btn_checkin.disabled = False
        if error is None:
            self.app.set_status(self.t("status_checkin_done"), COLOR_OK)
            self.app.refresh_account_profile()      # 签到会改变 J 币 / 经验
        else:
            self.app.set_status(self.t("status_checkin_failed", error=error), COLOR_ERR)
        self._show_checkin_dialog(result, error)

    def _show_checkin_dialog(self, result, error):
        """签到结果弹窗：尺寸固定，不滚动，只有「确认」一个动作。"""
        if error is not None:
            # 服务端报错：只说明失败原因，不展示签到统计
            rows = [(self.t("checkin_status"), self.t("checkin_status_failed"),
                     CHECKIN_VALUE_MAX_LINES),
                    (self.t("checkin_error"), str(error), CHECKIN_ERROR_MAX_LINES)]
        else:
            rows = [
                (self.t("checkin_status"),
                 self.t("checkin_status_ok") if result["code"] == 0
                 else self.t("checkin_status_already"), CHECKIN_VALUE_MAX_LINES),
                (self.t("checkin_month_days"),
                 self.t("checkin_days", days=result["month_days"]),
                 CHECKIN_VALUE_MAX_LINES),
                (self.t("checkin_streak"),
                 self.t("checkin_days", days=result["streak"]),
                 CHECKIN_VALUE_MAX_LINES),
                (self.t("checkin_reward"), self._reward_text(result),
                 CHECKIN_VALUE_MAX_LINES),
            ]
            if result["event"]:
                rows.append((self.t("checkin_event"), result["event"],
                             CHECKIN_VALUE_MAX_LINES))
        dialog = ft.AlertDialog(
            title=ft.Text(self.t("checkin_title"), size=16),
            content=ft.Container(
                content=ft.Column([self._dialog_row(*row) for row in rows],
                                  spacing=8, tight=True),
                width=CHECKIN_DIALOG_WIDTH, height=CHECKIN_DIALOG_HEIGHT,
                alignment=ft.Alignment.TOP_LEFT),
            title_padding=ft.Padding.only(left=16, right=16, top=12, bottom=0),
            content_padding=ft.Padding.only(left=16, right=16, top=6, bottom=0),
            actions_padding=ft.Padding.only(left=8, right=8, top=0, bottom=6),
            actions=[ft.TextButton(self.t("btn_confirm"),
                                   on_click=lambda e: self._close_checkin_dialog())],
        )
        # 上一次的签到弹窗若还开着先关掉：叠加时 pop_dialog 只关最上面那个，
        # 下面还压着一个同样的弹窗，看起来就是「点了确认退不出去」
        if self.checkin_dialog is not None and self.checkin_dialog.open:
            self.app.page.pop_dialog()
        self.checkin_dialog = dialog
        self.app.page.show_dialog(dialog)

    def _close_checkin_dialog(self):
        """确认：关掉签到弹窗。"""
        self.app.page.pop_dialog()
        self.checkin_dialog = None

    def _reward_text(self, result):
        """当天签到奖励：成功时展示解析到的 J 币 / 经验，否则退回服务端原文。"""
        if result["code"] != 0:
            return self.t("checkin_reward_claimed")
        coin, exp = result["coin"], result["exp"]
        if coin is None and exp is None:
            return result["msg"] or EMPTY_VALUE
        return self.t("checkin_reward_value",
                      coin=_int_text(coin or 0), exp=_int_text(exp or 0))

    @staticmethod
    def _dialog_row(label, value, value_max_lines):
        """一行「标签 + 值」：值超过给定行数就省略，完整内容放在 tooltip 里。"""
        return ft.Column([
            ft.Text(label, size=11, color=ft.Colors.ON_SURFACE_VARIANT, max_lines=1),
            ft.Text(value, size=13, selectable=True, max_lines=value_max_lines,
                    tooltip=value or None, overflow=ft.TextOverflow.ELLIPSIS),
        ], spacing=2, tight=True)

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _on_login(self):
        if self.app.logging_in:
            return
        username = (self.username_field.value or "").strip()
        password = self.password_field.value or ""
        if not username or not password:
            self.app.set_status(self.t("status_login_need_input"), COLOR_ERR)
            return
        self.btn_login.disabled = True
        self.app.login(username, password)
