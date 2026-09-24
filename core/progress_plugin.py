# -*- coding: utf-8 -*-
"""下载进度插件：把 jmcomic 的下载钩子转成进度事件上报给任务队列。

模块导入时会向 jmcomic 注册插件，因此必须早于 ``create_option_by_str`` 被导入
（由 ``core.downloader`` 顶部触发）。插件挂在 ``plugins`` 的 before_album /
before_photo / before_image / after_image / after_photo / after_album 六个分组上，
由 :func:`core.downloader.build_option` 在传入 ``progress=True`` 时自动注入。

两条硬约束（都是读 jmcomic 源码确认的）：

- ``JmOption.call_all_plugin`` 默认会吞掉插件异常（``safe=True``），所以这里所有
  回调都必须自己兜住异常，绝不能向外抛 —— 否则只会看到「下载正常、进度不动」；
- 暂停 / 取消只能通过给实体置 ``skip = True`` 实现（jmcomic 明确说明该字段
  「可供外界控制」，见 ``jm_entity.DetailEntity.skip``）；抛异常会被下载器
  的 ``catch_exception`` 记成「下载失败」，把任务误标为失败。
"""

import logging
import threading

import jmcomic

# 插件 key 前缀：conf.yml 中 plugins 各钩子分组下填完整的 key
PLUGIN_PREFIX = "jm2pdf_progress"

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_sinks = {}          # album_id(str) -> ProgressSink


class ProgressSink:
    """进度接收器：由任务队列实现，插件只负责把事件转交过来。

    - 每个方法都必须保证不抛异常，否则会被 jmcomic 的插件调度吞掉；
    - 返回 True 表示请求跳过（暂停 / 取消），插件据此给实体置 ``skip``；
    - 钩子运行在 jmcomic 的图片 / 章节线程池里，实现方需自行保证线程安全。
    """

    def on_album_start(self, album) -> bool:
        """本子即将开始下载（此时能拿到名称与总页数）。"""
        return False

    def on_photo(self, photo) -> bool:
        """章节即将开始下载（用作进度心跳与中止检查）。"""
        return False

    def on_image_start(self, image) -> bool:
        """单张图片即将开始下载（中止检查）。"""
        return False

    def on_image_done(self, image) -> None:
        """单张图片下载完成（含命中缓存而跳过的图片）。"""
        return None

    def on_photo_done(self, photo) -> None:
        """章节下载完成。"""
        return None

    def on_album_end(self, album) -> None:
        """本子下载结束（部分失败时也会触发）。"""
        return None


def bind_sink(album_id, sink):
    """给某个本子绑定进度接收器（任务开始前调用）。"""
    with _lock:
        _sinks[str(album_id)] = sink


def unbind_sink(album_id):
    """解绑（任务结束后调用，避免长时间持有引用）。"""
    with _lock:
        _sinks.pop(str(album_id), None)


def _current_sink():
    """按当前任务上下文里的本子 ID 找接收器；找不到返回 None。"""
    try:
        jm_id = str(jmcomic.get_jm_task_context().get("jm_id") or "")
    except Exception:
        return None
    if not jm_id:
        return None
    with _lock:
        return _sinks.get(jm_id)


class _ProgressPlugin(jmcomic.JmOptionPlugin):
    """进度插件的公共部分：只负责兜异常与解引用。"""

    plugin_dependencies = ()

    def invoke(self, album=None, photo=None, image=None, downloader=None, **kwargs):
        sink = _current_sink()
        if sink is None:
            return
        try:
            self.dispatch(sink, album, photo, image)
        except Exception:      # 进度上报绝不能影响下载主流程
            logger.debug("进度上报失败: %s", self.plugin_key, exc_info=True)

    def dispatch(self, sink, album, photo, image):
        raise NotImplementedError


class AlbumStartPlugin(_ProgressPlugin):
    plugin_key = PLUGIN_PREFIX + "_album_start"

    def dispatch(self, sink, album, photo, image):
        if album is not None and sink.on_album_start(album):
            album.skip = True


class AlbumEndPlugin(_ProgressPlugin):
    plugin_key = PLUGIN_PREFIX + "_album_end"

    def dispatch(self, sink, album, photo, image):
        if album is not None:
            sink.on_album_end(album)


class PhotoStartPlugin(_ProgressPlugin):
    plugin_key = PLUGIN_PREFIX + "_photo_start"

    def dispatch(self, sink, album, photo, image):
        if photo is not None and sink.on_photo(photo):
            photo.skip = True


class PhotoDonePlugin(_ProgressPlugin):
    plugin_key = PLUGIN_PREFIX + "_photo_done"

    def dispatch(self, sink, album, photo, image):
        if photo is not None:
            sink.on_photo_done(photo)


class ImageStartPlugin(_ProgressPlugin):
    plugin_key = PLUGIN_PREFIX + "_image_start"

    def dispatch(self, sink, album, photo, image):
        if image is not None and sink.on_image_start(image):
            image.skip = True


class ImageDonePlugin(_ProgressPlugin):
    plugin_key = PLUGIN_PREFIX + "_image_done"

    def dispatch(self, sink, album, photo, image):
        if image is not None:
            sink.on_image_done(image)


# 钩子分组 -> 插件 key：build_option 注入进度插件时按这张表填 plugins
PLUGIN_KEYS = {
    "before_album": AlbumStartPlugin.plugin_key,
    "after_album": AlbumEndPlugin.plugin_key,
    "before_photo": PhotoStartPlugin.plugin_key,
    "after_photo": PhotoDonePlugin.plugin_key,
    "before_image": ImageStartPlugin.plugin_key,
    "after_image": ImageDonePlugin.plugin_key,
}


for _plugin in (AlbumStartPlugin, AlbumEndPlugin, PhotoStartPlugin,
                PhotoDonePlugin, ImageStartPlugin, ImageDonePlugin):
    jmcomic.JmModuleConfig.register_plugin(_plugin)
