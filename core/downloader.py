# -*- coding: utf-8 -*-
"""下载层：把界面配置翻译成 jmcomic 选项，并处理下载产物与邮件推送。"""

import copy
import os
import re
import smtplib

import jmcomic
import yaml

from core import pdf_metadata
from core.config import resolve_path
from utils.helpers import clamp

# 本子网页链接固定使用 18comic.vip：其余镜像域名只支持下载，浏览器直接访问会被拦截
SITE_DOMAIN = "18comic.vip"

# dir_rule 未配置时的兜底规则（与 jmcomic 默认一致：图片存放在 base_dir/<章节名>）
DEFAULT_FILENAME_RULE = "Pname"

# PDF 插件 key：本工具插件会把元数据写进 PDF；img2pdf 为旧配置里的 key，一并识别并替换
PDF_PLUGIN_KEYS = (pdf_metadata.PLUGIN_KEY, "img2pdf")


def album_url(album_id, domain=SITE_DOMAIN):
    """拼接本子在网站上的链接，便于在界面里跳转查看。"""
    return jmcomic.JmcomicText.format_album_url(str(album_id), domain)


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


def build_option(conf):
    """根据界面配置构建 jmcomic Option。

    app 段的下载目录、并发数、登录信息、是否生成 PDF 会覆盖 option 段中的同名项。
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
    username = (app_conf.get("username") or "").strip()
    password = (app_conf.get("password") or "").strip()
    if username and password:
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
