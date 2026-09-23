# -*- coding: utf-8 -*-
"""本子详情页：左上方更大封面，右上方本子信息，下方操作按钮与「前 5 页」预览。

入口来自探索页点击名称；信息通过 jmcomic 的 get_album_detail 现取。
进入页面即自动取前 5 页预览（取到几张展示几张），预览图点击后可放大查看，
放大后可用两侧按钮在这几张之间翻页。
「浏览」按钮打开在线浏览层（与资源管理器的浏览功能同一套界面）。
"""

import flet as ft

from core import explore
from core.constants import (COLOR_ERR, ROUTE_ALBUM, ROUTE_MAIN,
                            WINDOW_HEIGHT, WINDOW_WIDTH)
from core.downloader import PREVIEW_LIMIT, album_url, fetch_cover, fetch_preview_images
from core.online_reader import OnlineAlbum
from ui.reader_view import ReaderView

COVER_WIDTH = 220
COVER_HEIGHT = 293

# 并排两项（点赞数/观看数、页数/章节数）的排版：左项固定宽度，
# 两行右项的起始位置就一致（观看数与章节数上下对齐）；PAIR_GAP 是两列之间的固定间距
PAIR_LEFT_WIDTH = 88
PAIR_GAP = 72

# 视图自身的内边距（与 ft.View 的 padding 保持一致）
VIEW_PADDING = 12
# 预览图之间的固定间隔
PREVIEW_GAP = 12
# 预览图与内容区右侧之间的留白：一排预览图在初始窗口下左右都不贴边
PREVIEW_MARGIN = 12
# 预览图宽度下限（窗口很窄时也不至于小到看不清）
PREVIEW_MIN_WIDTH = 60
# 预览图宽度：先按初始窗口尺寸规划一排 5 张，实际显示时再按预览区实测宽度算一次
PREVIEW_WIDTH = ((WINDOW_WIDTH - 2 * VIEW_PADDING - PREVIEW_MARGIN
                  - (PREVIEW_LIMIT - 1) * PREVIEW_GAP) // PREVIEW_LIMIT)
# 单张预览图的高度上限（宽高比）：个别长条图不至于把整页撑开
PREVIEW_MAX_RATIO = 0.6
# 预览区宽度的采样间隔（毫秒）：拖动窗口时按此节流
SIZE_INTERVAL = 100
# 放大查看时两侧的翻页按钮：与资源管理器浏览层的翻页按钮同规格
NAV_WIDTH = 46
NAV_GAP = 8
ZOOM_NAV = 2 * NAV_WIDTH + 2 * NAV_GAP
# 放大查看时背景的虚化强度，以及留给关闭按钮的高度
PREVIEW_BLUR = 6
ZOOM_CHROME = 64

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
        self.preview_pages = []          # 已取到的预览图（只留在内存里）
        self.preview_loading = False
        self.browse_loading = False      # 是否正在打开在线浏览
        self.preview_index = 0           # 放大查看时当前显示的是第几张
        self.preview_image_width = 0     # 预览图当前宽度（按预览区实测宽度算）
        self.preview_avail = 0.0         # 预览区实测宽度

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
        self.btn_browse = ft.Button(self.t("btn_browse"), icon=ft.Icons.AUTO_STORIES,
                                    on_click=self._on_browse)
        buttons = ft.Row([
            ft.Button(self.t("btn_open_site"), icon=ft.Icons.OPEN_IN_NEW,
                      url=album_url(self.album_id)),
            ft.Button(self.t("btn_download_now"), icon=ft.Icons.DOWNLOAD,
                      on_click=self._on_download),
            ft.Button(self.t("btn_add_to_queue"), icon=ft.Icons.PLAYLIST_ADD,
                      on_click=self._on_add_queue),
            self.btn_browse,
        ], spacing=10, wrap=True)
        # 预览区：按钮下方那块空白，进页面就自动取前几页填上，未加载时为空容器
        # 挂上尺寸监听：按预览区实测宽度排图，初始窗口下左右留白才均衡
        self.preview_box = ft.Container(size_change_interval=SIZE_INTERVAL,
                                        on_size_change=self._on_preview_area)
        # 放大查看时的翻页按钮：与资源管理器浏览层的翻页按钮同规格，
        # 只在已取到的这几张预览图之间切换，不会再去取新图
        self.zoom_prev = ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_size=36,
                                       tooltip=self.t("btn_prev_page"),
                                       on_click=lambda e: self._turn_zoom(-1))
        self.zoom_next = ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_size=36,
                                       tooltip=self.t("btn_next_page"),
                                       on_click=lambda e: self._turn_zoom(1))
        content = ft.Column([
            ft.Row([self.cover_holder, self.info_col], spacing=16,
                   vertical_alignment=ft.CrossAxisAlignment.START),
            ft.Divider(height=1),
            buttons,
            self.preview_box,
            self.status_text,
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
        # 内容整块模糊变暗由放大预览层控制，因此包一层容器叠在下面
        self.content_box = ft.Container(content=content, left=0, top=0, right=0, bottom=0)
        self.overlay = self._build_overlay()
        # 在线浏览层：与资源管理器的浏览功能同一套界面
        self.reader = ReaderView(app, self.content_box)
        view = ft.View(
            route=ROUTE_ALBUM,
            appbar=ft.AppBar(
                title=ft.Text(self.t("album_title")),
                leading=ft.IconButton(ft.Icons.ARROW_BACK,
                                      on_click=lambda e: app.navigate(ROUTE_MAIN)),
            ),
            controls=[ft.Stack([self.content_box, self.overlay,
                                self.reader.build()], expand=True)],
            padding=VIEW_PADDING,
        )
        self.reader.attach(view)
        app.bind_status(self.status_text)
        app.page.run_thread(self._load)
        self._start_preview()
        return view

    def _cover_placeholder(self):
        return ft.Icon(ft.Icons.BROKEN_IMAGE, size=24,
                       color=ft.Colors.ON_SURFACE_VARIANT,
                       tooltip=self.t("cover_load_failed"))

    def _build_overlay(self):
        """预览图放大层：背景虚化变暗，右上方关闭。

        图片控件在打开预览时才创建：Image 的 src 不能为空，否则会触发客户端校验错误。
        """
        self.zoom_holder = ft.Container(alignment=ft.Alignment.CENTER, expand=True)
        close_btn = ft.IconButton(ft.Icons.CLOSE, icon_size=28,
                                  tooltip=self.t("btn_close"),
                                  on_click=lambda e: self._close_zoom())
        return ft.Container(
            visible=False, left=0, top=0, right=0, bottom=0, padding=16,
            bgcolor=ft.Colors.with_opacity(0.78, ft.Colors.BLACK),
            content=ft.Column([
                ft.Row([close_btn], alignment=ft.MainAxisAlignment.END),
                self.zoom_holder,
            ], spacing=0, expand=True))

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

    # ------------------------------------------------------------------
    # 浏览（在线看本子）
    # ------------------------------------------------------------------
    def _on_browse(self, e=None):
        """打开在线浏览：先取本子信息（要拿总页数），就绪后再开浏览层。"""
        if self.browse_loading:
            return
        self.browse_loading = True
        self.btn_browse.disabled = True
        self.app.set_status(self.t("status_browse_opening"))
        self.app.page.run_thread(self._open_browse)

    def _open_browse(self):
        try:
            doc = OnlineAlbum(self.app.conf, self.album_id)
            error = None
        except Exception as exc:
            doc, error = None, exc
        self.browse_loading = False
        self.btn_browse.disabled = False
        if doc is None:
            self.app.set_status(self.t("browse_open_failed", error=error), COLOR_ERR)
            return
        self.reader.open_doc(doc)

    # ------------------------------------------------------------------
    # 预览前 5 页（进页面自动获取并展示）
    # ------------------------------------------------------------------
    def _start_preview(self):
        """进入详情页就自动取前几页预览；已经在取或已经取到就不重复。"""
        if self.preview_loading or self.preview_pages:
            return
        self.preview_loading = True
        self.preview_box.content = ft.Row([
            ft.ProgressRing(width=20, height=20, stroke_width=2),
            ft.Text(self.t("preview_loading"), size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT),
        ], spacing=10)
        self.app.update()
        self.app.page.run_thread(self._load_preview)

    def _load_preview(self):
        try:
            pages = fetch_preview_images(self.app.conf, self.album_id)
            error = None
        except Exception as exc:
            pages, error = [], exc
        self.preview_loading = False
        if error is not None or not pages:
            text = self.t("preview_failed", error=error)
            self.preview_box.content = ft.Text(text, size=12, color=COLOR_ERR,
                                               selectable=True)
            self.app.set_status(text, COLOR_ERR)
            self.app.update()
            return
        self.preview_pages = pages
        self._render_preview()

    def _render_preview(self, avail=None):
        """把预览图按固定间隔从左到右排开（左端与上方大封面左对齐）。

        avail 是预览区实测宽度；还没量到时按初始窗口尺寸规划。
        """
        self.preview_image_width = self._preview_image_width(avail or self.preview_avail)
        self.preview_box.content = ft.Row(
            [self._preview_item(page, index)
             for index, page in enumerate(self.preview_pages)],
            spacing=PREVIEW_GAP, alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.START)
        self.app.update()

    def _preview_image_width(self, avail=None):
        """按可用宽度算单张预览图宽度：右侧留出与左侧相当的留白，一排 5 张放得下。"""
        if not avail or avail <= 0:
            avail = float(WINDOW_WIDTH - 2 * VIEW_PADDING)
        count = len(self.preview_pages) or PREVIEW_LIMIT
        width = int((avail - PREVIEW_MARGIN - (count - 1) * PREVIEW_GAP) / count)
        return max(PREVIEW_MIN_WIDTH, width)

    def _on_preview_area(self, e):
        """预览区宽度变化（首次显示、拖动窗口）：按实际可用宽度重排预览图。"""
        avail = float(e.width or 0)
        if avail <= 0:
            return
        self.preview_avail = avail        # 先记下来：取图期间就能量到宽，取完直接用
        if not self.preview_pages:
            return
        if self._preview_image_width(avail) == self.preview_image_width:
            return
        self._render_preview(avail)

    def _preview_item(self, page, index):
        """一张预览图：按原图宽高比等比缩放，点击放大查看。"""
        image_w, image_h = page["size"]
        max_height = int(self.preview_image_width / PREVIEW_MAX_RATIO)
        height = min(max_height, max(1, round(self.preview_image_width * image_h / image_w)))
        return ft.GestureDetector(
            content=ft.Image(src=page["data"], width=self.preview_image_width,
                             height=height, fit=ft.BoxFit.CONTAIN, border_radius=4),
            mouse_cursor=ft.MouseCursor.CLICK,
            on_tap=lambda e, i=index: self._open_zoom(i))

    # ------------------------------------------------------------------
    # 放大查看（放大后可在已取到的预览图之间翻页）
    # ------------------------------------------------------------------
    def _open_zoom(self, index):
        self.preview_index = index
        self._render_zoom()
        self.overlay.visible = True
        self.content_box.blur = PREVIEW_BLUR
        self.app.update()

    def _turn_zoom(self, delta):
        """放大层的翻页按钮：在已取到的预览图之间前进 / 后退一张。"""
        index = self.preview_index + delta
        if not 0 <= index < len(self.preview_pages):
            return
        self.preview_index = index
        self._render_zoom()
        self.app.update()

    def _render_zoom(self):
        """放大显示当前预览图，两侧放翻页按钮（规格与浏览层一致）。

        图片按窗口尺寸等比缩放到放得下，并扣掉左右两个翻页按钮占的宽度；
        停在第一张时左按钮消失，停在最后一张时右按钮消失。
        """
        page = self.preview_pages[self.preview_index]
        image_w, image_h = page["size"]
        area_w = (self.app.page.width or WINDOW_WIDTH) - 2 * (VIEW_PADDING + 16) - ZOOM_NAV
        area_h = (self.app.page.height or WINDOW_HEIGHT) - 2 * (VIEW_PADDING + 16) - ZOOM_CHROME
        scale = min(area_w / image_w, area_h / image_h)
        self.zoom_prev.visible = self.preview_index > 0
        self.zoom_next.visible = self.preview_index < len(self.preview_pages) - 1
        self.zoom_holder.content = ft.Row([
            ft.Container(content=self.zoom_prev, width=NAV_WIDTH,
                         alignment=ft.Alignment.CENTER),
            ft.Image(src=page["data"], width=image_w * scale, height=image_h * scale,
                     fit=ft.BoxFit.CONTAIN),
            ft.Container(content=self.zoom_next, width=NAV_WIDTH,
                         alignment=ft.Alignment.CENTER),
        ], spacing=NAV_GAP, alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _close_zoom(self):
        self.overlay.visible = False
        self.content_box.blur = None
        self.zoom_holder.content = None
        self.app.update()
