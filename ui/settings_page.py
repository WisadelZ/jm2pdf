# -*- coding: utf-8 -*-
# Copyright (C) 2026 WisadelZ
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""设置页：配置管理（导入 / 导出）、外观设置、语言设置、账号设置。

外观、语言与账号设置均即时生效；语言切换会触发整棵视图树重建，
因此所有界面文本都必须通过 :meth:`AppUI.t` 获取。
"""

import flet as ft

from core.config import conf_path
from core.constants import APPBAR_LEADING_WIDTH, COLOR_OK, ROUTE_SETTINGS
from utils.i18n import LANGUAGE_NAMES, LANGUAGES


class SettingsPage:
    def __init__(self, app):
        self.app = app

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def build_view(self):
        app = self.app
        t = self.t

        self.status_text = ft.Text(app.status_text_value, size=12, color=app.status_color)

        # ---- 配置管理 ----
        config_section = self._section(
            t("section_config"), t("desc_config"),
            ft.Column([
                ft.Row([
                    ft.Button(t("btn_export_conf"), on_click=self._on_export),
                    ft.Button(t("btn_import_conf"), on_click=self._on_import),
                ], spacing=12),
                ft.Text(t("label_conf_path", path=conf_path()), size=11,
                        color=ft.Colors.ON_SURFACE_VARIANT, selectable=True),
            ], spacing=12),
        )

        # ---- 外观设置 ----
        self.theme_group = ft.RadioGroup(
            value=self._current_theme_mode(),
            on_change=self._on_theme_change,
            content=ft.Row([
                ft.Radio(value="light", label=t("theme_light")),
                ft.Radio(value="dark", label=t("theme_dark")),
                ft.Radio(value="system", label=t("theme_system")),
            ], spacing=8, wrap=True),
        )
        appearance_section = self._section(
            t("section_appearance"), t("desc_appearance"), self.theme_group)

        # ---- 语言设置 ----
        self.lang_group = ft.RadioGroup(
            value=app.i18n.language,
            on_change=self._on_language_change,
            content=ft.Row([
                ft.Radio(value=lang, label=LANGUAGE_NAMES[lang]) for lang in LANGUAGES
            ], spacing=8, wrap=True),
        )
        language_section = self._section(
            t("section_language"), t("desc_language"), self.lang_group)

        # ---- 账号设置 ----
        self.auto_login_switch = ft.Switch(
            label=t("switch_auto_login"),
            value=bool(app.conf["app"].get("auto_login", False)),
            on_change=self._on_auto_login_change)
        account_section = self._section(
            t("section_account"), t("desc_account"), self.auto_login_switch)

        # ---- 缓存管理 ----
        cache_section = self._section(
            t("section_cache"), t("desc_cache"),
            ft.Row([ft.Button(t("btn_clear_cache"), icon=ft.Icons.DELETE_SWEEP,
                              on_click=self._on_clear_cache)], spacing=12),
        )

        content = ft.Column([
            config_section,
            appearance_section,
            language_section,
            account_section,
            cache_section,
            self.status_text,
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

        view = ft.View(
            route=ROUTE_SETTINGS,
            appbar=ft.AppBar(
                title=ft.Text(t("settings_title")),
                leading=app.nav_leading(),
                leading_width=APPBAR_LEADING_WIDTH,
            ),
            controls=[content],
            padding=12,
        )
        app.bind_status(self.status_text)
        return view

    @staticmethod
    def _section(title, description, body):
        return ft.Container(
            content=ft.Column([
                ft.Text(title, size=15, weight=ft.FontWeight.BOLD),
                ft.Text(description, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                body,
            ], spacing=10),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            padding=14,
        )

    def _current_theme_mode(self):
        mode = str(self.app.conf["app"].get("theme_mode") or "dark").lower()
        return mode if mode in ("light", "dark", "system") else "dark"

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    async def _on_export(self, e):
        await self.app.export_conf()

    async def _on_import(self, e):
        await self.app.import_conf()

    def _on_theme_change(self, e):
        mode = self.theme_group.value
        if mode:
            self.app.apply_theme(mode)

    def _on_language_change(self, e):
        language = self.lang_group.value
        if language and language != self.app.i18n.language:
            self.app.apply_language(language)

    def _on_clear_cache(self, e):
        """清除运行期间产生的内存缓存（不退出登录、不影响配置与下载任务）。"""
        self.app.clear_cache()

    def _on_auto_login_change(self, e):
        """自动登录开关：立即写盘，下次启动生效。"""
        enabled = bool(self.auto_login_switch.value)
        self.app.conf["app"]["auto_login"] = enabled
        self.app.flush_conf()
        self.app.set_status(
            self.t("status_auto_login_on" if enabled else "status_auto_login_off"),
            COLOR_OK)
