# -*- coding: utf-8 -*-
"""本子详情页：左上方更大封面，右上方本子信息，下方三个操作按钮。

入口来自探索页点击名称；信息通过 jmcomic 的 get_album_detail 现取。
"""

import flet as ft

from core import explore
from core.constants import COLOR_ERR, ROUTE_ALBUM, ROUTE_MAIN
from core.downloader import album_url, fetch_cover

COVER_WIDTH = 220
COVER_HEIGHT = 293

# 并排两项（点赞数/观看数、页数/章节数）的排版：左项固定宽度，
# 两行右项的起始位置就一致（观看数与章节数上下对齐）；PAIR_GAP 是两列之间的固定间距
PAIR_LEFT_WIDTH = 88
PAIR_GAP = 72

# 观看数 / 点赞数在站点上可能是纯数字串，也可能是 "1K" / "1.2M" 这类缩写，
# 这里统一格式化成带千位分隔符的纯数字；解析不出来就返回空串（界面显示占位符）
_COUNT_UNITS = {"k": 1000, "m": 1000000}


def _count_text(value):
    """把观看数 / 点赞数格式化成 "200,000" 这样的纯数字文本。"""
    text = str(value or "").strip().replace(",", "").replace(" ", "")
    if text.isdigit():
        return format(int(text), ",")
    unit = text[-1:].lower()
    if len(text) > 1 and unit in _COUNT_UNITS:
        try:
            return format(int(float(text[:-1]) * _COUNT_UNITS[unit]), ",")
        except ValueError:
            return ""
    return ""


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
                                      on_click=lambda e: app.navigate(ROUTE_MAIN)),
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

    def _row_pair(self, left, right):
        """两个「标签 + 数值」并排一行。

        左项宽度固定，因此两行（点赞数/观看数、页数/章节数）的第二列
        起始位置相同，观看数与章节数在竖直方向对齐；
        用于这两组后信息区更矮，高度更贴近左侧的大封面。
        """
        return ft.Row([
            ft.Container(content=self._row(self.t(left[0]), left[1]),
                         width=PAIR_LEFT_WIDTH, alignment=ft.Alignment.TOP_LEFT),
            self._row(self.t(right[0]), right[1]),
        ], spacing=PAIR_GAP, vertical_alignment=ft.CrossAxisAlignment.START)

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
            # 点赞数与观看数并排、页数与章节数并排：信息区更矮，贴近左侧大封面
            self.info_col.controls = [
                self._row(self.t("meta_title"), album.name),
                self._row(self.t("meta_album_id"), str(album.album_id)),
                self._row(self.t("meta_author"), ", ".join(album.authors or [])),
                self._row(self.t("meta_tags"), ", ".join(str(tag) for tag in (album.tags or []))),
                self._row_pair(("meta_likes", _count_text(album.likes)),
                               ("meta_views", _count_text(album.views))),
                self._row_pair(("meta_pages", str(album.page_count)),
                               ("meta_chapters", str(len(album)))),
            ]
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
