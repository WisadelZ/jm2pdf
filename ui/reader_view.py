# -*- coding: utf-8 -*-
"""内置浏览层：叠在资源管理器页上，浏览已下载的 PDF 或图片文件夹。

- 打开后背景模糊变暗，右上角是关闭按钮，关闭后回到资源管理器
- 横式：单页居中显示并随窗口缩放，窗口左右两侧翻页，首/末页隐藏对应按钮
- 竖式：所有页从上到下无缝排列，支持鼠标拖动与滚轮滚动
- 左下角切换横竖式，右下角显示页码（PDF）或图片名（图片文件夹）

图片的像素尺寸由本层按可视区算好后再交给客户端（不依赖布局约束），
可视区大小来自 ``on_size_change``，因此拖动窗口时画面会跟着缩放：
横式是整页等比缩放到放入可视区，竖式是一屏尽量正好放下一页。
"""

import flet as ft

from core import reader as reader_mod
from core.constants import COLOR_ERR, WINDOW_HEIGHT, WINDOW_WIDTH

# 资源管理器视图自身的内边距（计算可视区时要扣掉）
VIEW_PADDING = 12
# 浏览层四周留白
OVERLAY_PADDING = 16
# 背景虚化强度
BLUR = 6
# 翻页按钮的占位宽度：按钮在首/末页隐藏时仍然占位，图片不会左右跳动
NAV_WIDTH = 46
# 上下两排控件（关闭按钮 / 左下切换 + 右下信息）的大致高度，仅用于首次测量前的估算
CHROME_HEIGHT = 96
# 竖式单列宽度：过宽不好读，也避免一屏放不下一页
VERTICAL_MAX_WIDTH = 900
VERTICAL_MIN_WIDTH = 200
# 量不到页面尺寸时的兜底宽高比（A4 纵向）
DEFAULT_ASPECT = 0.707
# 可视区尺寸的采样间隔（毫秒）：拖动窗口时按此节流，避免频繁重排
SIZE_INTERVAL = 100
# 竖式每加载这么多页刷新一次界面：在线本子取一页要 1 秒左右，这里取小一点，
# 让第一屏更快出来，后面继续铺满
VERTICAL_BATCH = 2
# 竖式分段加载：一次只铺这么多页，滚到接近底部再接着铺下一段（页数多时不会一次性卡住）
VERTICAL_SEGMENT = 8
# 打开浏览层前先取这么多页：取到了才亮出界面，避免一进来先看到空白/转圈
PRELOAD_PAGES = 3
# 横式预取窗口：当前页之后预取这么多页（顺序往后翻基本不用等），往前只补少量
HORIZ_PREFETCH = 4
HORIZ_BACK = 2
# 横式最多缓存几页：略大于预取窗口，避免刚取到的页被立刻清掉
HORIZ_CACHE = HORIZ_PREFETCH + HORIZ_BACK + 2


class ReaderView:
    """浏览层：控件在资源管理器页构建时一并创建，打开时才显示。"""

    def __init__(self, app, dim_target):
        self.app = app
        self.dim_target = dim_target      # 打开时要模糊变暗的那块内容
        self.view = None                  # 由资源管理器页在视图建好后回填

        self.doc = None
        self.index = 0                    # 当前页（竖式下由滚动位置推算）
        self.vertical = False
        self.loaded_vertical = False
        self.epoch = 0                    # 会话序号：关闭/换文档作废还在跑的加载
        self.cache = {}                   # 页号 -> 图片字节
        self.sizes = {}                   # 页号 -> (宽, 高)，竖式定位当前页用
        self.pending = set()              # 正在取图的页号
        self.prefetching = False          # 是否已有预取线程在跑
        self.shown = None                 # 横式当前显示的页号
        self.pixels = 0.0                 # 竖式滚动位置
        self.viewport = 0.0               # 竖式可视高度
        self.aspect = DEFAULT_ASPECT      # 首页宽高比：竖式按它推一屏一页的列宽
        self.area = (0.0, 0.0)            # 竖式可视区（由 on_size_change 量得）
        self.image_area = (0.0, 0.0)      # 横式图片区（由 on_size_change 量得）
        self.vert_width = VERTICAL_MAX_WIDTH   # 竖式当前列宽
        self.vert_images = []             # 竖式已铺开的图片控件，列宽变化时统一重算
        self.vert_next = 0                # 竖式下一段要从第几页开始铺
        self.vert_loading = False         # 是否正在铺一段

        self.overlay = None
        self.image_box = None
        self.page_image = None
        self.spinner = None
        self.prev_btn = None
        self.next_btn = None
        self.info_text = None
        self.mode_btn = None
        self.vert_body = None
        self.horiz_layer = None
        self.vert_layer = None

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def build(self):
        """创建浏览层的控件树（初始隐藏），返回最外层容器。"""
        self.spinner = ft.ProgressRing(width=28, height=28, stroke_width=3)
        # 横式：左右两侧固定宽度的翻页按钮，中间是可伸缩的图片区
        # 图片区与竖式可视区都挂 on_size_change：拖动窗口时按量到的尺寸重新缩放图片
        self.image_box = ft.Container(expand=True, alignment=ft.Alignment.CENTER,
                                      size_change_interval=SIZE_INTERVAL,
                                      on_size_change=self._on_image_area_change)
        self.prev_btn = ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_size=36,
                                      tooltip=self.t("btn_prev_page"),
                                      on_click=lambda e: self.turn(-1))
        self.next_btn = ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_size=36,
                                      tooltip=self.t("btn_next_page"),
                                      on_click=lambda e: self.turn(1))
        horiz_row = ft.Row([
            ft.Container(content=self.prev_btn, width=NAV_WIDTH,
                         alignment=ft.Alignment.CENTER),
            self.image_box,
            ft.Container(content=self.next_btn, width=NAV_WIDTH,
                         alignment=ft.Alignment.CENTER),
        ], expand=True, spacing=0, vertical_alignment=ft.CrossAxisAlignment.STRETCH)
        self.horiz_layer = ft.Container(content=horiz_row, left=0, top=0, right=0, bottom=0)

        # 竖式：一列图片整体可滚动。这里用「定位容器 + 可滚动 Column」这套结构，
        # 与本项目探索页的内容区完全一致（该结构已验证可用）。
        # 注意：尺寸监听必须挂在里面的 Column 上，不能挂在定位容器上——
        # 定位容器是 Stack 的孩子，挂监听会让客户端布局报错（表现为一块灰色占位）。
        self.vert_body = ft.Column(spacing=0, expand=True, scroll=ft.ScrollMode.AUTO,
                                   horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                   size_change_interval=SIZE_INTERVAL,
                                   on_scroll=self._on_scroll,
                                   on_size_change=self._on_vert_area_change)
        self.vert_layer = ft.Container(
            content=self.vert_body, left=0, top=0, right=0, bottom=0, visible=False)

        self.mode_btn = ft.IconButton(ft.Icons.SWAP_VERT, icon_size=24,
                                      tooltip=self.t("browse_switch_vertical"),
                                      on_click=self._toggle_mode)
        self.info_text = ft.Text("", size=12, color=ft.Colors.WHITE)
        close_btn = ft.IconButton(ft.Icons.CLOSE, icon_size=28,
                                  tooltip=self.t("btn_close"),
                                  on_click=lambda e: self.close())
        self.overlay = ft.Container(
            visible=False, left=0, top=0, right=0, bottom=0, padding=OVERLAY_PADDING,
            bgcolor=ft.Colors.with_opacity(0.78, ft.Colors.BLACK),
            content=ft.Column([
                ft.Row([close_btn], alignment=ft.MainAxisAlignment.END),
                ft.Stack([self.horiz_layer, self.vert_layer], expand=True),
                ft.Row([self.mode_btn, ft.Container(expand=True), self.info_text],
                       spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=0, expand=True))
        return self.overlay

    def attach(self, view):
        """记下所属视图，用于判断页面是否还在显示（离开页面后停止后台加载）。"""
        self.view = view

    # ------------------------------------------------------------------
    # 打开与关闭
    # ------------------------------------------------------------------
    def open(self, path):
        """打开本地的一个 PDF 或图片文件夹；打不开时把原因写到状态栏。"""
        try:
            doc = reader_mod.Reader(path)
        except reader_mod.ReaderError as exc:
            self.app.set_status(self.t("browse_failed", error=exc), COLOR_ERR)
            return
        self.open_doc(doc)

    def open_doc(self, doc, preload=PRELOAD_PAGES):
        """打开一个已经就绪的数据源（本地文件或在线的本子）。

        只要求 doc 提供 page_count / numbered_pages / name / page_name / size / render。
        先取到首批图片再亮出界面：在线本子取一页要一秒左右，
        否则一进来先是空白，切竖式时也看不到内容。
        """
        self.close()
        self.doc = doc
        self.index = 0
        self.vertical = False
        self.loaded_vertical = False
        self.epoch += 1
        self.cache = {}
        self.sizes = {}
        self.pending = set()
        self.prefetching = False
        self.shown = None
        self.pixels = 0.0
        self.area = (0.0, 0.0)
        self.image_area = (0.0, 0.0)
        self.vert_images = []
        self.vert_body.controls = []
        self.vert_next = 0
        self.vert_loading = False
        self._preload(doc, preload)
        # 首页尺寸要等取到图才知道，放在预取之后：竖式列宽按真实比例推一屏一页
        self.aspect = self._page_aspect(doc, 0)
        self.vert_width = self._vertical_width()
        self._apply_mode()
        self.overlay.visible = True
        self.dim_target.blur = BLUR
        self.app.set_status(self.t("status_browsing", name=doc.name))
        self._render_current()

    def _preload(self, doc, count):
        """先把前几页取到缓存里，界面亮出来时就有内容可看。"""
        for index in range(min(count, doc.page_count)):
            try:
                self.cache[index] = doc.render(index)
                self.sizes[index] = doc.size(index)
            except Exception:
                break          # 首批都取不到就别继续等了，交给界面按需再取并提示

    def close(self, e=None):
        """关闭浏览层：停掉还在跑的加载，恢复背景。"""
        self.epoch += 1                   # 作废后台加载线程
        if self.overlay is None:
            return
        self.overlay.visible = False
        self.dim_target.blur = None
        self.image_box.content = None
        self.page_image = None
        self.shown = None
        self.vert_body.controls = []
        self.vert_images = []
        self.vert_next = 0
        self.vert_loading = False
        self.info_text.value = ""
        # 只丢掉引用：仍在取页的线程自己持着文档对象，句柄不会被提前关掉
        self.doc = None
        self.cache = {}
        self.sizes = {}
        self.pending = set()
        self.prefetching = False
        self.app.update()

    def _alive(self, epoch):
        """页面还在显示、且仍是同一次会话时才继续加载。"""
        if epoch != self.epoch:
            return False
        views = self.app.page.views
        return bool(views) and views[-1] is self.view

    # ------------------------------------------------------------------
    # 可视区尺寸：图片大小全部由这里算出来
    # ------------------------------------------------------------------
    def _window_size(self):
        """窗口尺寸；只有整页预览用得到，取不到时退回默认窗口尺寸。"""
        page = self.app.page
        width = float(page.width or 0) or float(page.window.width or WINDOW_WIDTH)
        height = float(page.height or 0) or float(page.window.height or WINDOW_HEIGHT)
        return width, height

    def _estimate_area(self, drop=0.0):
        """还没量到可视区时的估算值（按窗口尺寸扣掉四周留白与上下两排控件）。"""
        width, height = self._window_size()
        return (max(1.0, width - 2 * (VIEW_PADDING + OVERLAY_PADDING) - drop),
                max(1.0, height - 2 * (VIEW_PADDING + OVERLAY_PADDING) - CHROME_HEIGHT))

    def _vertical_width(self):
        """竖式单列宽度：一页的高度尽量接近可视区高度，即一屏约一页。"""
        area_w, area_h = self.area if self.area[0] else self._estimate_area()
        return max(VERTICAL_MIN_WIDTH,
                   min(VERTICAL_MAX_WIDTH, area_w - 8, area_h * self.aspect))

    def _on_vert_area_change(self, e):
        """竖式可视区变化（首次显示、拖动窗口）：重算列宽并让已铺开的图片跟着缩放。"""
        self.area = (float(e.width or 0), float(e.height or 0))
        self._apply_vertical_width()

    def _apply_vertical_width(self):
        """列宽变化：已铺开的图片按新列宽重算尺寸，整列跟着变宽变窄。"""
        width = self._vertical_width()
        if width == self.vert_width:
            return
        self.vert_width = width
        for image in self.vert_images:
            image.width, image.height = self._vertical_size(image.data)
        self.app.update()

    def _on_image_area_change(self, e):
        """横式图片区变化：当前页按新尺寸重新等比缩放。"""
        self.image_area = (float(e.width or 0), float(e.height or 0))
        if not self.vertical and self.page_image is not None:
            self._fit_horizontal()
            self.app.update()

    def _page_aspect(self, doc, index):
        """页面的宽高比；量不到时用兜底值。"""
        try:
            width, height = doc.size(index)
            return width / height if height else DEFAULT_ASPECT
        except Exception:
            return DEFAULT_ASPECT

    def _fit_horizontal(self):
        """把当前页等比缩放到刚好放进图片区（窗口变化时重算）。"""
        if self.page_image is None or self.doc is None:
            return
        area_w, area_h = self.image_area if self.image_area[0] else self._estimate_area(
            2 * NAV_WIDTH)
        try:
            image_w, image_h = self.doc.size(self.index)
        except Exception:
            # 量不到原图尺寸时不指定尺寸，交给客户端按容器自适应
            self.page_image.width = None
            self.page_image.height = None
            return
        scale = min(area_w / image_w, area_h / image_h)
        self.page_image.width = max(1.0, image_w * scale)
        self.page_image.height = max(1.0, image_h * scale)

    # ------------------------------------------------------------------
    # 横式 / 竖式
    # ------------------------------------------------------------------
    def _apply_mode(self):
        self.horiz_layer.visible = not self.vertical
        self.vert_layer.visible = self.vertical
        self.mode_btn.icon = ft.Icons.SWAP_HORIZ if self.vertical else ft.Icons.SWAP_VERT
        self.mode_btn.tooltip = self.t("browse_switch_horizontal" if self.vertical
                                       else "browse_switch_vertical")

    def _toggle_mode(self, e=None):
        if self.doc is None:
            return
        self.vertical = not self.vertical
        self._apply_mode()
        if self.vertical:
            # 竖式总是从第一页开始往下铺，页码也从第一页算起（之后由滚动位置决定）
            self.index = 0
            self.pixels = 0.0
            self._apply_vertical_width()
            self._ensure_vertical()
        else:
            # 切回横式时停在竖式最后看到的页码上
            self._render_current()
        self._refresh_info()
        self.app.update()

    def _ensure_vertical(self):
        """竖式内容按需加载：第一次切到竖式时铺第一段，之后滚到底自动续铺。"""
        if self.loaded_vertical:
            return
        self.loaded_vertical = True
        self.vert_body.controls = []
        self.vert_images = []
        self.vert_next = 0
        self.vert_loading = False
        self._load_segment()

    def _load_segment(self):
        """分段铺页：一次只取 VERTICAL_SEGMENT 页，页数多时不会一次性卡住界面。"""
        doc = self.doc
        if doc is None or self.vert_loading or self.vert_next >= doc.page_count:
            return
        start = self.vert_next
        end = min(doc.page_count, start + VERTICAL_SEGMENT)
        self.vert_next = end
        self.vert_loading = True
        self.app.page.run_thread(self._load_vertical, doc, start, end, self.epoch)

    def _load_vertical(self, doc, start, end, epoch):
        pending = []
        for index in range(start, end):
            if not self._alive(epoch):
                break
            data = self.cache.get(index)      # 横式取过的页直接复用，不再重复取
            try:
                if data is None:
                    data = doc.render(index)
                size = self.sizes.get(index) or doc.size(index)
            except Exception as exc:
                # 取不出来的页给一个等高的占位块：跳过会让后面的页码与滚动位置整体前移
                self.sizes[index] = self._placeholder_size()
                pending.append(self._error_tile(index, exc))
                if len(pending) >= VERTICAL_BATCH:
                    self._flush_vertical(pending, epoch)
                continue
            self.cache[index] = data
            self.sizes[index] = size
            pending.append(ft.Image(data=index, src=data, fit=ft.BoxFit.CONTAIN))
            if len(pending) >= VERTICAL_BATCH:
                self._flush_vertical(pending, epoch)
        self._flush_vertical(pending, epoch)
        # 这一段铺完才允许续铺下一段：否则两段同时入列会把页序打乱
        self.vert_loading = False

    def _placeholder_size(self):
        """取不到的页用的占位尺寸：按首页的宽高比，占位块与正常页一样高。"""
        aspect = self.aspect or DEFAULT_ASPECT
        return (1000, max(1, int(1000 / aspect)))

    def _error_tile(self, index, error):
        """竖式里取不到的页：显示一个占位块，标出页号与原因。"""
        width, height = self._vertical_size(index)
        return ft.Container(
            data=index, width=width, height=height,
            bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
            alignment=ft.Alignment.CENTER,
            content=ft.Text("%d/%d\n%s" % (index + 1, self.doc.page_count, error),
                            size=12, color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                            text_align=ft.TextAlign.CENTER))

    def _vertical_size(self, index):
        """竖式里一页的显示尺寸：宽固定为列宽，高按该页宽高比算出来。

        宽高都给全（不依赖客户端从原图推高度），否则列表项高度可能算错，整列就铺不开。
        """
        width = self.vert_width
        size = self.sizes.get(index)
        aspect = (size[0] / size[1]) if size and size[1] else self.aspect
        return width, width / aspect

    def _flush_vertical(self, pending, epoch):
        if not pending or not self._alive(epoch):
            return
        # 入列前统一按当前列宽对齐，避免加载途中改过窗口后新旧图片尺寸不一致
        for image in pending:
            image.width, image.height = self._vertical_size(image.data)
        self.vert_images.extend(pending)
        self.vert_body.controls.extend(pending)
        del pending[:]
        self.app.update()

    def _on_scroll(self, e):
        """竖式滚动：更新右下角页码，滚到接近底部时接着铺下一段。"""
        self.pixels = float(e.pixels or 0)
        self.viewport = float(e.viewport_dimension or 0)
        index = self._visible_index()
        if index is not None and index != self.index:
            self.index = index
            self._refresh_info()
            self.app.update()
        limit = float(e.max_scroll_extent or 0)
        if self.pixels + self.viewport >= limit - self.viewport:
            self._load_segment()

    def _visible_index(self):
        """用已加载页面的像素高度累加，找出视口中心落在哪一页。"""
        if not self.sizes:
            return None
        center = self.pixels + self.viewport / 2
        width = float(self.vert_width)
        offset = 0.0
        last = 0
        for index in sorted(self.sizes):
            page_width, page_height = self.sizes[index]
            height = width * page_height / page_width
            if center < offset + height:
                return index
            offset += height
            last = index
        return last

    # ------------------------------------------------------------------
    # 取图与翻页
    # ------------------------------------------------------------------
    def turn(self, delta):
        """横式翻页：delta 为 -1 上一页、1 下一页。"""
        doc = self.doc
        if doc is None or self.vertical:
            return
        index = self.index + delta
        if not 0 <= index < doc.page_count:
            return
        self.index = index
        self._render_current()

    def _render_current(self):
        """显示当前页；没缓存就放进后台线程去取。

        取图期间保留上一页画面（只有还没显示过任何图时才显示转圈），
        否则快速翻页会变成「图片—空白—图片」的闪烁。
        """
        doc = self.doc
        if doc is None:
            return
        data = self.cache.get(self.index)
        if data is None:
            self._refresh_nav()
            self._refresh_info()
            if self.page_image is None:
                self.image_box.content = self.spinner
            self.app.update()
            self._request(doc, self.index)
            return
        self._show(data)
        self._start_prefetch(doc, self.index)   # 命中缓存时也要把后面几页续上

    def _request(self, doc, index):
        if index in self.pending:
            return
        self.pending.add(index)
        self.app.page.run_thread(self._load_page, doc, index, self.epoch)

    def _start_prefetch(self, doc, index):
        """把当前页之后几页预取到缓存：横式顺序往下翻时就不用等。"""
        if self.prefetching or not self._alive(self.epoch):
            return
        missing = [index + step for step in range(1, HORIZ_PREFETCH + 1)
                   if 0 <= index + step < doc.page_count and index + step not in self.cache]
        if not missing:
            return                       # 预取窗口已经备满，不必再起线程
        self.prefetching = True
        self.app.page.run_thread(self._prefetch, doc, index, self.epoch)

    def _prefetch(self, doc, index, epoch):
        """按窗口预取：先取当前页之后几页，再补前面少量（往回翻比较少见）。"""
        try:
            offsets = list(range(1, HORIZ_PREFETCH + 1))
            offsets += [-step for step in range(1, HORIZ_BACK + 1)]
            for offset in offsets:
                if not self._alive(epoch):
                    return
                target = index + offset
                if not 0 <= target < doc.page_count or target in self.cache:
                    continue
                try:
                    self.cache[target] = doc.render(target)
                    self.sizes[target] = doc.size(target)
                except Exception:
                    return               # 取不到就先停，别一直占着网络
            self._trim_cache()
            self._show_if_ready()
        finally:
            self.prefetching = False

    def _load_page(self, doc, index, epoch):
        error = None
        try:
            data = doc.render(index)
        except Exception as exc:
            data, error = None, exc
        self.pending.discard(index)
        if not self._alive(epoch):
            return
        if data is not None:
            self.cache[index] = data
            try:
                self.sizes[index] = doc.size(index)
            except Exception:
                pass
        if index == self.index and not self.vertical:
            if data is None:
                self._show_error(error)
            else:
                self._show(data)
        self._trim_cache()
        self._show_if_ready()
        self._start_prefetch(doc, self.index)   # 继续把后面的页补上

    def _show(self, data):
        """把图片填进横式的图片区（控件复用，只换 src），并按可视区定好尺寸。

        gapless_playback：换图时客户端先保留上一帧，解码完再替换，
        快速翻页不会出现短暂空白。
        """
        if self.page_image is None:
            self.page_image = ft.Image(src=data, fit=ft.BoxFit.CONTAIN,
                                       gapless_playback=True)
            self.image_box.content = self.page_image
        else:
            self.page_image.src = data
            if self.image_box.content is not self.page_image:
                self.image_box.content = self.page_image
        self._fit_horizontal()
        self.shown = self.index
        self._refresh_nav()
        self._refresh_info()
        self.app.update()

    def _show_if_ready(self):
        """预取完成后，如果用户已经翻到有缓存的那页，直接补上。"""
        if self.vertical or self.shown == self.index:
            return
        data = self.cache.get(self.index)
        if data is not None:
            self._show(data)

    def _show_error(self, error):
        self.shown = None
        self.image_box.content = ft.Text(
            "%s\n%s" % (self.t("browse_render_failed"), error),
            size=13, color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
            text_align=ft.TextAlign.CENTER)
        self._refresh_nav()
        self.app.update()

    def _trim_cache(self):
        """横式只留当前页附近的若干页（保留整个预取窗口，避免刚取到就被清掉）。"""
        if self.vertical or len(self.cache) <= HORIZ_CACHE:
            return
        keep = {self.index + offset
                for offset in range(-HORIZ_BACK - 1, HORIZ_PREFETCH + 1)}
        for index in list(self.cache):
            if index not in keep:
                del self.cache[index]
                if len(self.cache) <= HORIZ_CACHE:
                    break

    def _refresh_nav(self):
        total = self.doc.page_count if self.doc is not None else 0
        self.prev_btn.visible = self.index > 0
        self.next_btn.visible = self.index < total - 1

    def _refresh_info(self):
        """右下角：按页编号的数据源显示「当前页/总页数」，否则显示当前图片名。"""
        if self.doc is None:
            self.info_text.value = ""
        elif getattr(self.doc, "numbered_pages", False):
            self.info_text.value = "%d/%d" % (self.index + 1, self.doc.page_count)
        else:
            self.info_text.value = self.doc.page_name(self.index)
