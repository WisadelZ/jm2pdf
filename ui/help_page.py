# -*- coding: utf-8 -*-
"""帮助页：版本号、作者署名、项目地址、分发协议、免责声明与 Issue 入口。"""

import flet as ft

from core.constants import (APP_AUTHOR, APP_NAME, APP_VERSION, ISSUES_URL,
                            LICENSE_NAME, LICENSE_URL, PROJECT_URL, ROUTE_HELP,
                            ROUTE_MAIN)


class HelpPage:
    def __init__(self, app):
        self.app = app

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def build_view(self):
        app = self.app
        about_card = self._card(ft.Column([
            self._row(self.t("help_version"), self._value("%s v%s" % (APP_NAME, APP_VERSION))),
            self._row(self.t("help_author"), self._value(APP_AUTHOR)),
            self._row(self.t("help_project"), self._link(PROJECT_URL)),
            self._row(self.t("help_license"), self._link(LICENSE_URL, LICENSE_NAME)),
        ], spacing=10))

        disclaimer_card = self._card(ft.Column([
            ft.Text(self.t("help_disclaimer_title"), size=15, weight=ft.FontWeight.BOLD),
            ft.Text(self.t("help_disclaimer", license=LICENSE_NAME), size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT, selectable=True),
        ], spacing=10))

        # 仅提供跳转链接，软件内不提供直接反馈途径
        issue_card = self._card(ft.Column([
            ft.Text(self.t("help_issue_hint"), size=12),
            ft.Button(self.t("help_issue_link"), icon=ft.Icons.OPEN_IN_NEW, url=ISSUES_URL),
            self._link(ISSUES_URL),
        ], spacing=10))

        content = ft.Column([about_card, disclaimer_card, issue_card], spacing=14,
                            scroll=ft.ScrollMode.AUTO, expand=True)
        view = ft.View(
            route=ROUTE_HELP,
            appbar=ft.AppBar(
                title=ft.Text(self.t("help_title")),
                leading=ft.IconButton(ft.Icons.ARROW_BACK,
                                      on_click=lambda e: app.navigate(ROUTE_MAIN)),
            ),
            controls=[content],
            padding=12,
        )
        return view

    @staticmethod
    def _card(body):
        return ft.Container(
            content=body,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            padding=14,
        )

    @staticmethod
    def _row(label, value):
        return ft.Row([
            ft.Text(label, size=12, width=72, color=ft.Colors.ON_SURFACE_VARIANT),
            value,
        ], spacing=8, wrap=True, vertical_alignment=ft.CrossAxisAlignment.START)

    @staticmethod
    def _value(text):
        return ft.Text(text, size=12, selectable=True)

    @staticmethod
    def _link(url, text=None):
        """可点击的外链文本。"""
        return ft.Text(
            size=12,
            selectable=True,
            spans=[ft.TextSpan(
                text or url, url=url,
                style=ft.TextStyle(color=ft.Colors.PRIMARY,
                                   decoration=ft.TextDecoration.UNDERLINE))])
