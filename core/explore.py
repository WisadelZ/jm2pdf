# -*- coding: utf-8 -*-
"""探索层：按关键词搜索本子（全部 / 作品 / 作者 / 标签 / 角色），支持服务端排序与时间筛选。

搜索走 jmcomic 的站内搜索接口，库每页最多返回 80 条
（``JmModuleConfig.PAGE_SIZE_SEARCH``），界面自行切分为 20 条一页。
列表项只带 id / name / author / description / category，
页数、章节数、标签等信息需要再调 ``get_album_detail`` 获取。
"""

import jmcomic

from core.downloader import build_option

# 搜索方式 -> jmcomic 客户端方法名（依次对应 main_tag 0~4）
SEARCH_MODES = {
    "all": "search_site",         # 全部（站内搜索：作品 / 作者 / 标签 / 角色一起搜）
    "work": "search_work",        # 作品
    "author": "search_author",    # 作者
    "tag": "search_tag",          # 标签
    "actor": "search_actor",      # 角色
}

DEFAULT_MODE = "all"

# 排序方式 -> 站点排序参数（服务端排序；客户端不提供「最旧」这类升序参数）
SORT_MODES = {
    "latest": jmcomic.JmMagicConstants.ORDER_BY_LATEST,      # 最新
    "views": jmcomic.JmMagicConstants.ORDER_BY_VIEW,         # 观看数
    "pictures": jmcomic.JmMagicConstants.ORDER_BY_PICTURE,   # 图片数
    "likes": jmcomic.JmMagicConstants.ORDER_BY_LIKE,         # 点赞数
}

DEFAULT_SORT = "latest"

# 时间筛选 -> 站点时间参数（排序菜单里的「按日期筛选」）
TIME_MODES = {
    "today": jmcomic.JmMagicConstants.TIME_TODAY,    # 今天
    "week": jmcomic.JmMagicConstants.TIME_WEEK,      # 本周
    "month": jmcomic.JmMagicConstants.TIME_MONTH,    # 本月
    "all": jmcomic.JmMagicConstants.TIME_ALL,        # 全部时间
}

DEFAULT_TIME = "all"

# 库每页返回的条数（与 JmModuleConfig.PAGE_SIZE_SEARCH 一致）
LIB_PAGE_SIZE = 80


def new_client(conf):
    """按当前配置创建一个 jmcomic 客户端，可重复使用（内部自带 cookies 与域名缓存）。"""
    return build_option(conf).new_jm_client()


def search(client, mode, keyword, page=1, sort=DEFAULT_SORT, time=DEFAULT_TIME):
    """按指定方式、排序与时间范围搜索一页，返回 JmSearchPage。

    关键词支持站内语法：``+词`` 必须包含、``-词`` 必须排除。
    排序与时间筛选都由服务端完成（order_by / time 参数），因此界面不要也不该再对
    结果做本地排序，否则会打乱跨页顺序。搜索纯数字车号时，jmcomic 会自动返回单本结果。
    """
    method = getattr(client, SEARCH_MODES.get(mode, SEARCH_MODES[DEFAULT_MODE]))
    return method(keyword, page,
                  order_by=SORT_MODES.get(sort, SORT_MODES[DEFAULT_SORT]),
                  time=TIME_MODES.get(time, TIME_MODES[DEFAULT_TIME]))


def to_items(page):
    """把搜索结果页 / 收藏列表页转成界面用的条目列表（不含封面，封面按需另取）。

    两类页面都遵循 jmcomic 的 ``JmPageContent`` 结构（``content`` 为
    ``(本子 id, 信息字典)`` 列表），因此可以共用这一份转换。
    """
    items = []
    for album_id, info in page.content:
        items.append({
            "id": str(album_id),
            "name": info.get("name") or "",
            "author": info.get("author") or "",
            "cover": None,
        })
    return items
