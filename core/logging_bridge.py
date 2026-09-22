# -*- coding: utf-8 -*-
"""日志桥接：把 jmcomic 的 logging 输出转发到界面日志区。"""

import logging


class UiLogHandler(logging.Handler):
    """把日志记录交给界面回调（sink）处理。"""

    def __init__(self, sink):
        super().__init__()
        self._sink = sink

    def emit(self, record):
        try:
            self._sink(self.format(record))
        except Exception:
            pass
