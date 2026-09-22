# -*- coding: utf-8 -*-
"""多语言支持：简体中文 / 繁体中文 / 英文。

界面文本统一在此维护，UI 层通过 ``I18n.t(key)`` 取值。
新增文本时请在三个语言表中同时补齐同名键。
"""

LANG_ZH_CN = "zh_cn"
LANG_ZH_TW = "zh_tw"
LANG_EN = "en"

# 语言下拉框的展示顺序
LANGUAGES = (LANG_ZH_CN, LANG_ZH_TW, LANG_EN)

# 语言代码 -> 该语言自身的名称（语言选择器里始终用母语显示）
LANGUAGE_NAMES = {
    LANG_ZH_CN: "简体中文",
    LANG_ZH_TW: "繁體中文",
    LANG_EN: "English",
}


_STRINGS = {
    # ------------------------------------------------------------------
    # 简体中文
    # ------------------------------------------------------------------
    LANG_ZH_CN: {
        "window_title": "jm2pdf v{version} - 本子下载转 PDF",

        # 工具栏
        "btn_explorer": "资源管理器",
        "btn_help": "帮助",
        "btn_settings": "设置",

        # 主页 - 下载任务
        "label_ids": "本子 ID",
        "hint_ids": "多个 ID 用逗号或空格分隔",
        "btn_clear": "清空",
        "label_download_dir": "下载目录",
        "btn_browse": "浏览",

        # 主页 - 搜索
        "label_search_id": "搜索 ID",
        "btn_search": "搜索",
        "btn_add": "添加",

        # 主页 - 操作
        "switch_to_pdf": "生成 PDF",
        "btn_start": "开始下载",

        # 主页 - 下载选项
        "tile_download_options": "下载选项",
        "label_thread_image": "图片并发",
        "label_thread_photo": "章节并发",
        "label_username": "账号（可选）",
        "label_password": "密码",

        # 主页 - 邮件推送
        "tile_mail": "邮件推送",
        "switch_mail_enable": "启用邮件推送",
        "label_mail_server": "服务器",
        "label_mail_port": "端口",
        "label_mail_sender": "发件邮箱",
        "label_mail_password": "授权码",
        "label_mail_receiver": "收件邮箱（留空则发给自己）",
        "label_mail_subject": "邮件标题",
        "label_mail_body": "邮件正文",

        # 搜索结果
        "search_info": "ID: {id}\n页数: {pages} / 章节: {chapters}\n名称: {title}",
        "search_info_tags": "ID: {id}\n页数: {pages} / 章节: {chapters}\n名称: {title}\n标签: {tags}",
        "search_failed": "搜索失败：{error}",
        "search_result_log": "搜索结果：{text}",
        "search_link": "网页链接",

        # 状态提示
        "status_ready": "就绪",
        "status_search_need_id": "请先在搜索框中输入本子 ID",
        "status_searching": "搜索中...",
        "status_search_done": "搜索完成",
        "status_search_failed": "搜索失败",
        "status_add_no_result": "没有可添加的搜索结果，请先搜索",
        "status_add_exists": "ID {id} 已在列表中",
        "status_add_ok": "已添加 {id} 到下载列表",
        "status_need_ids": "请先输入至少一个本子 ID",
        "status_mail_incomplete": "已启用邮件推送：请填写发件邮箱与授权码",
        "status_downloading": "下载中...",
        "status_conf_save_failed": "配置保存失败：{error}",
        "status_done": "完成：{count} 个本子，{pdfs} 个 PDF",
        "status_done_with_errors": "完成（含失败项），详见日志",
        "status_error": "出错，详见日志",

        # 下载日志
        "log_start": "开始下载 {count} 个本子：{ids}",
        "log_download_dir": "下载目录：{path}",
        "log_download_failed": "下载失败 [{id}]：{error}",
        "log_pdf_total": "共生成 {count} 个 PDF：",
        "log_no_pdf": "未生成任何 PDF 文件",
        "log_skip_pdf": "已按设置跳过 PDF 合并",
        "log_sending_mail": "正在发送邮件...",
        "log_mail_sent": "邮件发送成功！",
        "log_mail_failed": "邮件发送失败：{error}",
        "log_no_pdf_for_mail": "没有可发送的 PDF，跳过邮件推送",
        "log_error": "发生错误：\n{error}",
        "log_attach_added": "已添加附件：{name}",
        "log_attach_failed": "警告：附件 {path} 读取失败，已跳过（{error}）",

        # 设置页
        "settings_title": "设置",
        "btn_back": "返回",
        "section_config": "配置管理",
        "desc_config": "导出当前配置以便备份，或从文件导入已有配置；导入后界面立即刷新。",
        "btn_export_conf": "导出配置",
        "btn_import_conf": "导入配置",
        "label_conf_path": "当前配置文件：{path}",
        "section_appearance": "外观设置",
        "desc_appearance": "选择界面主题，切换后立即生效。",
        "theme_light": "浅色",
        "theme_dark": "深色",
        "theme_system": "跟随系统",
        "section_language": "语言设置",
        "desc_language": "切换界面语言，切换后立即生效。",
        "status_theme_changed": "外观已切换为「{theme}」",
        "status_lang_changed": "界面语言已切换为「{language}」",
        "status_busy_restart": "任务进行中，该设置将在重启后生效",

        # 导入 / 导出
        "export_dialog_title": "导出配置",
        "import_dialog_title": "选择要导入的配置文件",
        "export_file_name": "conf.yml",
        "filter_yaml": "YAML 配置文件",
        "status_exported": "配置已导出到 {path}",
        "status_export_canceled": "已取消导出",
        "status_export_failed": "配置导出失败：{error}",
        "status_imported": "配置导入成功",
        "status_import_canceled": "已取消导入",
        "status_import_failed": "配置导入失败：{error}",

        # 资源管理器
        "explorer_title": "资源管理器",
        "explorer_dir": "目录：{path}",
        "explorer_empty": "下载目录里还没有已下载的漫画",
        "explorer_scan_failed": "扫描下载目录失败：{error}",
        "explorer_type_folder": "图片文件夹",
        "explorer_type_pdf": "PDF",
        "btn_refresh": "刷新",
        "btn_open_selected": "打开",
        "btn_delete_selected": "删除",
        "explorer_need_selection": "请先勾选要操作的漫画文件夹或 PDF",
        "status_opened": "已打开 {name}",
        "status_open_failed": "打开失败：{error}",
        "delete_dialog_title": "确认删除",
        "delete_dialog_body": "以下 {count} 项将被移入回收站（可从回收站恢复）：\n{items}",
        "btn_cancel": "取消",
        "btn_confirm_delete": "删除",
        "status_deleted": "已删除 {count} 项，可在回收站中恢复",
        "status_delete_failed": "删除失败：{error}",

        # 资源管理器 - 元数据边栏
        "panel_meta_title": "元数据",
        "panel_meta_hint": "勾选左侧的 PDF 查看元数据\n（只有 PDF 在生成时写入了元数据）",
        "panel_meta_none": "该 PDF 没有元数据，可能由旧版本生成",
        "panel_meta_failed": "元数据读取失败：{error}",
        "meta_title": "标题",
        "meta_album_id": "本子 ID",
        "meta_author": "作者",
        "meta_tags": "标签",
        "meta_pages": "页数",
        "meta_chapter": "章节序号",

        # 帮助页
        "help_title": "帮助",
        "help_version": "版本",
        "help_author": "作者",
        "help_project": "项目地址",
        "help_license": "分发协议",
        "help_disclaimer_title": "免责声明",
        "help_disclaimer": "本工具仅供学习研究使用，请遵守网站的使用条款，尊重版权与创作者权益，"
                           "请勿用于任何商业用途。\n"
                           "程序按「现状」提供，作者不对使用本工具造成的任何后果负责。\n"
                           "本项目采用 {license} 许可证：允许非商用分享，禁止商用，"
                           "禁止修改后再分发。",
        "help_issue_hint": "如遇问题或有功能建议，请前往 GitHub 项目主页提交 Issue：",
        "help_issue_link": "提交 Issue",
    },

    # ------------------------------------------------------------------
    # 繁体中文
    # ------------------------------------------------------------------
    LANG_ZH_TW: {
        "window_title": "jm2pdf v{version} - 本子下載轉 PDF",

        "btn_explorer": "資源管理器",
        "btn_help": "幫助",
        "btn_settings": "設定",

        "label_ids": "本子 ID",
        "hint_ids": "多個 ID 用逗號或空格分隔",
        "btn_clear": "清空",
        "label_download_dir": "下載目錄",
        "btn_browse": "瀏覽",

        "label_search_id": "搜尋 ID",
        "btn_search": "搜尋",
        "btn_add": "新增",

        "switch_to_pdf": "產生 PDF",
        "btn_start": "開始下載",

        "tile_download_options": "下載選項",
        "label_thread_image": "圖片並行",
        "label_thread_photo": "章節並行",
        "label_username": "帳號（可選）",
        "label_password": "密碼",

        "tile_mail": "郵件推送",
        "switch_mail_enable": "啟用郵件推送",
        "label_mail_server": "伺服器",
        "label_mail_port": "連接埠",
        "label_mail_sender": "寄件信箱",
        "label_mail_password": "授權碼",
        "label_mail_receiver": "收件信箱（留空則寄給自己）",
        "label_mail_subject": "郵件標題",
        "label_mail_body": "郵件內文",

        "search_info": "ID: {id}\n頁數: {pages} / 章節: {chapters}\n名稱: {title}",
        "search_info_tags": "ID: {id}\n頁數: {pages} / 章節: {chapters}\n名稱: {title}\n標籤: {tags}",
        "search_failed": "搜尋失敗：{error}",
        "search_result_log": "搜尋結果：{text}",
        "search_link": "網頁連結",

        "status_ready": "就緒",
        "status_search_need_id": "請先在搜尋框中輸入本子 ID",
        "status_searching": "搜尋中...",
        "status_search_done": "搜尋完成",
        "status_search_failed": "搜尋失敗",
        "status_add_no_result": "沒有可新增的搜尋結果，請先搜尋",
        "status_add_exists": "ID {id} 已在清單中",
        "status_add_ok": "已新增 {id} 到下載清單",
        "status_need_ids": "請先輸入至少一個本子 ID",
        "status_mail_incomplete": "已啟用郵件推送：請填寫寄件信箱與授權碼",
        "status_downloading": "下載中...",
        "status_conf_save_failed": "設定儲存失敗：{error}",
        "status_done": "完成：{count} 個本子，{pdfs} 個 PDF",
        "status_done_with_errors": "完成（含失敗項），詳見日誌",
        "status_error": "發生錯誤，詳見日誌",

        "log_start": "開始下載 {count} 個本子：{ids}",
        "log_download_dir": "下載目錄：{path}",
        "log_download_failed": "下載失敗 [{id}]：{error}",
        "log_pdf_total": "共產生 {count} 個 PDF：",
        "log_no_pdf": "未產生任何 PDF 檔案",
        "log_skip_pdf": "已依設定跳過 PDF 合併",
        "log_sending_mail": "正在傳送郵件...",
        "log_mail_sent": "郵件傳送成功！",
        "log_mail_failed": "郵件傳送失敗：{error}",
        "log_no_pdf_for_mail": "沒有可傳送的 PDF，跳過郵件推送",
        "log_error": "發生錯誤：\n{error}",
        "log_attach_added": "已加入附件：{name}",
        "log_attach_failed": "警告：附件 {path} 讀取失敗，已跳過（{error}）",

        "settings_title": "設定",
        "btn_back": "返回",
        "section_config": "設定管理",
        "desc_config": "匯出目前設定以便備份，或從檔案匯入既有設定；匯入後介面立即重新整理。",
        "btn_export_conf": "匯出設定",
        "btn_import_conf": "匯入設定",
        "label_conf_path": "目前設定檔：{path}",
        "section_appearance": "外觀設定",
        "desc_appearance": "選擇介面主題，切換後立即生效。",
        "theme_light": "淺色",
        "theme_dark": "深色",
        "theme_system": "跟隨系統",
        "section_language": "語言設定",
        "desc_language": "切換介面語言，切換後立即生效。",
        "status_theme_changed": "外觀已切換為「{theme}」",
        "status_lang_changed": "介面語言已切換為「{language}」",
        "status_busy_restart": "任務進行中，此設定將在重新啟動後生效",

        "export_dialog_title": "匯出設定",
        "import_dialog_title": "選擇要匯入的設定檔",
        "export_file_name": "conf.yml",
        "filter_yaml": "YAML 設定檔",
        "status_exported": "設定已匯出至 {path}",
        "status_export_canceled": "已取消匯出",
        "status_export_failed": "設定匯出失敗：{error}",
        "status_imported": "設定匯入成功",
        "status_import_canceled": "已取消匯入",
        "status_import_failed": "設定匯入失敗：{error}",

        # 資源管理器
        "explorer_title": "資源管理器",
        "explorer_dir": "目錄：{path}",
        "explorer_empty": "下載目錄裡還沒有已下載的漫畫",
        "explorer_scan_failed": "掃描下載目錄失敗：{error}",
        "explorer_type_folder": "圖片資料夾",
        "explorer_type_pdf": "PDF",
        "btn_refresh": "重新整理",
        "btn_open_selected": "開啟",
        "btn_delete_selected": "刪除",
        "explorer_need_selection": "請先勾選要操作的漫畫資料夾或 PDF",
        "status_opened": "已開啟 {name}",
        "status_open_failed": "開啟失敗：{error}",
        "delete_dialog_title": "確認刪除",
        "delete_dialog_body": "以下 {count} 項將被移入資源回收筒（可從資源回收筒還原）：\n{items}",
        "btn_cancel": "取消",
        "btn_confirm_delete": "刪除",
        "status_deleted": "已刪除 {count} 項，可從資源回收筒還原",
        "status_delete_failed": "刪除失敗：{error}",

        # 資源管理器 - 元資料邊欄
        "panel_meta_title": "元資料",
        "panel_meta_hint": "勾選左側的 PDF 檢視元資料\n（只有 PDF 在產生時寫入了元資料）",
        "panel_meta_none": "該 PDF 沒有元資料，可能由舊版本產生",
        "panel_meta_failed": "元資料讀取失敗：{error}",
        "meta_title": "標題",
        "meta_album_id": "本子 ID",
        "meta_author": "作者",
        "meta_tags": "標籤",
        "meta_pages": "頁數",
        "meta_chapter": "章節序號",

        # 說明頁
        "help_title": "說明",
        "help_version": "版本",
        "help_author": "作者",
        "help_project": "專案位址",
        "help_license": "分發條款",
        "help_disclaimer_title": "免責聲明",
        "help_disclaimer": "本工具僅供學習研究使用，請遵守網站的使用條款，尊重版權與創作者權益，"
                           "請勿用於任何商業用途。\n"
                           "程式按「現狀」提供，作者不對使用本工具造成的任何後果負責。\n"
                           "本專案採用 {license} 授權條款：允許非商用分享，禁止商用，"
                           "禁止修改後再散布。",
        "help_issue_hint": "如遇問題或有功能建議，請前往 GitHub 專案主頁提交 Issue：",
        "help_issue_link": "提交 Issue",
    },

    # ------------------------------------------------------------------
    # English
    # ------------------------------------------------------------------
    LANG_EN: {
        "window_title": "jm2pdf v{version} - Comic Downloader & PDF Merger",

        "btn_explorer": "Explorer",
        "btn_help": "Help",
        "btn_settings": "Settings",

        "label_ids": "Comic ID",
        "hint_ids": "Separate multiple IDs with commas or spaces",
        "btn_clear": "Clear",
        "label_download_dir": "Download Directory",
        "btn_browse": "Browse",

        "label_search_id": "Search ID",
        "btn_search": "Search",
        "btn_add": "Add",

        "switch_to_pdf": "Generate PDF",
        "btn_start": "Start Download",

        "tile_download_options": "Download Options",
        "label_thread_image": "Image Threads",
        "label_thread_photo": "Chapter Threads",
        "label_username": "Account (optional)",
        "label_password": "Password",

        "tile_mail": "Email Notification",
        "switch_mail_enable": "Enable Email Notification",
        "label_mail_server": "SMTP Server",
        "label_mail_port": "Port",
        "label_mail_sender": "Sender Email",
        "label_mail_password": "Auth Code",
        "label_mail_receiver": "Recipient (empty = send to yourself)",
        "label_mail_subject": "Subject",
        "label_mail_body": "Body",

        "search_info": "ID: {id}\nPages: {pages} / Chapters: {chapters}\nTitle: {title}",
        "search_info_tags": "ID: {id}\nPages: {pages} / Chapters: {chapters}\nTitle: {title}\nTags: {tags}",
        "search_failed": "Search failed: {error}",
        "search_result_log": "Search result: {text}",
        "search_link": "Web page",

        "status_ready": "Ready",
        "status_search_need_id": "Enter a comic ID in the search box first",
        "status_searching": "Searching...",
        "status_search_done": "Search completed",
        "status_search_failed": "Search failed",
        "status_add_no_result": "No search result to add, please search first",
        "status_add_exists": "ID {id} is already in the list",
        "status_add_ok": "Added {id} to the download list",
        "status_need_ids": "Enter at least one comic ID",
        "status_mail_incomplete": "Email enabled: fill in the sender email and auth code",
        "status_downloading": "Downloading...",
        "status_conf_save_failed": "Failed to save config: {error}",
        "status_done": "Done: {count} comic(s), {pdfs} PDF(s)",
        "status_done_with_errors": "Finished with errors, see log for details",
        "status_error": "Error, see log for details",

        "log_start": "Start downloading {count} comic(s): {ids}",
        "log_download_dir": "Download directory: {path}",
        "log_download_failed": "Download failed [{id}]: {error}",
        "log_pdf_total": "Generated {count} PDF(s):",
        "log_no_pdf": "No PDF file was generated",
        "log_skip_pdf": "PDF merging skipped per settings",
        "log_sending_mail": "Sending email...",
        "log_mail_sent": "Email sent successfully!",
        "log_mail_failed": "Failed to send email: {error}",
        "log_no_pdf_for_mail": "No PDF to send, skipping email notification",
        "log_error": "Error occurred:\n{error}",
        "log_attach_added": "Attached: {name}",
        "log_attach_failed": "Warning: failed to read attachment {path}, skipped ({error})",

        "settings_title": "Settings",
        "btn_back": "Back",
        "section_config": "Configuration",
        "desc_config": "Export the current configuration for backup, or import one from a file. The UI refreshes right after importing.",
        "btn_export_conf": "Export Config",
        "btn_import_conf": "Import Config",
        "label_conf_path": "Current config file: {path}",
        "section_appearance": "Appearance",
        "desc_appearance": "Choose the interface theme. It takes effect immediately.",
        "theme_light": "Light",
        "theme_dark": "Dark",
        "theme_system": "Follow System",
        "section_language": "Language",
        "desc_language": "Switch the interface language. It takes effect immediately.",
        "status_theme_changed": "Appearance switched to \"{theme}\"",
        "status_lang_changed": "Interface language switched to \"{language}\"",
        "status_busy_restart": "A task is running, this setting will apply after restart",

        "export_dialog_title": "Export Configuration",
        "import_dialog_title": "Select a configuration file to import",
        "export_file_name": "conf.yml",
        "filter_yaml": "YAML config file",
        "status_exported": "Configuration exported to {path}",
        "status_export_canceled": "Export canceled",
        "status_export_failed": "Failed to export configuration: {error}",
        "status_imported": "Configuration imported successfully",
        "status_import_canceled": "Import canceled",
        "status_import_failed": "Failed to import configuration: {error}",

        # Explorer
        "explorer_title": "Explorer",
        "explorer_dir": "Directory: {path}",
        "explorer_empty": "No downloaded comics in the download directory yet",
        "explorer_scan_failed": "Failed to scan the download directory: {error}",
        "explorer_type_folder": "Image folder",
        "explorer_type_pdf": "PDF",
        "btn_refresh": "Refresh",
        "btn_open_selected": "Open",
        "btn_delete_selected": "Delete",
        "explorer_need_selection": "Select a comic folder or PDF first",
        "status_opened": "Opened {name}",
        "status_open_failed": "Failed to open: {error}",
        "delete_dialog_title": "Confirm deletion",
        "delete_dialog_body": "The following {count} item(s) will be moved to the Recycle Bin "
                              "(recoverable):\n{items}",
        "btn_cancel": "Cancel",
        "btn_confirm_delete": "Delete",
        "status_deleted": "Deleted {count} item(s), recoverable from the Recycle Bin",
        "status_delete_failed": "Failed to delete: {error}",

        # Explorer - metadata panel
        "panel_meta_title": "Metadata",
        "panel_meta_hint": "Tick a PDF on the left to view its metadata\n"
                           "(only PDFs generated with metadata have it)",
        "panel_meta_none": "This PDF has no metadata, probably generated by an older version",
        "panel_meta_failed": "Failed to read metadata: {error}",
        "meta_title": "Title",
        "meta_album_id": "Comic ID",
        "meta_author": "Author",
        "meta_tags": "Tags",
        "meta_pages": "Pages",
        "meta_chapter": "Chapter No.",

        # Help
        "help_title": "Help",
        "help_version": "Version",
        "help_author": "Author",
        "help_project": "Project",
        "help_license": "License",
        "help_disclaimer_title": "Disclaimer",
        "help_disclaimer": "This tool is for learning and research only. Please follow the website's "
                           "terms of use, respect copyright and the rights of creators, and do not use "
                           "it for any commercial purpose.\n"
                           "The program is provided \"as is\"; the author is not responsible for any "
                           "consequence of using it.\n"
                           "This project is licensed under {license}: non-commercial sharing is allowed, "
                           "while commercial use and distribution of modified versions are prohibited.",
        "help_issue_hint": "If you run into problems or have a feature request, "
                           "please submit an issue on the GitHub project page:",
        "help_issue_link": "Submit an issue",
    },
}


class I18n:
    """语言表访问器，语言非法时回退到简体中文。"""

    def __init__(self, language=LANG_ZH_CN):
        self.language = language if language in _STRINGS else LANG_ZH_CN

    def set_language(self, language):
        self.language = language if language in _STRINGS else LANG_ZH_CN

    def t(self, key, **kwargs):
        table = _STRINGS[self.language]
        text = table.get(key)
        if text is None:
            # 当前语言缺失该键时回退中文，最终兜底为键名
            text = _STRINGS[LANG_ZH_CN].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text
