# -*- coding: utf-8 -*-
"""全局常量：应用元信息、窗口尺寸、状态颜色、路由、界面字体。

Copyright (c) 2026 WisadelZ

This work is licensed under the CC BY-NC-ND 4.0 International License.
You may obtain a copy of the License at

    https://creativecommons.org/licenses/by-nc-nd/4.0/

Unauthorized modification, distribution of modified versions,
or commercial use is strictly prohibited.
"""

APP_NAME = "jm2pdf"
APP_VERSION = "2.4.1"

# 项目信息（帮助页展示用）
APP_AUTHOR = "WisadelZ"
PROJECT_URL = "https://github.com/WisadelZ/jm2pdf"
ISSUES_URL = PROJECT_URL + "/issues"
LICENSE_NAME = "CC BY-NC-ND 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-nd/4.0/"

# 默认窗口尺寸
WINDOW_WIDTH = 660
WINDOW_HEIGHT = 700
WINDOW_MIN_WIDTH = 540
WINDOW_MIN_HEIGHT = 520

# 状态颜色
COLOR_OK = "#27ae60"
COLOR_ERR = "#c0392b"
COLOR_IDLE = "#666666"

# 路由：首页固定为探索页，下载页与任务中心都是二级页，由首页顶栏 / 下载页进入
ROUTE_MAIN = "/"
ROUTE_DOWNLOAD = "/download"
ROUTE_TASKS = "/tasks"
ROUTE_ACCOUNT = "/account"
ROUTE_FAVORITE = "/favorite"
ROUTE_SETTINGS = "/settings"
ROUTE_EXPLORER = "/explorer"
ROUTE_HELP = "/help"
ROUTE_ALBUM = "/album"

# 界面字体：微软雅黑 UI（Windows 10/11 自带），保证中英文混排字重均匀
UI_FONT_FAMILY = "Microsoft YaHei UI"
