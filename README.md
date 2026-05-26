# MovieWall Desktop

MovieWall 是一个本地影视海报墙桌面应用。它扫描本地影视目录，生成类似流媒体平台的海报墙界面，支持通过 PotPlayer / VLC 等外部播放器播放视频。对接 TMDB + 豆瓣双数据源获取元数据，提供独立的用户评分系统。

## 架构

```
┌─────────────────────────────────────────────────┐
│              Desktop Window                      │
│  (pywebview — Edge Chromium, 1280×820)          │
├─────────────────────────────────────────────────┤
│           Single-Page Frontend                   │
│  Vanilla JS · 分类/搜索/详情/剧集/评分/设置     │
├─────────────────────────────────────────────────┤
│              Flask Backend (REST API)             │
│  routes.py · scanner.py · database.py · metadata │
├─────────────────────────────────────────────────┤
│              SQLite (library.db)                  │
│  8 表：media · seasons · episodes ·              │
│  metadata_tmdb · metadata_douban ·               │
│  ratings · history · favorites                    │
└─────────────────────────────────────────────────┘
```

## 功能特性

| 特性 | 说明 |
|------|------|
| 自动扫描 | 递归扫描影视目录，自动识别电影/剧集/动漫 |
| 增量扫描 | 基于目录 mtime 跳过未变更的扫描 |
| 海报墙 | 支持本地海报 + TMDB 远程海报 + ffmpeg 自动缩略图 |
| TMDB 元数据 | 简介、评分、类型、海报、背景图、分季信息 |
| 豆瓣元数据 | 评分、评分人数、剧情简介（支持分季）、演员信息 |
| 豆瓣熔断器 | HTTP 403 后自动暂停 24h，避免 IP 被封 |
| 双评分系统 | TMDB + 豆瓣评分并列展示 |
| 用户评分 | 独立的"我的评分"系统（10 分制），电影/剧集/季均可评分 |
| 剧集浏览器 | 季-集层级展开，支持分季海报、进度追踪 |
| 多播放器 | 支持 PotPlayer / VLC 等，可通过设置菜单切换 |
| 播放历史 | 自动记录播放位置，支持"继续观看" |
| 收藏系统 | 收藏列表，支持按分类筛选 |
| 搜索 | 跨类型全文搜索 |
| 设置面板 | 图形化编辑目录分类、豆瓣 ID 覆盖 |
| 路径安全 | `is_allowed_media_path` 验证播放路径合法性 |
| 单文件 EXE | PyInstaller --onefile 打包，开箱即用 |

## 目录结构

```
MovieWall_Desktop_V15_Rating_UI/
├── moviewall/                          # Flask 后端
│   ├── __init__.py                     # 应用工厂 (Flask app factory)
│   ├── routes.py                       # API 路由 (~20 endpoints)
│   ├── scanner.py                      # 文件系统扫描器
│   ├── database.py                     # SQLite 层（含批量写入）
│   ├── metadata.py                     # TMDB + 豆瓣元数据编排
│   ├── douban.py                       # 豆瓣搜索爬虫 + 熔断器
│   ├── artwork.py                      # 海报/缩略图智能评分查找
│   ├── config.py                       # 配置加载（运行时/打包路径）
│   ├── utils.py                        # 工具函数（ID 生成、ffmpeg、TMDB 请求）
│   ├── constants.py                    # 视频扩展名、海报命名常量
│   └── log.py                          # 日志 + Timer 上下文管理器
├── static/                             # 前端静态资源
│   ├── app.js                          # SPA 逻辑 (~1100 行, Vanilla JS)
│   ├── style.css                       # 暗色主题样式 (~960 行)
│   └── generated/thumbs/               # ffmpeg 生成缩略图
├── templates/
│   └── index.html                      # 单页应用壳
├── tests/
│   └── test_routes.py                  # 路径验证回归测试
├── desktop_app.py                      # 桌面入口（pywebview 窗口）
├── run.py                              # 开发模式启动脚本
├── build_desktop.py                    # EXE 构建脚本（PyInstaller）
├── MovieWall.spec                      # PyInstaller 备选配置
├── config.json                         # 用户配置
├── requirements.txt                    # Python 依赖
├── library.db                          # SQLite 数据库（自动生成）
├── metadata_cache.json                 # TMDB/豆瓣缓存（自动生成）
├── MovieWall.ico                       # 应用图标
├── Build_EXE.bat                       # 一键构建 EXE
├── Install_Dependencies.bat            # 依赖安装
├── Clean_Old_Background.bat            # 清理旧进程
└── release/dist/
    └── MovieWall.exe                   # 打包产物（单文件 ~22MB）
```

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/library` | 全量媒体库数据（含季/集） |
| POST | `/api/scan` | 启动全量扫描 |
| GET | `/api/scan/progress` | 扫描进度轮询 |
| POST | `/api/update` | 仅更新元数据（不重新扫描） |
| POST | `/api/play` | 启动外部播放器 |
| GET | `/api/players` | 播放器列表 |
| POST | `/api/open_folder` | 打开文件所在文件夹 |
| GET/PUT | `/api/config` | 获取/更新配置 |
| GET/PUT/DELETE | `/api/ratings` | 评分 CRUD |
| GET/PUT | `/api/history` | 播放历史 |
| GET/PUT | `/api/favorites` | 收藏 |
| GET | `/api/artwork/<id>/<kind>` | 海报/缩略图 |
| PUT/DELETE | `/api/metadata/douban/<id>` | 豆瓣 ID 管理 |
| POST | `/api/update_single` | 单条目更新 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

或双击 `Install_Dependencies.bat`。

### 2. 配置

编辑 `config.json`：

```json
{
  "library_root": "F:\\Download\\影视",
  "categories": {
    "Movies": {"name": "电影", "type": "movie"},
    "TV Shows": {"name": "剧集", "type": "show"},
    "Anime": {"name": "动漫", "type": "show"}
  },
  "tmdb_api_key": "你的 TMDB API Key",
  "players": [
    {"name": "PotPlayer", "path": "D:\\software\\PotPlayer\\PotPlayerMini64.exe"}
  ],
  "ffmpeg_path": "ffmpeg",
  "generate_thumbnails": true,
  "metadata_enabled": true,
  "douban_enabled": true
}
```

> TMDB API Key 在 [themoviedb.org](https://www.themoviedb.org/settings/api) 免费申请。

### 3. 运行

**桌面模式**（推荐）：双击 `Run_Desktop_Debug.bat`（或使用 `release/dist/MovieWall.exe`）

**开发模式**：

```bash
python run.py
```

打开浏览器访问 `http://127.0.0.1:5000`。

## 影视目录规范

```
F:/Download/影视
├── Movies/                            # 电影目录
│   └── Zootopia 2 (2025)/
│       ├── Zootopia 2 (2025).mkv
│       └── poster.jpg                 # 本地海报（可选）
├── TV Shows/                          # 剧集目录
│   └── 汉尼拔/
│       ├── poster.jpg                 # 剧集海报（可选）
│       └── Season 01/
│           ├── Hannibal S01E01.mkv
│           └── poster.jpg             # 季海报（可选）
└── Anime/                             # 动漫目录
    └── 葬送的芙莉莲 (2023)/
        └── Season 01/
            ├── Frieren - S01E29.mkv
            └── Frieren - S01E30.mkv
```

### 扫描规则

- **电影**：每个子文件夹（或根目录下的单独视频文件）识别为一部电影
- **剧集**：子文件夹识别为剧集，其下的 `Season *` 子文件夹识别为季
- **名称解析**：自动识别 `S01E01`、`E01`、`第1集`、`第 1 集` 等格式

## 元数据系统

### TMDB

- 搜索匹配：按 `title + year` 搜索
- 缓存：`metadata_cache_days`（默认 30 天）内复用缓存
- 存储：`metadata_tmdb` 表（含 `season_data` JSON 字段）

### 豆瓣

- 搜索：豆瓣电影搜索 API（模拟浏览器）
- 熔断器：
  - HTTP 403 → 暂停 24 小时
  - 超时 → 暂停 1 小时
  - 网络错误 → 暂停 30 分钟
- 支持分季搜索（"汉尼拔 第二季"）
- 支持手动豆瓣 ID 覆盖
- 手机端页面抓取剧情简介、演员信息
- 自动下载分季海报

### 评分展示

```
┌─────────────────────────────────────────┐
│  豆瓣 9.2    TMDB 8.5    128,456 评    │
│  我的评分 ★★★★★★☆☆☆☆  6.0  [清除]    │
└─────────────────────────────────────────┘
```

## 海报命名规则

| 位置 | 支持的文件名（按优先级） |
|------|------------------------|
| 电影文件夹 | `poster.jpg`, `cover.jpg`, `folder.jpg`, `海报.jpg`, `封面.jpg` |
| 剧集根目录 | `poster.jpg`, `{剧集名}.jpg`, `show.jpg`, `系列.jpg` |
| Season 文件夹 | `poster.jpg`, `season.jpg`, `季海报.jpg` |
| 分集缩略图 | `{视频同名}.jpg`（自动 ffmpeg 截图兜底） |

**评分算法**：按文件名关键词智能打分（海报相关词 +60~160 分，含有 `SxxExx` 的图 -100 分避免误匹配）。

## 测试

```bash
python -m pytest tests/ -v
```

现有测试：12 个用例（路径验证回归、播放 API、DB 完整性）。

## 构建 EXE

### 方式一：一键构建

双击 `Build_EXE.bat`，自动完成依赖安装 + 打包。

### 方式二：命令行

```bash
python build_desktop.py
```

### 构建说明

- PyInstaller `--onefile` 单文件模式
- `--noconsole` 隐藏控制台
- 自动内嵌 `templates/`、`static/`、`MovieWall.ico`
- 自动处理 `pywebview` 的 hidden import

### 输出

`release/dist/MovieWall.exe`（约 22 MB）。运行时在 exe 同目录自动生成 `library.db`、`metadata_cache.json`、`static/generated/thumbs/`。

## 数据库架构

| 表 | 说明 |
|----|------|
| `media` | 电影 & 剧集条目（path 为电影文件路径，show 仅存 folder） |
| `seasons` | 剧集季信息（show_id → season_number） |
| `episodes` | 单集信息（season_id → episode_number, path） |
| `metadata_tmdb` | TMDB 元数据（全量 JSON 存储） |
| `metadata_douban` | 豆瓣元数据（评分、简介） |
| `metadata_douban_seasons` | 分季豆瓣元数据 |
| `ratings` | 用户评分（media_id → 1-10 分） |
| `history` | 播放历史（支持 episode_id 追踪） |
| `favorites` | 收藏列表 |

## 常见问题

**Q: 扫描没有找到影片？**  
检查 `config.json` 的 `library_root` 和 `categories` 配置是否正确。确保目录结构符合规范。

**Q: 剧集无法播放？**  
检查 `is_allowed_media_path` 是否通过了 episodes 表验证（v15 版本已修复此回归问题）。

**Q: 没有海报怎么办？**  
将海报图片放入对应文件夹（见上表），或配置 TMDB API Key 自动拉取远程海报。重新扫描后生效。

**Q: 豆瓣没有数据？**  
豆瓣目前有 WAF 防护，可能返回 403。熔断器会自动暂停 24h。可通过设置面板手动输入豆瓣 ID 和评分。

**Q: ffmpeg 有什么用？**  
自动从视频中截取缩略图。未安装也能正常使用，只是没有自动缩略图。

**Q: 用户数据存在哪里？**  
所有数据在 exe 同目录：`config.json`、`library.db`、`metadata_cache.json`、`static/generated/thumbs/`。

**Q: 如何切换播放器？**  
在 `config.json` 的 `players` 数组中添加多个播放器路径，在"更多"菜单中可切换。

**Q: 关闭窗口后还有后台进程吗？**  
桌面版在窗口关闭时自动终止 Flask 服务器，无残留进程。
