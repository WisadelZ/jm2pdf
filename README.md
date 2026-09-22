# Jm2PDF v2.1.0 - 禁漫本子下载工具 📚

一个开源免费的禁漫（jmcomic）本子下载、搜索和 PDF 合并工具，支持批量操作和邮件推送。

[![License: CC BY-NC-ND 4.0](https://img.shields.io/badge/License-CC%20BY--NC--ND%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-nd/4.0/)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-10%2B-green.svg)](https://www.microsoft.com/windows)

## ✨ 特性

- **智能搜索**：输入本子 ID 即可获取详细信息（名称、页数、章节、标签）
- **批量下载**：支持逗号/空格分隔的多个 ID，一次下载多个本子
- **自动合并 PDF**：每个章节自动合并为 PDF 文件，可通过「生成 PDF」开关自由关闭
- **邮件推送**：可选将生成的 PDF 通过邮件发送（支持 QQ/163 等邮箱）
- **可配置性**：自定义下载目录、并发数、账号密码等设置，界面修改自动同步到 conf.yml
- **配置导入导出**：一键导出当前配置备份，或从文件导入已有配置
- **多语言**：内置简体中文、繁体中文、英文三种界面语言，切换后立即生效
- **主题切换**：支持浅色 / 深色 / 跟随系统三种外观，切换后立即生效
- **开源共享**：CC BY-NC-ND 4.0 许可证，允许非商用分享

## 🚀 快速开始

### 方式一：使用预编译版本（推荐）

1. 访问 [Releases](https://github.com/WisadelZ/jm2pdf/releases) 页面
2. 下载最新的 `jm2pdf-v2.1.0.exe`
3. 双击运行，输入本子 ID 即可开始使用

### 方式二：从源码构建

```bash
# 克隆仓库
git clone https://github.com/WisadelZ/jm2pdf.git
cd jm2pdf

# 安装依赖
python -m pip install -r requirements.txt

# 运行（调试）
python app.py

# 打包成单文件 exe（内部调用 flet pack）
python build.py
```

## 📖 使用说明

### 基本流程

1. **输入本子 ID**：在"本子 ID"框中输入本子编号（如：`1462837`）
2. **选择下载目录**：指定保存位置（默认 `./download`）
3. **生成 PDF 开关**：主界面可直接切换是否合并 PDF
4. **配置选项**（折叠面板，可选展开）：
   - 图片/章节并发数：调整下载速度
   - 账号密码：如需登录（可选）
5. **点击"开始下载"**：等待完成

### 搜索功能

1. 在"搜索 ID"框中输入本子 ID（回车或点击"搜索"）
2. 查看返回的信息（自动换行，无需拖动）：
   ```
   ID: 422866
   页数: 2 / 章节: 1
   名称: [MANA] 神里绫华 1 (原神) [中国语] [无修正]
   标签: cosplay, 原神, 神里绫华
   ```
3. 点击"添加"按钮将其加入下载列表

### 邮件推送（可选）

展开"邮件推送"面板：
1. 打开"启用邮件推送"开关
2. 填写 SMTP 服务器信息：
   - 服务器：`smtp.qq.com`（QQ邮箱）或 `smtp.163.com`（163邮箱）
   - 端口：`465`（SSL）或 `25`（非加密）
   - 发件箱：你的邮箱地址
   - 授权码：邮箱的授权码（不是登录密码！）
   - 收件箱：留空则发给自己
3. 下载完成后会自动发送邮件

### 设置

主界面左上角的「设置」按钮可打开设置页，包含三个分区：

- **配置管理**：导出当前配置到指定文件备份，或从文件导入已有配置（导入后界面立即刷新）
- **外观设置**：浅色 / 深色 / 跟随系统
- **语言设置**：简体中文 / 繁体中文 / English

外观与语言切换后立即生效，无需重启；下载任务进行中时修改语言会在重启后生效。

## 📁 项目结构

```
jm2pdf/
├── app.py                      # 程序入口（仅创建窗口）
├── build.py                    # flet pack 打包脚本
├── conf.yml                    # 配置模板
├── icon.ico                    # 应用图标
├── requirements.txt            # 依赖清单
├── LICENSE                     # CC BY-NC-ND 4.0 许可证
├── README.md                   # 项目说明
├── CHANGELOG.md                # 更新日志
├── DEPLOYMENT.md               # 发布指南
├── .gitignore                  # Git 忽略规则
├── core/                       # 业务逻辑层（不依赖 Flet）
│   ├── constants.py            # 全局常量与应用元信息
│   ├── config.py               # 路径解析、conf.yml 读写、导入导出
│   ├── downloader.py           # jmcomic 选项构建、PDF 收集、邮件发送
│   └── logging_bridge.py       # jmcomic 日志转发到界面
├── ui/                         # 界面层
│   ├── app_ui.py               # 协调器：路由、状态、配置持久化、业务调度
│   ├── main_page.py            # 主页（下载、搜索、日志）
│   └── settings_page.py        # 设置页（配置管理、外观、语言）
└── utils/                      # 通用工具层
    ├── i18n.py                 # 多语言文本表
    └── helpers.py              # 通用辅助函数
```

代码按「业务逻辑 / 界面 / 工具」三层拆分，各层职责单一、互不耦合，新增功能时只需在对应层增加模块。

## ⚙️ 配置说明

首次运行时会自动生成 `conf.yml`，可手动编辑：

```yaml
app:
  download_dir: ./download      # 下载目录
  to_pdf: true                  # 是否合并为 PDF
  thread_image: 30              # 图片并发数
  thread_photo: 16              # 章节并发数
  username: ''                  # 登录账号（可选）
  password: ''                  # 登录密码（可选）
  theme_mode: light             # 界面主题：light / dark / system
  language: zh_cn               # 界面语言：zh_cn / zh_tw / en

mail:
  enable: false                 # 是否启用邮件
  server: smtp.qq.com           # SMTP 服务器
  port: 465                     # 端口
  sender: ''                    # 发件邮箱
  password: ''                  # 授权码
  receiver: ''                  # 收件邮箱（留空=自己）
```

## 🔧 技术栈

- **Python**: 3.12+
- **GUI框架**: Flet（现代化跨平台 UI 框架）
- **核心库**: jmcomic（禁漫客户端）、Pillow（图像处理）
- **打包工具**: flet pack / PyInstaller（单文件 exe）

## 🙏 反馈与建议

欢迎提交 Issue 报告问题或提出建议！

由于本项目采用 CC BY-NC-ND 4.0 许可证（禁止衍生作品），因此不接受 Fork 修改后的 Pull Request。如有功能需求或 Bug，请直接通过 Issue 反馈。

## 📄 许可证

Copyright (c) 2026 WisadelZ

This work is licensed under the CC BY-NC-ND 4.0 International License.
You may obtain a copy of the License at

    https://creativecommons.org/licenses/by-nc-nd/4.0/

## 🙏 致谢

- jmcomic 禁漫客户端库
- Flet 与 Python 社区及所有开源贡献者

---

**注意**：本工具仅用于学习研究，请遵守网站的使用条款，尊重版权和创作者权益。
