# -*- coding: utf-8 -*-
"""设置页：配置管理（导入 / 导出）、外观设置、语言设置。

外观与语言均即时生效；语言切换会触发整棵视图树重建，
因此所有界面文本都必须通过 :meth:`AppUI.t` 获取。
"""

import flet as ft

from core.config import conf_path
from core.constants import ROUTE_MAIN, ROUTE_SETTINGS
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

        content = ft.Column([
            config_section,
            appearance_section,
            language_section,
            self.status_text,
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

        view = ft.View(
            route=ROUTE_SETTINGS,
            appbar=ft.AppBar(
                title=ft.Text(t("settings_title")),
                leading=ft.IconButton(ft.Icons.ARROW_BACK,
                                      on_click=lambda e: app.navigate(ROUTE_MAIN)),
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
