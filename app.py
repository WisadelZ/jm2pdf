# -*- coding: utf-8 -*-
"""
Jm2PDF v1.2.0 - 禁漫本子下载工具

Copyright (c) 2026 WisadelZ

This program is free software: you can redistribute it and/or modify
it under the terms of the CC BY-NC-ND 4.0 License.
You should have received a copy of the CC BY-NC-ND 4.0 License along
with this program. If not, see <https://creativecommons.org/licenses/by-nc-nd/4.0/>

Unauthorized modification, distribution, or commercial use is strictly prohibited.
"""

import copy
import logging
import os
import queue
import re
import smtplib
import sys
import threading
import traceback

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, scrolledtext, ttk

import yaml
import jmcomic

# 应用标识
_APP_NAME = "Jm2PDF"
_APP_VER = "1.2.0"
_CONF_FILE = "conf.yml"

APP_NAME = _APP_NAME.lower()
APP_VERSION = _APP_VER
APP_TITLE = "%s v%s - 本子下载转 PDF" % (APP_NAME, APP_VERSION)
CONF_FILENAME = _CONF_FILE
BTN_WIDTH = 8

CONF_HEADER = """# Jm2PDF 配置文件
# 界面中的任何修改都会自动同步保存到本文件；也可手动编辑后重启程序生效。
# 相对路径基于程序（exe）所在目录解析。

"""

DEFAULT_CONF_TEXT = """
version: 1.2.0
app:
  download_dir: ./download
  to_pdf: true
  thread_image: 30
  thread_photo: 16
  username: ''
  password: ''
mail:
  enable: false
  server: smtp.qq.com
  port: 465
  sender: ''
  password: ''
  receiver: ''
  subject: downloaded comic
  body: jmcomic download successfully.
option:
  log: true
  download:
    image:
      suffix: .jpg
  dir_rule:
    base_dir: ./download
  plugins:
    after_photo:
      - plugin: img2pdf
        kwargs:
          pdf_dir: ./download
          filename_rule: Pid
"""


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def bundle_dir():
    return getattr(sys, "_MEIPASS", app_dir())


def conf_path():
    return os.path.join(app_dir(), CONF_FILENAME)


def resolve_path(path):
    path = (path or "").strip()
    if not path:
        path = "download"
    if not os.path.isabs(path):
        path = os.path.join(app_dir(), path)
    return os.path.normpath(path)


def clamp(value, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def parse_ids(text):
    tokens = [t for t in re.split(r"[\s,;，；、]+", text or "") if t]
    seen, result = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _deep_merge(base, override):
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def ensure_conf_file():
    path = conf_path()
    if os.path.isfile(path):
        return path
    text = None
    bundled = os.path.join(bundle_dir(), CONF_FILENAME)
    if os.path.isfile(bundled):
        try:
            with open(bundled, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            text = None
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text if text else CONF_HEADER + yaml.safe_dump(
                yaml.safe_load(DEFAULT_CONF_TEXT), allow_unicode=True, sort_keys=False))
    except OSError:
        pass
    return path


def load_conf():
    defaults = yaml.safe_load(DEFAULT_CONF_TEXT)
    path = ensure_conf_file()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return _deep_merge(defaults, data)


def save_conf(conf):
    conf = copy.deepcopy(conf)
    conf["version"] = APP_VERSION
    text = CONF_HEADER + yaml.safe_dump(
        conf, allow_unicode=True, sort_keys=False, default_flow_style=False)
    with open(conf_path(), "w", encoding="utf-8") as f:
        f.write(text)


def build_option(conf):
    app_conf = conf.get("app") or {}
    download_dir = resolve_path(app_conf.get("download_dir"))
    data = copy.deepcopy(conf.get("option") or {})
    threading_conf = data.setdefault("download", {}).setdefault("threading", {})
    threading_conf["image"] = clamp(app_conf.get("thread_image", 30), 1, 50)
    threading_conf["photo"] = clamp(app_conf.get("thread_photo", 16), 1, 64)
    data.setdefault("dir_rule", {})["base_dir"] = download_dir
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
            if isinstance(item, dict) and item.get("plugin") == "img2pdf":
                item.setdefault("kwargs", {})["pdf_dir"] = download_dir
                break
        else:
            after_photo.append({
                "plugin": "img2pdf",
                "kwargs": {"pdf_dir": download_dir, "filename_rule": "Pid"},
            })
    else:
        plugins["after_photo"] = [
            item for item in after_photo
            if not (isinstance(item, dict) and item.get("plugin") == "img2pdf")
        ]
    return jmcomic.create_option_by_str(yaml.safe_dump(data, allow_unicode=True))


def collect_pdfs(result):
    items = list(result) if hasattr(result, "__iter__") and not isinstance(result, tuple) else [result]
    pdfs = []
    for item in items:
        try:
            pdfs.extend(item.manifest.export_filepath_dict.get("pdf", []))
        except Exception:
            continue
    return [p for p in dict.fromkeys(pdfs) if os.path.isfile(p)]


def send_mail(cfg, files, log):
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
            log("警告：附件 %s 读取失败，已跳过（%s）" % (path, e))
            continue
        part.add_header("Content-Disposition", "attachment",
                        filename=Header(os.path.basename(path), "utf-8").encode())
        encoders.encode_base64(part)
        msg.attach(part)
        log("已添加附件：%s" % os.path.basename(path))
    port = clamp(cfg.get("port", 465), 1, 65535)
    if port == 465:
        server = smtplib.SMTP_SSL(cfg["server"], port, timeout=60)
    else:
        server = smtplib.SMTP(cfg["server"], port, timeout=60)
        server.starttls()
    with server:
        server.login(sender, cfg["password"])
        server.sendmail(sender, receiver, msg.as_string())


class QueueLogHandler(logging.Handler):
    def __init__(self, q):
        super().__init__()
        self.q = q

    def emit(self, record):
        try:
            self.q.put(("log", self.format(record)))
        except Exception:
            pass


# --------------------------------------------------------------------------
# 折叠面板控件
# --------------------------------------------------------------------------
class CollapsibleFrame(ttk.Frame):
    """可折叠面板：勾选复选框展开，取消勾选折叠并禁用内部控件。"""

    def __init__(self, parent, text, variable, **kw):
        super().__init__(parent, **kw)
        self._variable = variable
        self._expanded = tk.BooleanVar(value=variable.get())
        self._expanded.trace_add("write", lambda *_: self._on_toggle())

        # 标题行
        header = ttk.Frame(self)
        header.pack(fill="x")
        self._check = ttk.Checkbutton(header, text=text, variable=self._expanded)
        self._check.pack(side="left", padx=8, pady=6)

        # 内容容器
        self._body = ttk.Frame(self)
        self._body.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self._on_toggle()

    def body(self):
        return self._body

    def _on_toggle(self):
        expanded = self._expanded.get()
        # 同步到外部 variable（供 conf 读取）
        self._variable.set(expanded)
        # 折叠时禁用内部所有控件
        for child in self._body.winfo_children():
            child.configure(state=("normal" if expanded else "disabled"))
        if expanded:
            self._body.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        else:
            self._body.pack_forget()


# --------------------------------------------------------------------------
# 主界面
# --------------------------------------------------------------------------
class App:
    SAVE_DELAY_MS = 500

    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.running = False
        self.searching = False
        self.searched_id = ""
        self._save_job = None
        self._loading = True

        self.conf = load_conf()

        root.title(APP_TITLE)
        root.geometry("640x720")
        root.minsize(480, 500)

        app_conf = self.conf["app"]
        mail_conf = self.conf["mail"]

        self.ids_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.result_var = tk.StringVar()

        self.download_dir = tk.StringVar(value=str(app_conf.get("download_dir") or "./download"))
        self.to_pdf = tk.BooleanVar(value=bool(app_conf.get("to_pdf", True)))
        self.thread_image = tk.IntVar(value=clamp(app_conf.get("thread_image", 30), 1, 50))
        self.thread_photo = tk.IntVar(value=clamp(app_conf.get("thread_photo", 16), 1, 64))
        self.username = tk.StringVar(value=app_conf.get("username") or "")
        self.password = tk.StringVar(value=app_conf.get("password") or "")

        self.mail_enable = tk.BooleanVar(value=bool(mail_conf.get("enable", False)))
        self.mail_server = tk.StringVar(value=mail_conf.get("server") or "smtp.qq.com")
        self.mail_port = tk.StringVar(value=str(mail_conf.get("port", 465)))
        self.mail_sender = tk.StringVar(value=mail_conf.get("sender") or "")
        self.mail_password = tk.StringVar(value=mail_conf.get("password") or "")
        self.mail_receiver = tk.StringVar(value=mail_conf.get("receiver") or "")
        self.mail_subject = tk.StringVar(value=mail_conf.get("subject") or "")
        self.mail_body = tk.StringVar(value=mail_conf.get("body") or "")

        self._conf_vars = [
            self.download_dir, self.to_pdf, self.thread_image, self.thread_photo,
            self.username, self.password,
            self.mail_enable, self.mail_server, self.mail_port, self.mail_sender,
            self.mail_password, self.mail_receiver, self.mail_subject, self.mail_body,
        ]

        self._build_ui()
        self._attach_jm_logger()

        for var in self._conf_vars:
            var.trace_add("write", self._on_conf_var_change)
        self._loading = False

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_queue)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True, padx=8, pady=6)

        # ===== 下载任务 =====
        box_task = ttk.LabelFrame(outer, text="下载任务")
        box_task.pack(fill="x", **pad)
        box_task.columnconfigure(1, weight=1)

        ttk.Label(box_task, text="本子 ID：").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(box_task, textvariable=self.ids_var).grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(box_task, text="清空", width=BTN_WIDTH,
                   command=lambda: self.ids_var.set("")).grid(row=0, column=2, sticky="ew", padx=(4, 6), pady=4)

        ttk.Label(box_task, text="下载目录：").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(box_task, textvariable=self.download_dir).grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(box_task, text="浏览...", width=BTN_WIDTH,
                   command=self._choose_dir).grid(row=1, column=2, sticky="ew", padx=(4, 6), pady=4)

        ttk.Label(box_task, text="多个 ID 用逗号或空格分隔；下载目录支持相对路径（基于程序目录）",
                  foreground="#777").grid(row=2, column=1, sticky="w", padx=4, pady=(0, 4))

        # ===== 本子搜索 =====
        box_search = ttk.LabelFrame(outer, text="本子搜索")
        box_search.pack(fill="x", **pad)
        box_search.columnconfigure(1, weight=1)

        ttk.Label(box_search, text="搜索 ID：").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        search_entry = ttk.Entry(box_search, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        search_entry.bind("<Return>", lambda e: self.do_search())
        self.btn_search = ttk.Button(box_search, text="搜索", width=BTN_WIDTH, command=self.do_search)
        self.btn_search.grid(row=0, column=2, sticky="ew", padx=(4, 6), pady=4)

        ttk.Label(box_search, text="搜索结果：").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        # 用 Text 替代 Entry 以支持自动换行
        self.result_text = scrolledtext.ScrolledText(
            box_search, height=3, wrap="word", state="disabled",
            font=("Consolas", 9), background="#f5f5f5", foreground="#222",
        )
        self.result_text.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        self.btn_add = ttk.Button(box_search, text="添加", width=BTN_WIDTH, command=self.add_searched)
        self.btn_add.grid(row=1, column=2, sticky="ew", padx=(4, 6), pady=4)

        # ===== 下载选项（折叠式）=====
        self.collapsible_opt = CollapsibleFrame(outer, "下载选项（展开更多设置）", self.to_pdf)
        self.collapsible_opt.pack(fill="x", **pad)

        opt_body = self.collapsible_opt.body()
        opt_body.columnconfigure(1, weight=1)

        ttk.Label(opt_body, text="图片并发：").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        ttk.Spinbox(opt_body, from_=1, to=50, width=5,
                    textvariable=self.thread_image).grid(row=0, column=1, sticky="w", padx=4, pady=4)
        ttk.Label(opt_body, text="章节并发：").grid(row=0, column=2, sticky="e", padx=(12, 4), pady=4)
        ttk.Spinbox(opt_body, from_=1, to=64, width=5,
                    textvariable=self.thread_photo).grid(row=0, column=3, sticky="w", padx=4, pady=4)

        ttk.Label(opt_body, text="账号（可选）：").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(opt_body, textvariable=self.username).grid(row=1, column=1, columnspan=3, sticky="ew", padx=4, pady=4)

        ttk.Label(opt_body, text="密码：").grid(row=2, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(opt_body, textvariable=self.password, show="*").grid(row=2, column=1, columnspan=3, sticky="ew", padx=4, pady=4)

        # ===== 邮件推送（折叠式）=====
        self.collapsible_mail = CollapsibleFrame(outer, "邮件推送（展开更多设置）", self.mail_enable)
        self.collapsible_mail.pack(fill="x", **pad)

        mail_body = self.collapsible_mail.body()
        mail_body.columnconfigure(1, weight=1)

        ttk.Label(mail_body, text="服务器：").grid(row=0, column=0, sticky="e", padx=6, pady=3)
        ttk.Entry(mail_body, textvariable=self.mail_server).grid(row=0, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(mail_body, text="端口：").grid(row=0, column=2, sticky="e", padx=(12, 4), pady=3)
        ttk.Entry(mail_body, textvariable=self.mail_port, width=8).grid(row=0, column=3, sticky="w", padx=4, pady=3)

        ttk.Label(mail_body, text="发件邮箱：").grid(row=1, column=0, sticky="e", padx=6, pady=3)
        ttk.Entry(mail_body, textvariable=self.mail_sender).grid(row=1, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(mail_body, text="授权码：").grid(row=1, column=2, sticky="e", padx=(12, 4), pady=3)
        ttk.Entry(mail_body, textvariable=self.mail_password, show="*").grid(row=1, column=3, sticky="w", padx=4, pady=3)

        ttk.Label(mail_body, text="收件邮箱：").grid(row=2, column=0, sticky="e", padx=6, pady=3)
        ttk.Entry(mail_body, textvariable=self.mail_receiver).grid(row=2, column=1, columnspan=3, sticky="ew", padx=4, pady=3)
        ttk.Label(mail_body, text="留空则发给自己", foreground="#777").grid(row=3, column=1, sticky="w", padx=4, pady=(0, 3))

        ttk.Label(mail_body, text="邮件标题：").grid(row=4, column=0, sticky="e", padx=6, pady=3)
        ttk.Entry(mail_body, textvariable=self.mail_subject).grid(row=4, column=1, columnspan=3, sticky="ew", padx=4, pady=3)

        ttk.Label(mail_body, text="邮件正文：").grid(row=5, column=0, sticky="e", padx=6, pady=3)
        ttk.Entry(mail_body, textvariable=self.mail_body).grid(row=5, column=1, columnspan=3, sticky="ew", padx=4, pady=3)

        # ===== 操作按钮 =====
        box_btn = ttk.Frame(outer)
        box_btn.pack(fill="x", **pad)

        self.btn_start = ttk.Button(box_btn, text="开始下载", command=self.start)
        self.btn_start.pack(side="left", padx=(6, 4))
        ttk.Button(box_btn, text="打开下载目录", command=self._open_dir).pack(side="left", padx=4)
        ttk.Button(box_btn, text="清空日志", command=self._clear_log).pack(side="left", padx=4)

        self.progress = ttk.Progressbar(box_btn, mode="indeterminate", length=120)
        self.progress.pack(side="right", padx=6)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(box_btn, textvariable=self.status_var, foreground="#444").pack(side="right", padx=6)

        # ===== 日志 =====
        box_log = ttk.LabelFrame(outer, text="运行日志")
        box_log.pack(fill="both", expand=True, **pad)

        self.log_widget = scrolledtext.ScrolledText(
            box_log, height=8, state="disabled", wrap="word",
            font=("Consolas", 9), background="#1e1e1e", foreground="#dcdcdc",
        )
        self.log_widget.pack(fill="both", expand=True, padx=4, pady=4)

    # ------------------------------ 配置同步 ------------------------------
    def _on_conf_var_change(self, *_):
        if self._loading:
            return
        self._sync_conf_from_ui()
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(self.SAVE_DELAY_MS, self._flush_conf)

    def _sync_conf_from_ui(self):
        self.conf["app"] = {
            "download_dir": self.download_dir.get().strip() or "./download",
            "to_pdf": bool(self.to_pdf.get()),
            "thread_image": self._safe_int(self.thread_image, 30),
            "thread_photo": self._safe_int(self.thread_photo, 16),
            "username": self.username.get(),
            "password": self.password.get(),
        }
        self.conf["mail"] = {
            "enable": bool(self.mail_enable.get()),
            "server": self.mail_server.get().strip() or "smtp.qq.com",
            "port": self._safe_int(self.mail_port, 465),
            "sender": self.mail_sender.get().strip(),
            "password": self.mail_password.get(),
            "receiver": self.mail_receiver.get().strip(),
            "subject": self.mail_subject.get(),
            "body": self.mail_body.get(),
        }

    @staticmethod
    def _safe_int(var, default):
        try:
            return int(var.get())
        except (tk.TclError, ValueError):
            return default

    def _flush_conf(self):
        self._save_job = None
        try:
            save_conf(self.conf)
        except OSError as e:
            self._set_status("配置保存失败：%s" % e)
            return
        if not self.running and not self.searching:
            self._set_status("配置已同步 → %s" % CONF_FILENAME)

    def _on_close(self):
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
            self._save_job = None
        self._sync_conf_from_ui()
        try:
            save_conf(self.conf)
        except OSError:
            pass
        self.root.destroy()

    def _set_status(self, text):
        self.status_var.set(text)

    # ------------------------------ 日志 ------------------------------
    def _attach_jm_logger(self):
        handler = QueueLogHandler(self.q)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logger = logging.getLogger("jmcomic")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

    def log(self, message):
        self.q.put(("log", message))

    def _poll_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._append_log(item[1])
                elif kind == "search_done":
                    self._on_search_done(item[1], item[2], item[3])
                elif kind == "task_done":
                    self._finish(item[1], item[2])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _append_log(self, text):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text.rstrip("\n") + "\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _clear_log(self):
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.configure(state="disabled")

    def _set_result_text(self, text):
        """设置搜索结果文本（自动换行）。"""
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.configure(state="disabled")

    # ------------------------------ 搜索 ------------------------------
    def do_search(self):
        if self.searching:
            return
        aid = self.search_var.get().strip()
        if not aid:
            messagebox.showwarning(APP_NAME, "请先在搜索框中输入本子 ID")
            return
        self.searching = True
        self.btn_search.configure(state="disabled")
        self.btn_add.configure(state="disabled")
        self._set_result_text("")
        self.searched_id = ""
        self._set_status("搜索中...")
        threading.Thread(target=self._search_worker, args=(aid,), daemon=True).start()

    def _search_worker(self, aid):
        try:
            option = build_option(self.conf)
            client = option.new_jm_client()
            detail = client.get_album_detail(aid)
            # 提取标签
            tags = ""
            try:
                tag_list = getattr(detail, "tags", None) or []
                if isinstance(tag_list, list):
                    tags = ", ".join(str(t) for t in tag_list[:10])
                    if len(tag_list) > 10:
                        tags += " ..."
                elif isinstance(tag_list, dict):
                    all_tags = []
                    for v in tag_list.values():
                        if isinstance(v, list):
                            all_tags.extend(v)
                        else:
                            all_tags.append(str(v))
                    tags = ", ".join(all_tags[:10])
                    if len(all_tags) > 10:
                        tags += " ..."
            except Exception:
                tags = ""
            # 顺序：id / 页数·章节 / 名称 / 标签
            text = "ID: %s\n页数: %s / 章节: %d\n名称: %s" % (
                detail.id, detail.page_count, len(detail), detail.title,
            )
            if tags:
                text += "\n标签: %s" % tags
            self.q.put(("search_done", True, text, str(detail.id)))
        except Exception as e:
            self.q.put(("search_done", False, "搜索失败：%s" % e, ""))

    def _on_search_done(self, ok, text, aid):
        self.searching = False
        self.btn_search.configure(state="normal")
        self.btn_add.configure(state="normal" if ok else "disabled")
        self._set_result_text(text)
        self.searched_id = aid if ok else ""
        self._set_status("搜索完成" if ok else "搜索失败")
        if ok:
            self.log("搜索结果：%s" % text.replace("\n", " | "))
        else:
            self.log(text)

    def add_searched(self):
        aid = self.searched_id
        if not aid:
            messagebox.showinfo(APP_NAME, "没有可添加的搜索结果，请先搜索")
            return
        ids = parse_ids(self.ids_var.get())
        if aid in ids:
            self._set_status("ID %s 已在列表中" % aid)
            return
        ids.append(aid)
        self.ids_var.set(", ".join(ids))
        self._set_status("已添加 %s 到下载列表" % aid)

    # ------------------------------ 交互 ------------------------------
    def _choose_dir(self):
        current = resolve_path(self.download_dir.get())
        path = filedialog.askdirectory(initialdir=current if os.path.isdir(current) else app_dir())
        if path:
            self.download_dir.set(os.path.normpath(path))

    def _open_dir(self):
        path = resolve_path(self.download_dir.get())
        os.makedirs(path, exist_ok=True)
        os.startfile(path)

    def _set_running(self, running):
        self.running = running
        if running:
            self.btn_start.configure(state="disabled")
            self.progress.start(12)
        else:
            self.btn_start.configure(state="normal")
            self.progress.stop()

    def start(self):
        if self.running:
            return
        ids = parse_ids(self.ids_var.get())
        if not ids:
            messagebox.showwarning(APP_NAME, "请先输入至少一个本子 ID")
            return
        self._sync_conf_from_ui()
        conf = copy.deepcopy(self.conf)
        download_dir = resolve_path(conf["app"].get("download_dir"))
        mail_conf = conf["mail"]
        if mail_conf.get("enable") and not (mail_conf.get("sender") and mail_conf.get("password")):
            messagebox.showwarning(APP_NAME, "已勾选邮件推送，请填写发件邮箱与授权码")
            return
        self._set_running(True)
        self._set_status("下载中...")
        threading.Thread(target=self._run_task, args=(ids, download_dir, conf), daemon=True).start()

    def _run_task(self, ids, download_dir, conf):
        try:
            os.makedirs(download_dir, exist_ok=True)
            option = build_option(conf)
            self.log("开始下载 %d 个本子：%s" % (len(ids), ", ".join(ids)))
            self.log("下载目录：%s" % download_dir)
            result = jmcomic.download_album(ids, option)
            failed = getattr(result, "failed", {}) or {}
            pdfs = collect_pdfs(result)
            for jmid, err in failed.items():
                self.log("下载失败 [%s]：%s" % (jmid, err))
            if conf["app"].get("to_pdf", True):
                if pdfs:
                    self.log("共生成 %d 个 PDF：" % len(pdfs))
                    for p in pdfs:
                        self.log("  %s" % p)
                else:
                    self.log("未生成任何 PDF 文件")
            mail_conf = conf["mail"]
            if mail_conf.get("enable"):
                if pdfs:
                    self.log("正在发送邮件...")
                    try:
                        send_mail(mail_conf, pdfs, self.log)
                        self.log("邮件发送成功！")
                    except Exception as e:
                        self.log("邮件发送失败：%s" % e)
                else:
                    self.log("没有可发送的 PDF，跳过邮件推送")
            ok = not failed
            summary = "完成：%d 个本子，%d 个 PDF" % (len(ids) - len(failed), len(pdfs))
            self.q.put(("task_done", ok, summary if ok else "完成（含失败项），详见日志"))
        except Exception:
            self.log("发生错误：\n%s" % traceback.format_exc())
            self.q.put(("task_done", False, "出错，详见日志"))

    def _finish(self, ok, status):
        self._set_running(False)
        self._set_status(status)
        if ok:
            messagebox.showinfo(APP_NAME, status)
        else:
            messagebox.showwarning(APP_NAME, status)


def main():
    # 高 DPI 下让界面更清晰
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    print("\n" + "=" * 50)
    print("Jm2PDF v1.2.0 - 禁漫本子下载工具")
    print("Copyright (c) 2026 WisadelZ")
    print("Licensed under CC BY-NC-ND 4.0")
    print("Source: https://github.com/WisadelZ/jm2pdf")
    print("=" * 50 + "\n")

    root = tk.Tk()
    
    # 设置窗口标题栏左侧的小图标（优先使用打包后的临时目录，失败则从程序目录找）
    for icon_name in ("icon.ico", "icon.png"):
        icon_path = os.path.join(bundle_dir(), icon_name)
        if os.path.isfile(icon_path):
            try:
                root.iconbitmap(icon_path)
                break
            except Exception:
                pass
        icon_path = os.path.join(app_dir(), icon_name)
        if os.path.isfile(icon_path):
            try:
                root.iconbitmap(icon_path)
                break
            except Exception:
                pass

    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass

    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
