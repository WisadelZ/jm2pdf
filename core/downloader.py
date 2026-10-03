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
"""下载层：把界面配置翻译成 jmcomic 选项，处理下载产物与邮件推送，
并提供「需要登录态」的接口（收藏 / 签到）所用的会话级登录客户端。"""

import copy
import io
import os
import re
import smtplib
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import jmcomic
import yaml
from PIL import Image

from core import account, pdf_metadata, progress_plugin  # noqa: F401  (导入即注册插件)
from core.config import resolve_path
from utils.helpers import clamp

# 本子网页链接固定使用 18comic.vip：其余镜像域名只支持下载，浏览器直接访问会被拦截
SITE_DOMAIN = "18comic.vip"

# dir_rule 未配置时的兜底规则（与 jmcomic 默认一致：图片存放在 base_dir/<章节名>）
DEFAULT_FILENAME_RULE = "Pname"

# PDF 插件 key：本工具插件会把元数据写进 PDF；img2pdf 为旧配置里的 key，一并识别并替换
PDF_PLUGIN_KEYS = (pdf_metadata.PLUGIN_KEY, "img2pdf")

# 封面缩略图尺寸后缀：与网站搜索列表一致，3:4 竖版
COVER_SIZE = "_3x4"

# 图片 CDN 会拒绝空 User-Agent（返回 403），取图时显式带一个
COVER_HEADERS = {"User-Agent": "Mozilla/5.0"}

# 批量取封面图时的并发线程数
COVER_WORKERS = 8

# 详情页「预览前 5 页」最多取几张
PREVIEW_LIMIT = 5

# 预览图重新编码时的 JPEG 质量（站点图片本身是打乱的，必须重排后重编码）
PREVIEW_QUALITY = 92


def album_url(album_id, domain=SITE_DOMAIN):
    """拼接本子在网站上的链接，便于在界面里跳转查看。"""
    return jmcomic.JmcomicText.format_album_url(str(album_id), domain)


def cover_url(album_id, size=COVER_SIZE):
    """拼接封面图 URL（只拼地址，不下载）。"""
    return jmcomic.JmcomicText.get_album_cover_url(str(album_id), size=size)


def fetch_image_bytes(url):
    """按 URL 取图片字节，供界面控件直接显示（只在内存中，不落盘）；失败返回 None。"""
    if not url:
        return None
    try:
        request = urllib.request.Request(url, headers=COVER_HEADERS)
        with urllib.request.urlopen(request, timeout=15) as resp:
            # 不存在的资源会返回 200 + 空响应，这里按失败处理
            return resp.read() or None
    except Exception:      # 图片只是界面的点缀，任何异常都不应影响主流程
        return None


def fetch_cover(album_id, size=COVER_SIZE):
    """取封面图字节，供界面控件直接显示（只在内存中，不落盘）；失败返回 None。"""
    return fetch_image_bytes(cover_url(album_id, size))


def fetch_covers(items, workers=COVER_WORKERS):
    """并发给条目列表补上封面字节（只在内存中，不落盘）；取不到的项保持 None。"""
    pending = [item for item in items if not item.get("cover")]
    if not pending:
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        covers = list(pool.map(lambda item: fetch_cover(item["id"]), pending))
    for item, cover in zip(pending, covers):
        item["cover"] = cover


def needs_login_to_view(error):
    """服务端是否明确表示「本子取不到」——这种本子可能只对登录用户可见。

    这是唯一值得用登录态重试的情况；网络抖动等其它错误一律交给用户重试，
    避免无谓地消耗下载额度。
    """
    return isinstance(error, jmcomic.MissingAlbumPhotoException)


def fetch_preview_images(conf, album_id, limit=PREVIEW_LIMIT):
    """取本子第一话的前几页图片，供详情页预览。

    返回 ``[{"data": 图片字节, "size": (宽, 高)}, ...]``；站点上的图片是打乱存放的，
    这里按 jmcomic 的分条规则还原（未打乱的直接用原始字节），全程只在内存中处理。
    单页取不到就跳过，一页都没取到时抛出异常，由调用方提示。

    预览属于取图流程，默认不带登录态，避免白白消耗下载额度；只有服务端明确
    表示本子取不到时，才用登录态再试一次。
    """
    try:
        return _fetch_preview_images(conf, album_id, limit, with_login=False)
    except Exception as exc:
        if not (needs_login_to_view(exc) and account.is_logged_in()):
            raise
    return _fetch_preview_images(conf, album_id, limit, with_login=True)


def _fetch_preview_images(conf, album_id, limit, with_login):
    client = build_option(conf, with_login=with_login).new_jm_client()
    photo = client.get_album_detail(album_id)[0]
    client.check_photo(photo)              # 补全图片 URL 等信息
    pages = []
    error = None
    for index in range(min(limit, len(photo))):
        try:
            pages.append(fetch_page_image(client, photo.getindex(index)))
        except Exception as exc:           # 个别页失败不影响其余几页
            error = exc
    if not pages:
        raise error if error is not None else ValueError("没有取到预览图片")
    return pages


def fetch_page_image(client, detail):
    """取一页图片并解密，返回 ``{"data": 字节, "size": (宽, 高)}``。

    供详情页预览与在线浏览共用；只在内存中处理，不落盘。
    """
    content = client.get_jm_image(detail.download_url).content
    if not content:
        raise ValueError("图片响应为空")
    num = jmcomic.JmImageTool.get_num_by_url(detail.scramble_id, detail.img_url)
    if num == 0:
        # 未打乱的图：原始字节就能直接显示，不必重新编码
        return {"data": content, "size": _image_size(content)}
    image = _decode_image(content, num)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=PREVIEW_QUALITY)
    return {"data": buffer.getvalue(), "size": image.size}


def _decode_image(content, num):
    """按 jmcomic 的分条规则把打乱的图片还原（与 JmImageTool.decode_and_save 一致）。"""
    source = jmcomic.JmImageTool.open_image(content)
    width, height = source.size
    target = Image.new("RGB", (width, height))
    over = height % num
    for i in range(num):
        move = height // num
        y_src = height - (move * (i + 1)) - over
        y_dst = move * i
        if i == 0:
            move += over
        else:
            y_dst += over
        target.paste(source.crop((0, y_src, width, y_src + move)),
                     (0, y_dst, width, y_dst + move))
    return target


def _image_size(content):
    """读出图片像素尺寸；读不出来时给一个竖版的兜底尺寸。"""
    try:
        return jmcomic.JmImageTool.open_image(content).size
    except Exception:
        return (1000, 1400)


def pdf_filename_rule(dir_rule_dsl):
    """由下载目录规则推导 PDF 文件名规则，取目录规则的最后一段。

    dir_rule 的最后一段就是图片文件夹的名字，PDF 用同一规则命名后，
    按名称排序时 PDF 与其图片文件夹会紧挨在一起。
    """
    segments = [seg.strip() for seg in re.split(r"[/_]", (dir_rule_dsl or "").strip())]
    segments = [seg for seg in segments if seg]
    if not segments or segments[-1] == "Bd":
        return DEFAULT_FILENAME_RULE
    return segments[-1]


def build_option(conf, with_login=True, progress=False):
    """根据界面配置构建 jmcomic Option。

    app 段的下载目录、并发数、是否生成 PDF 会覆盖 option 段中的同名项；
    登录信息由 :mod:`core.account` 加密保存，``with_login=True`` 时取运行时凭据
    注入登录插件（读元数据、收藏等需要身份的场景）。

    ``with_login=False`` 用于取图流程（下载 / 预览 / 在线浏览）：站点会按登录
    身份统计下载额度，因此这些流程默认不带登录态，只有本子确实需要登录时才改用它。

    ``progress=True`` 时额外注入 :mod:`core.progress_plugin` 的进度插件
    （任务队列用它统计每个任务的页数进度）。
    """
    app_conf = conf.get("app") or {}
    download_dir = resolve_path(app_conf.get("download_dir"))
    data = copy.deepcopy(conf.get("option") or {})

    threading_conf = data.setdefault("download", {}).setdefault("threading", {})
    threading_conf["image"] = clamp(app_conf.get("thread_image", 30), 1, 50)
    threading_conf["photo"] = clamp(app_conf.get("thread_photo", 16), 1, 64)

    dir_rule = data.setdefault("dir_rule", {})
    dir_rule["base_dir"] = download_dir
    # PDF 文件名跟随图片文件夹名（取 dir_rule 最后一段），便于按名称归在一起
    filename_rule = pdf_filename_rule(dir_rule.get("rule"))

    plugins = data.setdefault("plugins", {})
    if progress:
        for group, key in progress_plugin.PLUGIN_KEYS.items():
            plugins.setdefault(group, []).append({"plugin": key, "kwargs": {}})
    username, password = account.get_credentials()
    if with_login and username and password:
        plugins.setdefault("after_init", []).insert(0, {
            "plugin": "login",
            "kwargs": {"username": username, "password": password},
        })

    after_photo = plugins.setdefault("after_photo", [])
    if app_conf.get("to_pdf", True):
        for item in after_photo:
            if isinstance(item, dict) and item.get("plugin") in PDF_PLUGIN_KEYS:
                # 旧配置里的 img2pdf 一并改写成带元数据的插件
                item["plugin"] = pdf_metadata.PLUGIN_KEY
                kwargs = item.setdefault("kwargs", {})
                kwargs["pdf_dir"] = download_dir
                kwargs["filename_rule"] = filename_rule
                break
        else:
            after_photo.append({
                "plugin": pdf_metadata.PLUGIN_KEY,
                "kwargs": {"pdf_dir": download_dir, "filename_rule": filename_rule},
            })
    else:
        plugins["after_photo"] = [
            item for item in after_photo
            if not (isinstance(item, dict) and item.get("plugin") in PDF_PLUGIN_KEYS)
        ]
    return jmcomic.create_option_by_str(yaml.safe_dump(data, allow_unicode=True))


# ---------------------------------------------------------------------------
# 会话级登录客户端：收藏 / 签到这类「必须带登录态」的接口用它
# ---------------------------------------------------------------------------

# 未登录时服务端的表现：收藏接口返回 code 401 的 JSON 原文，签到接口返回 data 为列表
_NOT_LOGGED_IN_HINTS = ("請先登入會員", "请先登入会员", "請先登入", "请先登入")

# 本会话复用的登录客户端及其对应的凭据（换账号后自动重建）
_session_lock = threading.Lock()
_session_client = None
_session_credentials = None


def reset_jm_session():
    """丢弃 jmcomic 的全局登录会话。

    jmcomic 把首次请求 ``/setting`` 拿到的 cookies（含会话标识 ``AVS``）缓存到
    ``JmModuleConfig.APP_COOKIES``，并把它直接赋给之后创建的每一个客户端；登录成功后
    服务端会把该 ``AVS`` 绑定的会话升级为登录态。因此换账号时必须丢弃这份 cookies，
    否则新客户端仍带着上一个账号的会话——登录接口会直接返回旧账号的信息，界面也就
    一直显示旧账号的数据（手动刷新、清缓存都无效，因为它们只是拿旧会话重拉一遍）。
    """
    jmcomic.JmModuleConfig.APP_COOKIES = None


def fresh_login_client(conf):
    """建一个「不带任何历史会话」的客户端，供登录 / 校验身份使用。

    先清掉全局 cookies 缓存，再让客户端重建：``new_jm_client`` 的初始化会重新请求
    ``/setting``，拿到一个全新的 ``AVS``（未被绑定到任何账号），登录请求因此不会命中
    上一个账号的会话。
    """
    reset_jm_session()
    return build_option(conf, with_login=False).new_jm_client()


def logged_in_client(conf, relogin=False):
    """取本会话用于「需要登录态」请求的客户端，没有（或 ``relogin``）时重新登录。

    这里不走 jmcomic 的 login 插件：插件挂在 option 的 after_init 上，而 jmcomic
    调用该阶段时是 safe=True（异常只记日志、不往外抛）。登录一旦失败，调用方拿到的
    就是「看着正常、其实未登录」的客户端，请求会被服务端当游客处理——收藏报 401
    「請先登入會員」，签到则因为响应 data 是列表而在解 base64 时抛出 TypeError。

    另外禁漫的登录态是按域名隔离的：在 A 域名登录后，用同样的 cookies 请求 B 域名
    同样会被当成未登录；而 jmcomic 会在请求连续失败后自动切到下一个域名，所以
    「登录用的域名」和「请求用的域名」可能不是同一个（域名顺序还是进程启动时随机
    打乱的，重启后又变一个样）。这正是「刚登录首次加载偶发报错、重启就恢复」的原因。
    因此这里逐个域名试登录，把客户端锁定在登录成功的那个域名上，本会话所有请求
    都走它，从结构上避免域名漂移。
    """
    global _session_client, _session_credentials
    username, password = account.get_credentials()
    if not (username and password):
        raise jmcomic.JmcomicException("未登录：请先在「账号」页登录后再试")

    credentials = (username, password)
    with _session_lock:
        if (not relogin and _session_client is not None
                and _session_credentials == credentials):
            return _session_client
        client = _login_new_client(conf, username, password)
        _session_client, _session_credentials = client, credentials
        return client


def reset_session_client():
    """丢弃当前登录会话（退出登录、换账号时调用）。

    除了本模块缓存的登录客户端，还要清掉 jmcomic 的全局 cookies（见
    :func:`reset_jm_session`），否则下一个账号登录时仍会命中上一个账号的会话。
    """
    global _session_client, _session_credentials
    with _session_lock:
        _session_client, _session_credentials = None, None
    reset_jm_session()


def run_with_login(conf, action):
    """在登录态下执行 ``action(client)``；若仍被当成游客，重新登录一次再试。

    重试覆盖的是「登录态没能生效」这种偶发情况；重试后依旧失败，就把异常抛给调用方。
    """
    client = logged_in_client(conf)
    try:
        return action(client)
    except Exception as exc:
        if not needs_relogin(exc):
            raise
    client = logged_in_client(conf, relogin=True)
    return action(client)


def needs_relogin(error):
    """判断异常是否表示「服务端把这次请求当成游客处理了」。"""
    if isinstance(error, TypeError):
        # 未登录时签到接口的 data 是列表，jmcomic 拿它去 base64 解码会抛这个 TypeError
        return "bytes-like object" in str(error)
    text = str(error)
    return any(hint in text for hint in _NOT_LOGGED_IN_HINTS)


def _login_new_client(conf, username, password):
    """建客户端并登录，返回锁定在「登录成功域名」上的客户端。

    用 :func:`fresh_login_client` 建客户端：每次登录都从一个全新的会话开始，
    避免新客户端继承上一个账号已登录的 cookies。
    """
    client = fresh_login_client(conf)
    domains = list(client.domain_list)
    last_error = None
    for domain in domains:
        # 一次只留一个域名：登录和后续请求都只能走它，请求重试也不会漂到别的域名上
        client.domain_list = [domain]
        try:
            resp = client.login(username, password)
            data = getattr(resp, "res_data", None)
            if not isinstance(data, dict) or not data.get("uid"):
                raise jmcomic.JmcomicException("登录失败：服务端没有返回账号信息")
            return client
        except jmcomic.RequestRetryAllFailException as exc:
            last_error = exc            # 这个域名不通（或被挡），换下一个再试
    raise last_error or jmcomic.JmcomicException("登录失败：禁漫接口域名都不可用")


def collect_pdfs(result):
    """从下载结果中收集实际存在的 PDF 路径（去重）。"""
    items = list(result) if hasattr(result, "__iter__") and not isinstance(result, tuple) else [result]
    pdfs = []
    for item in items:
        try:
            pdfs.extend(item.manifest.export_filepath_dict.get("pdf", []))
        except Exception:
            continue
    return [p for p in dict.fromkeys(pdfs) if os.path.isfile(p)]


def send_mail(cfg, files, log, t):
    """把指定文件作为附件发送邮件；log 为日志回调，t 为多语言取值函数。"""
    from email import encoders
    from email.header import Header
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    sender = cfg["sender"]
    receiver = cfg.get("receiver") or sender
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = Header(cfg.get("subject") or "downloaded comic", "utf-8")
    msg.attach(MIMEText(cfg.get("body") or "jmcomic download successfully.", "plain", "utf-8"))

    for path in files:
        try:
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
        except OSError as e:
            log(t("log_attach_failed", path=path, error=e))
            continue
        part.add_header("Content-Disposition", "attachment",
                        filename=Header(os.path.basename(path), "utf-8").encode())
        encoders.encode_base64(part)
        msg.attach(part)
        log(t("log_attach_added", name=os.path.basename(path)))

    port = clamp(cfg.get("port", 465), 1, 65535)
    if port == 465:
        server = smtplib.SMTP_SSL(cfg["server"], port, timeout=60)
    else:
        server = smtplib.SMTP(cfg["server"], port, timeout=60)
        server.starttls()
    with server:
        server.login(sender, cfg["password"])
        server.sendmail(sender, receiver, msg.as_string())
