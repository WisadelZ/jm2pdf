# -*- coding: utf-8 -*-
"""下载任务队列：任务状态机、调度线程、进度聚合与持久化。

供 :class:`jm2pdf.ui.app_ui.AppUI` 使用；本模块不依赖 UI 框架，可单独测试。

设计要点：

- **一个任务 = 一个本子**：队列把 ``jmcomic.download_album(单个 ID)`` 交给调度线程
  逐个执行，每个任务因此都是可暂停 / 可取消 / 可重试的独立单元；本子内部的图片 /
  章节并发仍由 ``conf.yml`` 的 ``thread_image`` / ``thread_photo`` 控制。
- **进度来自插件钩子**：见 :mod:`core.progress_plugin`，本模块只做聚合、节流与落盘。
- **暂停 / 取消 = 给实体置 skip**：剩余章节 / 图片被优雅跳过，已下载的图片保留
  （jmcomic 命中 ``download.cache`` 时会跳过重复下载），继续时接着下即可。
- **关窗可恢复**：队列落盘到程序目录的 ``queue.json``，下次启动把未完成任务恢复为
  已暂停，由用户决定何时继续。
"""

import json
import logging
import os
import threading
import time
from collections import deque

import jmcomic

from core import account, progress_plugin
from core import config as conf_mod
from core import library
from core.config import app_dir
from core.downloader import build_option, collect_pdfs, needs_login_to_view, send_mail

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- 状态

STATUS_WAITING = "waiting"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"

# 界面筛选顺序
TASK_STATUSES = (STATUS_WAITING, STATUS_RUNNING, STATUS_PAUSED,
                 STATUS_DONE, STATUS_FAILED, STATUS_CANCELED)

# 需要调度线程操心的状态（未结束）
UNFINISHED_STATUSES = (STATUS_WAITING, STATUS_RUNNING, STATUS_PAUSED)
# 视为「队列有活动任务」（供界面置灰按钮）
ACTIVE_STATUSES = (STATUS_WAITING, STATUS_RUNNING)
# 已结束
FINISHED_STATUSES = (STATUS_DONE, STATUS_FAILED, STATUS_CANCELED)

# 筛选菜单里的「全部」
FILTER_ALL = "all"

# ---------------------------------------------------------------- 排序 / 持久化

TASK_SORT_KEYS = ("added", "id", "name", "progress")
DEFAULT_SORT_KEY = "added"
# 进度默认从高到低更有参考价值，其余按升序
SORT_DESC_DEFAULT = {"added": False, "id": False, "name": False, "progress": True}

QUEUE_FILENAME = "queue.json"
QUEUE_VERSION = 1
# 已结束的任务最多保留多少条，避免 queue.json 无限增长
QUEUE_HISTORY_LIMIT = 200

# ---------------------------------------------------------------- 进度

# 速度滑窗（秒）与采样上限
SPEED_WINDOW = 10.0
MAX_SPEED_SAMPLES = 600
# 界面刷新节流间隔（秒）：钩子来自多个下载线程，必须收敛刷新频率
NOTIFY_INTERVAL = 0.4
# 进度落盘间隔（秒）
SAVE_INTERVAL = 2.0
# 调度线程空转等待（秒）
WORKER_WAIT = 0.25
# 清理取消任务时，零散文件超过这个数量就先集中到临时文件夹再整体移入回收站
LOOSE_FILE_LIMIT = 20


def queue_path():
    """队列文件路径：与 conf.yml 同级（打包后为 exe 所在目录）。"""
    return os.path.join(app_dir(), QUEUE_FILENAME)


def format_size(value):
    """把字节数格式化成 "2.4 MB" 这样的短文本（界面上再补 "/s"）。"""
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    if value < 1024:
        return "%.0f B" % max(0.0, value)
    for unit in ("KB", "MB"):
        value /= 1024.0
        if value < 1024:
            return "%.1f %s" % (value, unit)
    return "%.1f GB" % (value / 1024.0)


def format_duration(seconds):
    """把秒数格式化成 mm:ss / hh:mm:ss。"""
    try:
        total = int(max(0.0, float(seconds)))
    except (TypeError, ValueError):
        return "--:--"
    hours, remain = divmod(total, 3600)
    minutes, secs = divmod(remain, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%02d:%02d" % (minutes, secs)


def _as_int(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _as_float(value):
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _error_text(error):
    """把异常整理成一行短文本（完整内容仍会进日志区）。"""
    text = str(error).strip().replace("\n", " ")
    if not text:
        text = error.__class__.__name__
    return text[:300]


def _file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


# ---------------------------------------------------------------- 任务


class DownloadTask:
    """一个下载任务（对应一个本子）。"""

    def __init__(self, seq, album_id):
        self.seq = int(seq)
        self.id = "t-%04d" % self.seq
        self.album_id = str(album_id)
        self.name = ""
        self.pages_total = 0        # album.page_count，未拿到前为 0（界面显示「页数未知」）
        self.pages_done = 0         # after_image 计数（含命中缓存而跳过的图片）
        self.bytes_done = 0
        self.status = STATUS_WAITING
        self.error = ""
        self.interrupted = False    # 上次退出时还在下载
        self.output_dir = ""
        self.pdfs = []
        self.created_at = time.time()
        self.started_at = 0.0
        self.finished_at = 0.0
        self.duration = 0.0
        # 运行期字段（不落盘）
        self.cancel_requested = False
        self.pause_requested = False
        self.skipped = False        # 本次运行是否有章节 / 图片被跳过（决定能不能算「已完成」）
        self.inflight = False       # 本次下载调用是否还在跑（暂停 / 取消后会在后台收尾）
        # 这个任务写下过的图片路径（跨轮累积）：取消时只清这些，既有的下载（一直命中
        # 缓存、从没被本任务写过）不碰。跨轮累积是必须的：暂停 → 继续会在新一轮里把
        # 上一轮写下的图片当成「已存在」跳过，若按轮记录就会漏清、留下半个文件夹。
        self.new_files = set()
        # 这个任务碰过的文件夹（章节文件夹 / 本子根目录，跨轮累积）：jmcomic 会先把
        # 文件夹建出来再逐张下图，所以「还没写入任何图片就被取消」时会留下空文件夹，
        # 只有记下文件夹本身才能在取消时把它清掉
        self.work_dirs = set()
        self.state_version = 0      # 用户意图版本：暂停 / 取消 / 继续都会 +1，用来防止
        #                             收尾时把用户刚改过的状态覆盖回去
        self.samples = deque(maxlen=MAX_SPEED_SAMPLES)

    # ---- 进度指标

    def progress(self):
        """已完成比例；总页数未知时返回 None（界面显示不定态进度条）。"""
        if not self.pages_total:
            return None
        return max(0.0, min(1.0, self.pages_done / float(self.pages_total)))

    @property
    def page_rate(self):
        """页 / 秒（滑窗）；采样不足时返回 0。"""
        return self._rate(1)

    @property
    def byte_rate(self):
        """字节 / 秒（滑窗）。"""
        return self._rate(2)

    @property
    def eta(self):
        """预计剩余秒数；页数或速度未知时返回 None。"""
        rate = self.page_rate
        if not rate or not self.pages_total:
            return None
        remain = max(0, self.pages_total - self.pages_done)
        return remain / rate

    def _rate(self, index):
        samples = self.samples
        if len(samples) < 2:
            return 0.0
        first, last = samples[0], samples[-1]
        span = last[0] - first[0]
        if span <= 0.5:
            return 0.0
        return max(0.0, (last[index] - first[index]) / span)

    # ---- 落盘

    def to_dict(self):
        return {
            "seq": self.seq,
            "id": self.id,
            "album_id": self.album_id,
            "name": self.name,
            "pages_total": self.pages_total,
            "pages_done": self.pages_done,
            "bytes_done": self.bytes_done,
            "status": self.status,
            "error": self.error,
            "interrupted": self.interrupted,
            "output_dir": self.output_dir,
            "pdfs": list(self.pdfs),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data):
        """从落盘数据还原任务；缺少本子 ID 的坏数据返回 None。"""
        if not isinstance(data, dict):
            return None
        album_id = str(data.get("album_id") or "").strip()
        if not album_id:
            return None
        task = cls(_as_int(data.get("seq")), album_id)
        task.id = str(data.get("id") or task.id)
        task.name = str(data.get("name") or "")
        task.pages_total = _as_int(data.get("pages_total"))
        task.pages_done = _as_int(data.get("pages_done"))
        task.bytes_done = _as_int(data.get("bytes_done"))
        status = str(data.get("status") or STATUS_WAITING)
        task.status = status if status in TASK_STATUSES else STATUS_WAITING
        task.error = str(data.get("error") or "")
        task.interrupted = bool(data.get("interrupted"))
        task.output_dir = str(data.get("output_dir") or "")
        task.pdfs = [str(path) for path in (data.get("pdfs") or [])]
        task.created_at = _as_float(data.get("created_at"))
        task.started_at = _as_float(data.get("started_at"))
        task.finished_at = _as_float(data.get("finished_at"))
        task.duration = _as_float(data.get("duration"))
        task.pages_done = min(task.pages_done, task.pages_total) if task.pages_total else task.pages_done
        return task


# ---------------------------------------------------------------- 过滤 / 排序（纯函数）


def filter_tasks(tasks, keyword, status):
    """按关键词（本子 ID / 名称）与状态过滤任务。"""
    keyword = (keyword or "").strip().lower()
    result = []
    for task in tasks:
        if status and status != FILTER_ALL and task.status != status:
            continue
        if keyword and keyword not in task.album_id.lower() \
                and keyword not in (task.name or "").lower():
            continue
        result.append(task)
    return result


def sort_tasks(tasks, key, desc):
    """排序：加入顺序 / 本子 ID / 名称 / 进度。"""
    if key == "id":
        ordered = sorted(tasks, key=lambda task: task.album_id)
    elif key == "name":
        ordered = sorted(tasks, key=lambda task: (task.name or "").lower())
    elif key == "progress":
        ordered = sorted(tasks, key=lambda task: (
            task.progress() if task.progress() is not None else -1.0))
    else:
        ordered = sorted(tasks, key=lambda task: task.seq)
    if desc:
        ordered.reverse()
    return ordered


# ---------------------------------------------------------------- 进度接收器


class _TaskReporter(progress_plugin.ProgressSink):
    """把插件钩子转成任务进度。

    钩子运行在 jmcomic 的下载线程里，这里只做「加锁累加 + 节流通知」，
    绝不碰任何界面控件（界面刷新由队列回调转交会话事件循环执行）。
    """

    def __init__(self, queue, task):
        self._queue = queue
        self._task = task

    def _aborted(self):
        task = self._task
        return bool(task.cancel_requested or task.pause_requested)

    def _request_abort(self):
        """请求跳过时打上标记。

        被跳过过的本子一定有页面没下（jmcomic 会把跳过的实体当作成功，不报失败），
        因此这一标记用来保证它只能停在「已暂停 / 已取消」，不会被误判成「已完成」。
        """
        with self._queue.lock:
            self._task.skipped = True
        return True

    def _record_dirs(self, dirs):
        """记下本任务碰过的文件夹（取消时用来清掉空文件夹）。"""
        with self._queue.lock:
            for path in dirs:
                if path:
                    self._task.work_dirs.add(path)

    def on_album_start(self, album):
        task = self._task
        self._record_dirs([getattr(album, "save_path", "")])
        with self._queue.lock:
            if not task.name:
                task.name = str(getattr(album, "name", "") or "")
            pages = _as_int(getattr(album, "page_count", 0))
            if pages:
                task.pages_total = pages
            task.samples.clear()
            task.samples.append((time.time(), task.pages_done, task.bytes_done))
        self._queue.notify(force=True)
        return self._request_abort() if self._aborted() else False

    def on_photo(self, photo):
        # photo.save_path 是这一章的图片文件夹：jmcomic 在 before_photo 之前就已建好，
        # 因此哪怕一张图都还没下完，取消时也能把它清掉
        self._record_dirs([getattr(photo, "save_path", "")])
        self._queue.touch(self._task)
        return self._request_abort() if self._aborted() else False

    def on_image_start(self, image):
        return self._request_abort() if self._aborted() else False

    def on_image_done(self, image):
        task = self._task
        save_path = getattr(image, "save_path", "") or ""
        with self._queue.lock:
            task.pages_done += 1
            size = _file_size(save_path)
            if size:
                task.bytes_done += size
            if save_path and not getattr(image, "exists", False):
                # 下载前目标不存在 = 这一张是本轮新写下的（取消时要清掉）
                task.new_files.add(save_path)
        self._queue.touch(task)

    def on_photo_done(self, photo):
        self._record_dirs([getattr(photo, "save_path", "")])
        self._queue.touch(self._task, force=True)

    def on_album_end(self, album):
        self._queue.touch(self._task, force=True)


# ---------------------------------------------------------------- 队列


class TaskQueue:
    """下载任务队列：调度、进度、暂停 / 取消 / 重试与持久化。"""

    def __init__(self, conf_provider, log=None, t=None, on_change=None):
        self._conf_provider = conf_provider
        self._log = log or (lambda message: None)
        self._t = t or (lambda key, **kwargs: key)
        self._on_change = on_change

        self.lock = threading.RLock()
        self._cond = threading.Condition(self.lock)
        self._tasks = []
        self._seq = 0
        self._workers = []
        self._pause_all = False
        self._stopping = False

        self._last_notify = 0.0
        self._last_save = 0.0
        # 本次会话统计（队列由闲转忙时清零），用于收尾状态提示
        self._session = {"done": 0, "failed": 0, "pdfs": 0}
        self._session_active = False
        self._session_logged = False
        # 本次会话新生成的 PDF，队列彻底空闲时统一发一次邮件
        self._pending_pdfs = []
        self._mail_sent = False

    # -------------------------------------------------- 读取（界面用）

    def tasks(self):
        with self.lock:
            return list(self._tasks)

    def find(self, task_id):
        with self.lock:
            for task in self._tasks:
                if task.id == task_id:
                    return task
        return None

    def stats(self):
        """各状态计数 + 总数。"""
        with self.lock:
            counts = {status: 0 for status in TASK_STATUSES}
            for task in self._tasks:
                if task.status in counts:
                    counts[task.status] += 1
            counts["total"] = len(self._tasks)
        return counts

    def session(self):
        with self.lock:
            return dict(self._session)

    def has_active(self):
        """是否存在排队中 / 下载中的任务（界面据此置灰按钮）。

        「已暂停但上一轮还在收尾」的任务也算活动：它仍在写文件，退出前应当提醒。
        """
        with self.lock:
            return any(task.status in ACTIVE_STATUSES or task.inflight
                       for task in self._tasks)

    def unfinished_count(self):
        with self.lock:
            return sum(1 for task in self._tasks if task.status in UNFINISHED_STATUSES)

    def is_paused(self):
        return self._pause_all

    # -------------------------------------------------- 入队与调度

    def enqueue(self, album_ids):
        """把 ID 加入队列，返回 ``(新增列表, 重复列表)``。

        已在队列里且还没结束（等待 / 下载中 / 已暂停）的本子视为重复，不重复入队。
        """
        added, duplicated = [], []
        with self.lock:
            pending = {task.album_id for task in self._tasks
                       if task.status in UNFINISHED_STATUSES}
            for raw in album_ids:
                album_id = str(raw).strip()
                if not album_id:
                    continue
                if album_id in pending:
                    duplicated.append(album_id)
                    continue
                self._seq += 1
                self._tasks.append(DownloadTask(self._seq, album_id))
                pending.add(album_id)
                added.append(album_id)
        if added:
            with self.lock:
                # 入队是明确的「我要下」动作：顺手解除队列级暂停，否则新任务会一直
                # 停在「等待中」；已经处于「已暂停」的旧任务保持暂停，不会被带起来
                self._pause_all = False
        if added:
            self.notify(force=True)
            self.save()
            self.start()
        return added, duplicated

    def update_meta(self, album_id, name="", pages_total=0):
        """补上任务详情（名称 / 总页数），只填空缺，不覆盖已有值。"""
        album_id = str(album_id).strip()
        with self.lock:
            for task in self._tasks:
                if task.album_id != album_id or task.status not in UNFINISHED_STATUSES:
                    continue
                if name and not task.name:
                    task.name = str(name)
                pages = _as_int(pages_total)
                if pages and not task.pages_total:
                    task.pages_total = pages
        self.notify(force=True)

    def start(self):
        """确保调度线程在跑（并发数取当前配置里的 task_concurrency）。

        只统计还活着的线程：万一某个线程因意外异常退出，这里会补一个新的，
        否则队列会永久卡在「等待中」再也不动。
        """
        with self.lock:
            self._workers = [worker for worker in self._workers if worker.is_alive()]
            wanted = max(1, min(4, _as_int((self._conf_provider() or {}).get(
                "app", {}).get("task_concurrency", 2)) or 2))
            while len(self._workers) < wanted:
                worker = threading.Thread(target=self._worker_loop,
                                          name="jm2pdf-queue-%d" % len(self._workers),
                                          daemon=True)
                self._workers.append(worker)
                worker.start()
            self._cond.notify_all()

    def _release_pause_if_idle(self):
        """没有未完成任务时解除「暂停全部」。

        队列被暂停、任务又被取消 / 清空之后，会剩下一个「暂停着但没有任何任务可以
        继续」的状态：新任务进不来，界面上的「继续全部」也因为找不到已暂停任务而
        置灰，用户就卡死了。这里保证队列不会停在这种死角。调用方需持有 self.lock。
        """
        if self._pause_all and not any(task.status in UNFINISHED_STATUSES
                                      for task in self._tasks):
            self._pause_all = False
            return True
        return False

    def pause_all(self):
        """暂停整个队列：全部立刻变为「已暂停」，正在下载的会在后台收尾。

        正在下载的任务不能凭空打断 jmcomic 已经发出的网络请求，所以这里**先把状态
        切成已暂停**（界面立刻有反馈），同时下发跳过请求让它在章节 / 图片边界停住；
        收尾结束后状态仍然是「已暂停」，随时可以继续。
        """
        with self.lock:
            self._pause_all = True
            for task in self._tasks:
                if task.status == STATUS_RUNNING:
                    task.pause_requested = True
                    task.state_version += 1
                    task.status = STATUS_PAUSED
                elif task.status == STATUS_WAITING:
                    task.status = STATUS_PAUSED
                    task.interrupted = False
        self.notify(force=True)
        self.save()

    def resume_all(self):
        """继续整个队列：把已暂停的任务重新排队。

        「上一轮还在收尾」的任务也会回到等待队列，调度线程会等它收尾结束后再开新的一轮
        （不会与正在收尾的那一轮抢同一批文件）。
        """
        with self.lock:
            self._pause_all = False
            for task in self._tasks:
                if task.status == STATUS_PAUSED:
                    task.status = STATUS_WAITING
                    task.interrupted = False
                    task.state_version += 1
            self._cond.notify_all()
        self.notify(force=True)
        self.save()

    # -------------------------------------------------- 单条操作

    def pause_task(self, task_id):
        """暂停单个任务：状态立刻变为已暂停，正在跑的那一轮在后台收尾。"""
        task = self.find(task_id)
        if task is None:
            return False
        with self.lock:
            if task.status == STATUS_RUNNING:
                task.pause_requested = True
            elif task.status == STATUS_WAITING:
                pass
            else:
                return False
            task.state_version += 1
            task.status = STATUS_PAUSED
        self.notify(force=True)
        self.save()
        return True

    def resume_task(self, task_id):
        """继续单个任务：回到等待队列，已下载的图片会自动跳过。"""
        return self._requeue(task_id, (STATUS_PAUSED,))

    def retry_task(self, task_id):
        """重试失败 / 已取消的任务。"""
        return self._requeue(task_id, (STATUS_FAILED, STATUS_CANCELED))

    def _requeue(self, task_id, allowed):
        task = self.find(task_id)
        if task is None or task.status not in allowed:
            return False
        with self.lock:
            # 用户明确要求跑这一条：顺带解除「暂停全部」，否则调度线程不会取任务，
            # 任务会一直停在「等待中」不动
            self._pause_all = False
            task.status = STATUS_WAITING
            task.error = ""
            task.interrupted = False
            task.cancel_requested = False
            task.pause_requested = False
            task.skipped = False
            task.state_version += 1
            self._cond.notify_all()
        self.notify(force=True)
        self.save()
        self.start()
        return True

    def cancel_task(self, task_id):
        """取消任务：状态立刻变为已取消，并清掉本轮写下的未完成内容。

        正在下载的任务不能立刻掐断已发出的请求，所以先切状态、让它在后台收尾，
        收尾结束后再清理；没有在跑的任务（等待 / 已暂停）则当场清理。
        """
        task = self.find(task_id)
        if task is None:
            return False
        clean_now = False
        with self.lock:
            if task.status == STATUS_RUNNING:
                task.cancel_requested = True
                task.state_version += 1
                task.status = STATUS_CANCELED
            elif task.status in (STATUS_WAITING, STATUS_PAUSED, STATUS_FAILED):
                task.status = STATUS_CANCELED
                task.error = ""
                task.interrupted = False
                task.state_version += 1
                # 上一轮若还在收尾，交给收尾流程清理；否则现在就能清理
                clean_now = not task.inflight
            else:
                return False
            # 取消掉最后一个未完成任务之后，别把队列留在「暂停着又没得继续」的死角
            self._release_pause_if_idle()
        self.notify(force=True)
        self.save()
        if clean_now:
            images, pdfs, dirs = self._take_cancel_targets(task)
            self._cleanup_canceled_files(task, images, pdfs, dirs)
        return True

    def remove_task(self, task_id):
        """把任务从列表里移除（只对已结束的任务开放）。"""
        with self.lock:
            for index, task in enumerate(self._tasks):
                if task.id != task_id:
                    continue
                if task.status not in FINISHED_STATUSES:
                    return False
                del self._tasks[index]
                break
            else:
                return False
            self._release_pause_if_idle()
        self.notify(force=True)
        self.save()
        return True

    def clear_finished(self):
        """清空已完成 / 已取消的任务（失败项保留，等用户重试）。"""
        with self.lock:
            before = len(self._tasks)
            self._tasks = [task for task in self._tasks
                           if task.status not in (STATUS_DONE, STATUS_CANCELED)]
            removed = before - len(self._tasks)
            if removed:
                self._release_pause_if_idle()
        if removed:
            self.notify(force=True)
            self.save()
        return removed

    # -------------------------------------------------- 通知与落盘

    def notify(self, force=False):
        """节流通知界面（force=True 时立即通知）。"""
        if self._on_change is None:
            return
        now = time.time()
        with self.lock:
            if not force and now - self._last_notify < NOTIFY_INTERVAL:
                return
            self._last_notify = now
        if self._on_change is None:
            return
        try:
            self._on_change()
        except Exception:
            pass

    def touch(self, task, force=False):
        """记录一次进度采样并通知界面（钩子线程调用）。"""
        with self.lock:
            task.samples.append((time.time(), task.pages_done, task.bytes_done))
            while len(task.samples) > 1 and time.time() - task.samples[0][0] > SPEED_WINDOW:
                task.samples.popleft()
        self.notify(force=force)
        self.maybe_save(force=force)

    def maybe_save(self, force=False):
        now = time.time()
        with self.lock:
            if not force and now - self._last_save < SAVE_INTERVAL:
                return
            self._last_save = now
        self.save()

    def save(self):
        """把队列写盘（原子写，避免中途退出留下半个文件）。"""
        with self.lock:
            data = {
                "version": QUEUE_VERSION,
                "seq": self._seq,
                "tasks": [task.to_dict() for task in self._tasks],
            }
        path = queue_path()
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except OSError:
            pass

    def load(self):
        """读取队列文件，返回恢复的未完成任务数。

        上次退出时正在下载的任务一律恢复为「已暂停」并标记中断，等用户点继续。
        """
        path = queue_path()
        if not os.path.isfile(path):
            return 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            self._backup_broken(path)
            return 0
        if not isinstance(data, dict):
            self._backup_broken(path)
            return 0

        tasks = []
        for item in (data.get("tasks") or []):
            task = DownloadTask.from_dict(item)
            if task is None:
                continue
            if task.status == STATUS_RUNNING:
                task.status = STATUS_PAUSED
                task.interrupted = True
            tasks.append(task)
        tasks = self._trim_history(tasks)
        with self.lock:
            self._tasks = tasks
            self._seq = max([_as_int(data.get("seq"))] + [task.seq for task in tasks] + [0])
            restored = sum(1 for task in tasks if task.status in UNFINISHED_STATUSES)
        self.notify(force=True)
        return restored

    @staticmethod
    def _trim_history(tasks):
        """只保留最近的若干条已结束任务（未结束的一律保留）。"""
        finished = [task for task in tasks if task.status in FINISHED_STATUSES]
        if len(finished) <= QUEUE_HISTORY_LIMIT:
            return tasks
        keep = {id(task) for task in finished[-QUEUE_HISTORY_LIMIT:]}
        return [task for task in tasks
                if task.status not in FINISHED_STATUSES or id(task) in keep]

    @staticmethod
    def _backup_broken(path):
        """队列文件损坏时备份一份，避免下次启动又踩同一个坑。"""
        try:
            os.replace(path, path + ".bad")
        except OSError:
            pass

    def shutdown(self):
        """退出前调用：落盘并停止调度线程。"""
        with self.lock:
            self._stopping = True
            self._cond.notify_all()
        self.save()

    # -------------------------------------------------- 调度线程

    def _worker_loop(self):
        while not self._stopping:
            try:
                task = self._next_task()
                if task is not None:
                    self._run_task(task)
                else:
                    self._on_idle_tick()
            except Exception:
                # 单个任务出意外不能让调度线程退出，否则队列会永久停在「等待中」
                logger.exception("下载队列调度线程异常")
                time.sleep(WORKER_WAIT)

    def _next_task(self):
        """取一个等待中的任务并置为下载中；没有就短暂等待。"""
        with self._cond:
            if self._stopping:
                return None
            if not self._pause_all:
                for task in self._tasks:
                    if task.status != STATUS_WAITING:
                        continue
                    if task.inflight:
                        # 上一轮（被暂停 / 取消的那一轮）还在收尾：等它结束再开新的一轮，
                        # 否则两轮会同时写同一批文件、进度也会互相污染
                        continue
                    task.status = STATUS_RUNNING
                    task.error = ""
                    task.interrupted = False
                    task.cancel_requested = False
                    task.pause_requested = False
                    task.skipped = False
                    task.inflight = True
                    task.started_at = time.time()
                    task.finished_at = 0.0
                    task.duration = 0.0
                    # 每次开跑都从 0 重新计页数：一轮会把整本重新走一遍（已下好的图片跳过
                    # 但也算「这页已就绪」），若沿用上一轮的计数，取消 / 暂停后重试就会
                    # 把两次的页数叠加 —— 进度超过总页数、进度条也卡住不动
                    task.pages_done = 0
                    task.bytes_done = 0
                    task.samples.clear()
                    if not self._session_active:
                        # 队列由闲转忙：开始新的一次会话统计
                        self._session = {"done": 0, "failed": 0, "pdfs": 0}
                        self._session_active = True
                        self._session_logged = False
                        self._mail_sent = False
                    return task
            self._cond.wait(WORKER_WAIT)
            return None

    def _run_task(self, task):
        """执行一个任务（在调度线程里跑，不持锁）。"""
        with self.lock:
            # 记下本轮开始时的用户意图版本：收尾时若版本变了，说明用户中途暂停 /
            # 取消 / 继续过，状态以用户的最新意图为准，不再被本轮结果覆盖
            version = task.state_version
        conf = self._conf_provider() or {}
        try:
            download_dir = conf_mod.resolve_path((conf.get("app") or {}).get("download_dir"))
            os.makedirs(download_dir, exist_ok=True)
            task.output_dir = download_dir
        except OSError as exc:
            self._finish_task(task, [], exc, version)
            return
        if not self._session_logged:
            self._session_logged = True
            self._log(self._t("log_download_dir", path=download_dir))
        self._log(self._t("log_task_start", id=task.album_id,
                          name=task.name or task.album_id))
        self.notify(force=True)

        reporter = _TaskReporter(self, task)
        progress_plugin.bind_sink(task.album_id, reporter)
        pdfs, error = [], None
        try:
            pdfs = self._download_album(task, conf)
        except Exception as exc:
            error = exc
        finally:
            progress_plugin.unbind_sink(task.album_id)
        self._finish_task(task, pdfs, error, version)

    def _download_album(self, task, conf):
        """下载单个本子，返回实际生成的 PDF 路径列表。

        与旧版整批下载保持一致：先不带登录态（避免按登录身份消耗下载额度），
        只有服务端明确表示本子取不到时才用登录态重试这一条。
        """
        try:
            result = jmcomic.download_album(
                task.album_id, build_option(conf, with_login=False, progress=True))
        except Exception as exc:
            if task.cancel_requested or task.pause_requested:
                raise
            if not (needs_login_to_view(exc) and account.is_logged_in()):
                raise
            self._log(self._t("log_retry_with_login", ids=task.album_id))
            result = jmcomic.download_album(
                task.album_id, build_option(conf, with_login=True, progress=True))
        return collect_pdfs(result)

    def _finish_task(self, task, pdfs, error, version):
        """收敛任务终态、记日志、统计会话并落盘。

        三条规则：

        - 被暂停 / 取消而跳过的章节不会出现在 jmcomic 的失败里（它把跳过当成功），
          所以终态必须由我们自己的标记决定，跳过的本子绝不判为「已完成」；
        - 本轮运行期间用户若暂停 / 取消 / 继续过（意图版本变了），状态以用户为准，
          这里只收尾，不覆盖，也不计入会话统计；
        - 取消掉的任务要把本轮写下的半成品清理掉（见 :meth:`_cleanup_canceled_files`）。
        """
        cleanup = False
        with self.lock:
            task.inflight = False
            task.finished_at = time.time()
            task.duration = task.finished_at - (task.started_at or task.finished_at)
            if pdfs:
                # PDF 按任务累积（不是按轮覆盖）：暂停过一轮再取消时，上一轮生成的
                # PDF 也要能一并清掉
                task.pdfs = list(dict.fromkeys(list(task.pdfs) + list(pdfs)))
            if task.state_version != version:
                # 用户已经决定了状态（已暂停 / 已取消 / 已继续）：状态不动，
                # 但如果最终是「已取消」，本轮写下的半成品仍要清掉
                cleanup = task.status == STATUS_CANCELED
            elif task.cancel_requested:
                task.status = STATUS_CANCELED
                task.error = ""
                cleanup = True
            elif task.pause_requested or task.skipped:
                # 兜底：有跳过却没人改过意图时，只能停在已暂停
                task.pause_requested = False
                task.interrupted = False
                task.status = STATUS_PAUSED
                task.error = ""
            elif error is not None:
                task.status = STATUS_FAILED
                task.error = _error_text(error)
                self._session["failed"] += 1
            else:
                task.status = STATUS_DONE
                task.error = ""
                if task.pages_total:
                    task.pages_done = max(task.pages_done, task.pages_total)
                self._session["done"] += 1
                self._session["pdfs"] += len(pdfs)
                for path in pdfs:
                    if path not in self._pending_pdfs:
                        self._pending_pdfs.append(path)
            if task.status == STATUS_DONE:
                # 下完了就不再需要留着清理清单
                task.new_files = set()
                task.work_dirs = set()
            self._release_pause_if_idle()
            status = task.status

        if status == STATUS_DONE:
            self._log(self._t("log_task_done", id=task.album_id, pdfs=len(pdfs)))
        elif status == STATUS_FAILED:
            self._log(self._t("log_download_failed", id=task.album_id, error=error))
        self.notify(force=True)
        self.maybe_save(force=True)
        if cleanup:
            images, cleanup_pdfs, dirs = self._take_cancel_targets(task)
            self._cleanup_canceled_files(task, images, cleanup_pdfs, dirs)

    def _take_cancel_targets(self, task):
        """取出取消时要清理的本任务产物（图片 / PDF / 碰过的文件夹），并清空记录。"""
        with self.lock:
            images = sorted(task.new_files)
            task.new_files = set()
            pdfs = [path for path in task.pdfs if os.path.isfile(path)]
            task.pdfs = []
            dirs = set(task.work_dirs) | {os.path.dirname(path) for path in images}
            task.work_dirs = set()
        return images, pdfs, dirs

    def _recycle_files(self, task, paths):
        """把零散文件移入回收站。

        逐个文件走系统回收站是很慢的（每个文件一次 shell 操作），文件一多就要几十秒；
        这里先把它们集中搬进一个临时文件夹（同盘移动只改目录项，几乎不耗时），再把
        整个文件夹一次性移入回收站，耗时与文件数量基本无关。
        """
        existing = [path for path in paths if os.path.isfile(path)]
        if not existing:
            return
        if len(existing) <= LOOSE_FILE_LIMIT:
            library.delete_to_recycle_bin(existing)
            return
        root = task.output_dir or os.path.dirname(existing[0])
        staging = os.path.join(root, ".jm2pdf-trash-%d" % int(time.time()))
        os.makedirs(staging, exist_ok=True)
        rest = []
        for index, path in enumerate(existing):
            target = os.path.join(staging, "%04d_%s" % (index, os.path.basename(path)))
            try:
                os.replace(path, target)          # 同盘移动，只是改目录项
            except OSError:
                rest.append(path)
        library.delete_to_recycle_bin([staging])
        if rest:
            library.delete_to_recycle_bin(rest)

    @staticmethod
    def _folder_belongs_to_run(folder, paths):
        """该文件夹里是否只有本任务写下的这些文件（是的话可以整个文件夹一次移走）。"""
        try:
            names = set(os.listdir(folder))
        except OSError:
            return False
        mine = {os.path.basename(path) for path in paths}
        return bool(names) and names == mine

    def _cleanup_canceled_files(self, task, images, pdfs, dirs):
        """把取消任务留下的半成品移入回收站，并清掉本任务建过、现已空的文件夹。

        只动本任务写过的文件：一直命中缓存、从没被本任务写过的旧文件一律不碰；
        非空的章节文件夹会保留，并记一行日志说明原因。
        """
        images = list(dict.fromkeys(images))
        pdfs = list(dict.fromkeys(pdfs))
        by_folder = {}
        for path in images:
            by_folder.setdefault(os.path.dirname(path), []).append(path)
        whole_dirs, loose = [], list(pdfs)
        for folder, paths in by_folder.items():
            if self._folder_belongs_to_run(folder, paths):
                whole_dirs.append(folder)     # 整个文件夹都是本任务的：一次移走
            else:
                loose.extend(paths)
        try:
            for folder in whole_dirs:
                library.delete_to_recycle_bin([folder])
            self._recycle_files(task, loose)
        except Exception as exc:      # 依赖系统回收站，失败也不能让调度线程崩掉
            self._log(self._t("log_cancel_clean_failed", id=task.album_id, error=exc))
        else:
            self._log(self._t("log_cancel_cleaned", id=task.album_id,
                              images=len(images), pdfs=len(pdfs)))
        self._cleanup_empty_dirs(task, dirs)
        self.notify(force=True)

    def _cleanup_empty_dirs(self, task, dirs):
        """清掉本任务建过、现在已空的文件夹。

        jmcomic 会先建文件夹再逐张下图，所以「刚开始下就取消」时会留下空文件夹；
        这里把空的收走。下载根目录本身绝不动，非空文件夹保留（里面有不属于本任务的
        文件）并记一行日志说明。
        """
        root = os.path.normcase(os.path.abspath(task.output_dir)) if task.output_dir else ""
        for folder in sorted(dirs, key=len, reverse=True):
            folder_abs = os.path.abspath(folder)
            if not os.path.isdir(folder_abs):
                continue
            if not root or not folder_abs:
                continue
            current = os.path.normcase(folder_abs)
            if current == root or not current.startswith(root + os.sep):
                continue                  # 只处理下载目录内部的文件夹
            try:
                if not os.listdir(folder_abs):
                    library.delete_to_recycle_bin([folder_abs])
                else:
                    self._log(self._t("log_cancel_kept_folder", path=folder_abs))
            except Exception:
                continue

    def _on_idle_tick(self):
        """没有可跑的任务时：队列彻底空闲则把本次积累的 PDF 汇总发一次邮件。"""
        with self.lock:
            if any(task.status in UNFINISHED_STATUSES for task in self._tasks):
                self._mail_sent = False       # 还有未完成的任务，不算结束
                return
            if self._mail_sent:
                return
            pdfs = list(self._pending_pdfs)
            self._mail_sent = True
            self._session_active = False
        if not pdfs:
            return
        conf = self._conf_provider() or {}
        mail_conf = conf.get("mail") or {}
        if not mail_conf.get("enable"):
            with self.lock:
                self._pending_pdfs = []
            return
        self._log(self._t("log_sending_mail"))
        try:
            send_mail(mail_conf, pdfs, self._log, self._t)
            self._log(self._t("log_mail_sent"))
        except Exception as exc:
            self._log(self._t("log_mail_failed", error=exc))
        with self.lock:
            self._pending_pdfs = [path for path in self._pending_pdfs
                                  if path not in pdfs]
