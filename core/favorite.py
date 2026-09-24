# -*- coding: utf-8 -*-
"""收藏层：读取当前登录账号的收藏列表，以及收藏 / 取消收藏。

收藏接口依赖登录态，客户端由 :func:`core.downloader.build_option` 注入登录凭据后
自动带上 cookies；库每页返回 20 条（``JmModuleConfig.PAGE_SIZE_FAVORITE``），
与界面每页条数一致，因此不需要再做页内切分。
"""

from core import explore
from core.downloader import build_option

# 库每页返回的条数（与 JmModuleConfig.PAGE_SIZE_FAVORITE 一致）
LIB_PAGE_SIZE = 20

# 「全部」收藏夹的 id：读取时表示不按收藏夹筛选，收藏时表示加入默认收藏夹
FOLDER_ALL = "0"

# 账号页预览的收藏条数：默认窗口宽度下正好 4 本一行、两行
PREVIEW_COUNT = 8


def new_client(conf):
    """按当前配置创建带登录态的 jmcomic 客户端。"""
    return build_option(conf).new_jm_client()


def fetch_page(client, page=1, folder_id=FOLDER_ALL):
    """读取一页收藏（按收藏时间倒序），返回 JmFavoritePage。

    返回值里的 ``folder_list`` 就是账号的全部收藏夹，界面据此构建筛选菜单。
    """
    return client.favorite_folder(page=page, folder_id=folder_id)


def folders_of(page):
    """从收藏页里取出收藏夹列表 ``[(fid, fname), ...]``（不含「全部」）。"""
    return [(str(fid), fname) for fid, fname in page.iter_folder_id_name()]


def fetch_folders(conf):
    """单独读取账号的全部收藏夹 ``[(fid, fname), ...]``（本子详情页收藏时用）。"""
    return folders_of(fetch_page(new_client(conf), 1))


def preview_items(conf, limit=PREVIEW_COUNT):
    """读取「全部」收藏夹最前面的若干条（账号页预览用，不含封面）。"""
    return explore.to_items(fetch_page(new_client(conf), 1, FOLDER_ALL))[:limit]


def add_to_folder(conf, album_id, folder_id=FOLDER_ALL):
    """把本子加入指定收藏夹。

    ``folder_id`` 传 :data:`FOLDER_ALL` 表示加入默认收藏夹（不进任何单独收藏夹）。

    移动端收藏接口是 Toggle 语义且不接受收藏夹参数，因此要做一层保护：
    若服务端返回的却是「取消」（说明它认为本子已收藏），立刻再调用一次加回来。
    """
    client = new_client(conf)
    resp = _toggle(client, album_id, folder_id)
    if resp.res_data.get("type") != "add":
        _toggle(client, album_id, folder_id)
    return resp


def remove_from_favorites(conf, album_id):
    """取消收藏本子。

    与收藏方向相反的保护：若服务端返回的却是「加入」（说明它认为本子未收藏），
    立刻再调用一次取消掉，保证调用后一定是未收藏状态。
    """
    client = new_client(conf)
    resp = _toggle(client, album_id)
    if resp.res_data.get("type") != "remove":
        _toggle(client, album_id)
    return resp


def _toggle(client, album_id, folder_id=FOLDER_ALL):
    """调用收藏接口（Toggle 语义）：已收藏会取消、未收藏会加入。"""
    resp = client.req_api(
        client.API_FAVORITE,
        get=False,
        data={"aid": str(album_id), "folder_id": str(folder_id)},
    )
    client.require_resp_status_ok(resp)
    return resp
