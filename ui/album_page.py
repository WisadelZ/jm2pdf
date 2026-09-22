# -*- coding: utf-8 -*-
"""本子详情页：左上方更大封面，右上方本子信息，下方三个操作按钮。

入口来自探索页点击名称；信息通过 jmcomic 的 get_album_detail 现取。
"""

import flet as ft

from core import explore
from core.constants import COLOR_ERR, ROUTE_ALBUM, ROUTE_EXPLORE
from core.downloader import album_url, fetch_cover

COVER_WIDTH = 220
COVER_HEIGHT = 293


class AlbumPage:
    def __init__(self, app):
        self.app = app
        self.album_id = ""

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def build_view(self):
        app = self.app
        self.album_id = str(app.detail_album_id or "")
        self.status_text = ft.Text(app.status_text_value, size=12, color=app.status_color)
        # 封面控件在拿到图片字节后再创建：Image 的 src 不能为空，否则会触发客户端校验错误
        self.cover_holder = ft.Container(
            width=COVER_WIDTH, height=COVER_HEIGHT, border_radius=6,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            alignment=ft.Alignment.CENTER, content=self._cover_placeholder())
        self.info_col = ft.Column([
            ft.Text(self.t("album_loading"), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
        ], spacing=10, expand=True)
        buttons = ft.Row([
            ft.Button(self.t("btn_open_site"), icon=ft.Icons.OPEN_IN_NEW,
                      url=album_url(self.album_id)),
            ft.Button(self.t("btn_download_now"), icon=ft.Icons.DOWNLOAD,
                      on_click=self._on_download),
            ft.Button(self.t("btn_add_to_queue"), icon=ft.Icons.PLAYLIST_ADD,
                      on_click=self._on_add_queue),
        ], spacing=10, wrap=True)
        content = ft.Column([
            ft.Row([self.cover_holder, self.info_col], spacing=16,
                   vertical_alignment=ft.CrossAxisAlignment.START),
            ft.Divider(height=1),
            buttons,
            self.status_text,
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
        view = ft.View(
            route=ROUTE_ALBUM,
            appbar=ft.AppBar(
                title=ft.Text(self.t("album_title")),
                leading=ft.IconButton(ft.Icons.ARROW_BACK,
                                      on_click=lambda e: app.navigate(ROUTE_EXPLORE)),
            ),
            controls=[content],
            padding=12,
        )
        app.bind_status(self.status_text)
        app.page.run_thread(self._load)
        return view

    def _cover_placeholder(self):
        return ft.Icon(ft.Icons.BROKEN_IMAGE, size=24,
                       color=ft.Colors.ON_SURFACE_VARIANT,
                       tooltip=self.t("cover_load_failed"))

    def _row(self, label, value):
        return ft.Column([
            ft.Text(label, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(value or "—", size=12, selectable=True),
        ], spacing=2)

    # ------------------------------------------------------------------
    # 取详情
    # ------------------------------------------------------------------
    def _load(self):
        try:
            client = explore.new_client(self.app.conf)
            album = client.get_album_detail(self.album_id)
            cover = fetch_cover(album.album_id)
            if cover:
                self.cover_holder.content = ft.Image(
                    src=cover, width=COVER_WIDTH, height=COVER_HEIGHT,
                    fit=ft.BoxFit.COVER, border_radius=6)
            rows = (
                ("meta_title", album.name),
                ("meta_album_id", str(album.album_id)),
                ("meta_author", ", ".join(album.authors or [])),
                ("meta_tags", ", ".join(str(tag) for tag in (album.tags or []))),
                ("meta_pages", str(album.page_count)),
                ("meta_chapters", str(len(album))),
            )
            self.info_col.controls = [self._row(self.t(key), value) for key, value in rows]
        except Exception as exc:
            self.info_col.controls = [ft.Text(self.t("album_load_failed", error=exc),
                                              size=12, color=COLOR_ERR, selectable=True)]
        self.app.update()

    # ------------------------------------------------------------------
    # 操作
    # ------------------------------------------------------------------
    def _on_download(self, e):
        self.app.download_ids([self.album_id])

    def _on_add_queue(self, e):
        self.app.append_ids([self.album_id])
