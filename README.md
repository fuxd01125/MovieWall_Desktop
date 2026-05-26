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
│  10 表：media · seasons · episodes ·             │
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
│   ├── __init__.py                     # 应用工厂，创建 Flask 实例，注册路由
│   ├── routes.py                       # 21 个 REST API 端点
│   ├── scanner.py                      # 文件系统扫描器（增量/全量）
│   ├── database.py                     # SQLite 层（10 表，含批量写入）
│   ├── metadata.py                     # TMDB + 豆瓣元数据编排
│   ├── douban.py                       # 豆瓣搜索爬虫 + 熔断器
│   ├── artwork.py                      # 海报/缩略图智能评分查找
│   ├── config.py                       # 配置加载、运行时/打包路径
│   ├── utils.py                        # 工具函数
│   ├── constants.py                    # 常量定义
│   └── log.py                          # 日志 + Timer 上下文管理器
├── static/                             # 前端静态资源
│   ├── app.js                          # SPA 逻辑 (~1115 行, Vanilla JS)
│   ├── style.css                       # 暗色主题样式 (~960 行)
│   └── generated/thumbs/               # ffmpeg 生成缩略图
├── templates/
│   └── index.html                      # 单页应用壳
├── tests/
│   └── test_routes.py                  # 34 个回归测试
├── desktop_app.py                      # 桌面入口（pywebview 窗口）
├── run.py                              # 开发模式启动脚本
├── build_desktop.py                    # EXE 构建脚本（PyInstaller）
├── MovieWall.spec                      # PyInstaller 备选配置
├── config.json                         # 用户配置
├── requirements.txt                    # Python 依赖
├── library.db                          # SQLite 数据库（自动生成）
├── metadata_cache.json                 # TMDB/豆瓣缓存（自动生成）
├── MovieWall.ico                       # 应用图标
├── moviewall.log                       # 应用日志（自动生成）
├── Build_EXE.bat                       # 一键构建 EXE
├── Install_Dependencies.bat            # 依赖安装
├── Clean_Old_Background.bat            # 清理旧进程
└── release/dist/
    └── MovieWall.exe                   # 打包产物（单文件 ~22MB）
```

## 后端模块详解

### `__init__.py`
Flask 应用工厂。`create_app()` 创建 Flask 实例，模板和静态目录指向 `PACKAGED_DIR`（PyInstaller 打包时使用 `sys._MEIPASS`）。注册所有路由。创建模块级 `app` 单例。

### `config.py`
系统和用户配置管理。
- **路径解析：** `runtime_dir()` 返回用户可写目录（EXE 目录或项目根目录），`packaged_dir()` 返回打包只读目录
- **文件操作：** `read_json()` / `write_json()` 线程安全的 JSON 文件读写（原子写入：先写 `.tmp` 再 `replace`）
- **配置加载：** `load_config()` 读取 `config.json`；`load_players()` 加载并验证播放器路径
- **常量：** `APP_DIR`（运行时目录）、`PACKAGED_DIR`（打包目录）、`METADATA_CACHE_FILE`（缓存文件路径）、`cache_lock`（全局线程锁）
- **副作用：** 导入时自动调用 `init_db()` 初始化数据库

### `database.py` (823 行)
SQLite 数据库层，所有持久化数据的唯一权威来源。

**10 张表：**

| 表 | 主键 | 说明 |
|---|---|---|
| `media` | `id` | 电影 & 剧集条目，字段：title, year, category, folder, path, poster, thumb 等 |
| `seasons` | `id` | 剧集季，FK → media，字段：show_id, season_number, title, folder, poster |
| `episodes` | `id` | 单集，FK → seasons，字段：season_id, episode_number, title, path, folder, thumb |
| `metadata_tmdb` | `media_id` FK | TMDB 元数据，字段：tmdb_id, title, original_title, overview, rating, date, genres(JSON), poster_url, backdrop_url, season_data(JSON), raw(JSON) |
| `metadata_douban` | `media_id` FK | 豆瓣元数据，字段：douban_id, rating, synopsis, abstract 等 |
| `metadata_douban_seasons` | `season_id` FK | 分季豆瓣元数据，字段：rating, synopsis, poster_url, cast_info, air_date |
| `ratings` | `media_id` FK | 用户评分（1-10 分） |
| `history` | `(media_id, played_at)` | 播放历史 |
| `favorites` | `media_id` FK | 收藏列表 |
| `metadata_tracker` | `key` | 扫描状态追踪（键值存储） |

**主要函数：**
- `get_conn()` — 创建 SQLite 连接（WAL 模式、外键约束、忙超时 5s）
- `init_db()` — DDL 执行 + 数据库迁移（向后兼容旧版本新增的列）
- `upsert_media/season/episode()` — 单条和批量写入（`_batch` 版本用事务包裹）
- `delete_media()` — 级联删除条目及所有关联数据
- `save_tmdb_meta()` / `load_tmdb_meta()` — TMDB 元数据持久化（始终调用，即使是空数据以清除旧数据）
- `save_douban_meta()` / `save_douban_season_meta()` — 豆瓣元数据持久化
- `build_library_dict()` — 组装完整的媒体库 JSON：合并 media + metadata + seasons + episodes

### `routes.py` (447 行)
Flask REST API，21 个端点。

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/` | 首页（index.html） |
| GET | `/api/library` | 全量媒体库（含元数据、季、集） |
| POST | `/api/scan` | 全量扫描（后台线程） |
| GET | `/api/scan/progress` | 扫描进度轮询 |
| POST | `/api/update` | 全量元数据更新（清除缓存后更新所有条目） |
| GET | `/api/artwork/<id>/<kind>` | 海报/缩略图服务（可查询 media/seasons/episodes 三张表） |
| POST | `/api/play` | 外部播放器播放（路径安全校验） |
| GET | `/api/players` | 播放器列表 |
| POST | `/api/open_folder` | 打开文件夹 |
| GET/PUT | `/api/config` | 配置读写 |
| GET/PUT/DELETE | `/api/ratings` | 评分 CRUD |
| GET/PUT | `/api/history` | 播放历史 |
| GET/PUT | `/api/favorites` | 收藏 |
| PUT/DELETE | `/api/metadata/douban/<id>` | 豆瓣 ID 管理（覆盖 + 手动评分/简介） |
| POST | `/api/update_single` | 单条目更新（清除缓存 → 重新获取元数据） |

**安全机制：** `is_allowed_media_path()` 验证播放路径在数据库中有合法记录。

### `scanner.py` (296 行)
文件系统扫描器。

**扫描流程：**
1. 增量检测：比较根目录 mtime，未变更（86400s 内）跳过全量扫描
2. 全量扫描：
   - 删除所有媒体/元数据（保留评分、历史、收藏）
   - 遍历每个分类目录（Movies / TV Shows / Anime）
   - **电影**：子文件夹 = 一部电影，最大文件 = 主视频
   - **剧集**：子文件夹 = 剧集，`Season *` 子文件夹 = 季，文件名解析集号（S01E01 / E01 / 第1集）
   - 批量写入数据库（upsert_media_batch）
   - 并行获取元数据（ThreadPoolExecutor, max 5 workers）
   - 清理孤立条目（磁盘已不存在的文件夹）

### `metadata.py` (414 行)
元数据编排引擎。

**数据流：**
```
clear_tmdb_cache()  →  清除缓存文件中的旧数据
       ↓
get_tmdb_metadata() →  L2 缓存检查 → TMDB 搜索 → 匹配评分 → 获取详情 → 一致性检查
       ↓
fetch_tmdb_seasons() →  TMDB 季数据（评分/简介/海报/播出日）
       ↓
attach_all_metadata() →  TMDB + 豆瓣组合 → 持久化到 SQLite
```

**关键函数：**
- `_tmdb_match_score()` — TMDB 搜索结果与查询的匹配度评分（0-200+ 分，阈值 50）。考虑：精确标题、部分匹配、年份、媒体类型、中文、季数
- `clear_tmdb_cache()` — 清除缓存文件中当前条目相关记录 + 所有 `tmdb:` 前缀的原始 API 缓存
- `get_tmdb_metadata()` — 搜索 TMDB，返回最佳匹配。缓存结果在 `metadata_cache.json`
- `fetch_tmdb_seasons()` — 获取 TMDB 季级数据。当主要语言（如 `zh-CN`）返回空简介时，自动 fallback 到 `en-US`
- `_final_consistency_check()` — 最终一致性检查，防止 TMDB 返回错误匹配
- `attach_all_metadata()` — 主入口：先 TMDB 后豆瓣，始终调用 `save_tmdb_meta()`（即使是空数据）

### `utils.py` (193 行)
通用工具函数。
- `stable_id()` — 确定性 16 字符 MD5 哈希 ID（用于 media/season/episode ID）
- `normalize_key()` / `clean_title()` — 文件名规范化/清洗
- `parse_year()` / `parse_season_number()` / `parse_episode_number()` — 年份/季数/集数解析
- `generate_video_image()` — ffmpeg 视频截图
- `tmdb_request()` — TMDB API v3 请求（带缓存、重试、指数退避）
- `tmdb_image()` — 构建 TMDB 图片完整 URL

**缓存策略（TMDB 请求）：**
- 两层缓存：L1 原始 API 响应（`tmdb:search/movie:query=...`）+ L2 搜索结果（`movie:title:year:lang`）
- L1 缓存键包含完整查询参数（修复历史 Bug：不同搜索不再互相污染）
- TTL 由 `metadata_cache_days` 控制（默认 60 天）
- 线程安全：`cache_lock` 全局锁

### `artwork.py` (155 行)
智能图片查找引擎。

**评分算法（`score_image_candidate`）：**
- 精确名称匹配：+160 分
- 部分名称匹配：+75 分
- 海报关键词（poster/cover/海报/封面）：+50 分
- 包含 `SxxExx`（剧集截图）：-100 分（排除）
- 文件名修改时间：微调（0-1 分）

**查找顺序：**
- `find_movie_poster()` — 旁加载 → 父文件夹 → 递归搜索 → 静态海报
- `find_show_poster()` — 父文件夹 → 非递归搜索 → 递归搜索 → 静态海报 → 第一季海报
- `find_season_poster()` — 父文件夹 → 搜索 → 递归 → 静态海报
- `find_episode_thumb()` — 旁加载 → 文件夹图片（排除海报风格，最低 40 分）

### `douban.py` (501 行)
豆瓣爬虫。

**熔断器策略：**
- HTTP 403 → 暂停 24 小时
- 超时 → 暂停 1 小时
- 网络错误 → 暂停 30 分钟
- 状态持久化在 `metadata_cache.json` 的 `douban_health` 键
- 内存缓存 60 秒 TTL 避免重复文件读取

**请求限制：** 0.5-0.8 秒随机延迟，浏览器 User-Agent 轮换，带 cookie jar。

### `constants.py`
- `VIDEO_EXTS` — 视频扩展名（.mp4, .mkv, .avi, .mov 等 10 种）
- `ART_EXTS` — 图片扩展名（.jpg, .jpeg, .png, .webp）
- `POSTER_NAMES` — 海报关键词：poster, cover, folder, 海报, 封面, 主图
- `SEASON_POSTER_NAMES` — 季海报关键词：poster, cover, folder, season, 海报, 封面, 季海报
- `THUMB_NAMES` — 缩略图关键词：thumb, thumbnail, screenshot, 剧照, 截图

### `log.py`
日志配置。默认输出到 `moviewall.log`（文件）和 stdout。`Timer` 上下文管理器用于操作计时，超过 1 秒自动记录。

## 前端模块详解

### `static/app.js` (1115 行)
纯 JavaScript SPA，无框架依赖。

**状态变量：** `library`, `activeTab`, `currentView`, `navStack`, `players`, `categoriesConfig`, `ratingsCache`, `historyCache`, `favoritesCache`

**核心函数：**
- `loadLibrary()` — 6 路并行 API 请求加载所有数据后渲染首页
- `renderHome()` / `navigateTo()` / `goBackSmart()` — 客户端路由
- `renderMovieDetail()` / `renderShowDetail()` / `renderSeasonDetail()` — 详情页
- `renderHomeCard()` / `renderSeasonCard()` / `renderEpisodeCard()` — 卡片渲染
- `starRatingWidget()` — 5 星评分 UI（内部映射 1-10 分）
- `artworkUrl()` — 海报/缩略图 URL 解析（含 TMDB / 本地 / fallback 链）
- `updateMetadata()` / `updateSingleItem()` — 触发元数据更新

**海报 URL 解析优先级（`artworkUrl()`）：**
```
剧集: TMDB 海报 → 本地文件 → 缩略图
电影: 本地海报 → TMDB 海报 → 缩略图
季:   TMDB 季海报 → 豆瓣季海报 → 本地文件 → 剧集缩略图
```

### `static/style.css` (960 行)
暗色主题 CSS。CSS 变量驱动的主题系统（`--bg`, `--accent`, `--radius` 等）。响应式断点：1200px / 1100px / 900px / 600px。

### `templates/index.html`
SPA 壳。包含 Google Fonts 引用、导航栏、搜索框、分类标签、扫描/更新/设置按钮、进度条、`#app` 容器。

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
    "Movies": "电影",
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
  "douban_enabled": true,
  "metadata_cache_days": 60,
  "tmdb_language": "zh-CN",
  "thumbnail_second": 60,
  "log_level": "INFO",
  "enable_file_log": true,
  "history_limit": 500
}
```

> TMDB API Key 在 [themoviedb.org](https://www.themoviedb.org/settings/api) 免费申请。

**配置项说明：**

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `library_root` | — | 影视媒体根目录 |
| `categories` | 见上 | 分类定义（key=文件夹名，value=显示名+类型） |
| `players` | [] | 播放器列表，支持多个 |
| `tmdb_api_key` | — | TMDB API v3 Key（必填） |
| `tmdb_language` | zh-CN | TMDB 元数据语言 |
| `metadata_cache_days` | 60 | TMDB/豆瓣缓存 TTL（天） |
| `douban_enabled` | true | 是否启用豆瓣元数据 |
| `ffmpeg_path` | ffmpeg | ffmpeg 路径 |
| `generate_thumbnails` | true | 是否自动生成缩略图 |
| `thumbnail_second` | 60 | 截图时间点（秒） |
| `history_limit` | 500 | 最大历史记录数 |

### 3. 运行

**桌面模式**（推荐）：使用 `release/dist/MovieWall.exe`

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

## 海报/缩略图优先级链

### 电影海报
1. 视频旁加载文件（`movie.mkv.jpg`）
2. 父文件夹同名称（`Movies/Zootopia 2/poster.jpg`）
3. 递归搜索电影文件夹评分图片
4. `static/posters/` 静态海报
5. TMDB 远程海报 URL
6. ffmpeg 自动生成的缩略图

### 剧集海报
1. 剧集根目录（`poster.jpg`, `{剧集名}.jpg` 等）
2. TMDB 远程海报 URL（前端 `artworkUrl()` 中优先于本地文件）
3. 第一季海报（本地或 TMDB）
4. ffmpeg 缩略图最后兜底

### 季海报
1. TMDB 季海报（通过 `fetch_tmdb_seasons()` 获取）
2. 豆瓣季海报（如配置了分季豆瓣 ID）
3. 季文件夹本地图片（`poster.jpg` 等）
4. 第一集缩略图（最后兜底）

### 分集缩略图
1. 旁加载文件（同目录同文件名不同扩展名）
2. 文件夹内评分图片（最低 40 分，排除海报风格）
3. ffmpeg 截图（`thumbnail_second` 秒处）

## 元数据系统

### TMDB 匹配算法

搜索结果的匹配度评分（`_tmdb_match_score`，阈值 ≥ 50）：

| 条件 | 分数 |
|------|------|
| 精确标题匹配 | +100 |
| 部分标题包含 | +60 |
| Token 模糊匹配 | 最高 +40 |
| 年份匹配 | +40 |
| 年份不匹配 | -20 |
| 媒体类型匹配 | +20 |
| 媒体类型不匹配 | -30 |
| 中文查询 + 中文原始语言 | +15 |
| 季数精确匹配（剧集） | +25 |
| 季数差 > 3（剧集） | -30 |

### 缓存系统

两层独立缓存，全部存储在 `metadata_cache.json`：

| 层级 | 缓存键格式 | 说明 |
|------|-----------|------|
| L1: 原始 API | `tmdb:{endpoint}:{sorted_params}` | TMDB API 原始响应（如 `tmdb:search/tv:language=zh-CN&query=真爱不死`） |
| L2: 搜索结果 | `{type}:{title}:{year}:{lang}` | 处理后的元数据（如 `tv:santa clarita diet:2017:zh-CN`） |
| 季数据 | `season:{tmdb_id}:{sn}:{lang}` | 分季 TMDB 数据 |

**缓存刷新：**
- **全量更新**（`/api/update`）：清除所有 L1 + L2 缓存，重新获取所有条目的 TMDB + 豆瓣元数据
- **单条目更新**（`/api/update_single`）：清除该条目的相关缓存后重新获取
- **强制跳过缓存**：`force_refresh=True` 参数（在 `get_tmdb_metadata` 中跳过 L2 缓存）

> ⚠️ 注意：L1 缓存键包含完整查询参数但不含 API Key，不同搜索不互相污染（修复了历史 Bug）

### 元数据刷新流程

```
POST /api/update
    ↓
clear_tmdb_cache()  →  删除 metadata_cache.json 中所有相关键 + 所有 tmdb: 前缀键
    ↓
get_tmdb_metadata(force_refresh=True)
    → 跳过 L2 缓存
    → tmdb_request(search/movie, {query, language, ...})
        → 跳过 L1 缓存（已被清除）
        → HTTP GET api.themoviedb.org/3/search/movie?...
        → 返回结果，缓存到 L1
    → 评分匹配（_tmdb_match_score）
    → 获取详情（movie/{id}）
    → 最终一致性检查
    ↓
fetch_tmdb_seasons()  （仅剧集）
    → 每季调用 tmdb_request(tv/{id}/season/{n}, {language})
    → 如果 zh-CN 简介为空，尝试 en-US 兜底
    ↓
save_tmdb_meta()  →  写入 SQLite metadata_tmdb 表
    ↓
fetch_douban_meta()  →  豆瓣搜索 + 详情
    ↓
save_douban_meta()  →  写入 SQLite metadata_douban 表
```

## 测试

```bash
python -m pytest tests/ -v
```

现有 34 个测试，12 个测试类：

| 测试类 | 测试数 | 说明 |
|--------|--------|------|
| `TestIsAllowedMediaPath` | 4 | 播放路径安全验证 |
| `TestApiPlayEpisodeRoute` | 4 | 播放 API 集成测试 |
| `TestIsAllowedFolder` | 2 | 文件夹路径验证 |
| `TestDBEpisodeDataIntegrity` | 2 | 数据库完整性 |
| `TestTmdbMatchScore` | 7 | TMDB 匹配评分算法 |
| `TestSeasonPosterPriority` | 3 | 海报优先级链 |
| `TestFinalConsistencyCheck` | 4 | 一致性检查 + 空数据清除 |
| `TestSeasonCountValidation` | 2 | 季数评分验证 |
| `TestClearTmdbCache` | 3 | 缓存清除（含 tmdb: 前缀） |
| `TestAttachMetadataAlwaysSaves` | 1 | 空数据保存 |
| `TestOrphanCleanup` | 2 | 孤立条目清理 |

## 构建 EXE

### 方式一：一键构建
双击 `Build_EXE.bat`。

### 方式二：命令行
```bash
python build_desktop.py
```

### 输出
`release/dist/MovieWall.exe`（约 22 MB）。运行时在 exe 同目录自动生成 `library.db`、`metadata_cache.json`、`moviewall.log`、`static/generated/thumbs/`。

## 常见问题

### Q: TMDB 返回的数据不对（匹配到了错误的影片）？
可能是缓存问题。在 UI 中点击"更新"按钮触发全量元数据刷新，这会清除所有缓存并重新从 TMDB 获取数据。如果仍然错误，可能是 TMDB 搜索匹配算法不够精确，可以在 `metadata.py` 中调整 `_TMDB_MATCH_THRESHOLD`（默认 50）或在 `_tmdb_match_score()` 中增加更严格的匹配规则。

### Q: TMDB 元数据更新后电影/剧集信息仍然不变？
有两个缓存层都需要清除：
1. **L1 原始 API 缓存**（`metadata_cache.json` 中 `tmdb:` 前缀的键）
2. **L2 搜索结果缓存**（`metadata_cache.json` 中 `movie:/tv:` 前缀的键）
`clear_tmdb_cache()` 现在同时清除这两层。如果更新后还没变化，检查 `metadata_cache_days` 配置，或手动删除 `metadata_cache.json` 文件后重启应用。

### Q: 季卡片显示剧集缩略图而不是季海报？
这是已被修复的已知 Bug。现在 TMDB 季海报优先于本地剧集缩略图。执行一次"更新元数据"后可见效果。

### Q: 季没有剧情简介？
TMDB API 在 `zh-CN` 语言下经常返回空的季级简介（即使英文版有数据）。代码已添加 fallback 机制：当 `zh-CN` 简介为空时自动请求 `en-US` 版本。执行一次"更新元数据"后可见效果。如果 TMDB 在所有语言下都没有该季的简介（例如某些剧集的第一季），则无法显示。

### Q: 首页的剧集海报和详情页不一致？
这是已被修复的已知 Bug。现在 `artworkUrl()` 对剧集类型优先返回 TMDB 海报。执行一次"更新元数据"后可见效果。

### Q: 扫描没有找到影片？
检查 `config.json` 的 `library_root` 和 `categories` 配置是否正确。确保目录结构符合规范。注意分类名是文件夹名（key），不是显示名（value）。

### Q: 剧集无法播放？
检查 `is_allowed_media_path` 是否通过了 episodes 表验证。

### Q: 海报不显示？
- 检查 TMDB API Key 是否配置正确
- 检查 `metadata_enabled` 是否为 `true`
- 执行"更新元数据"操作
- 如果使用本地海报，检查文件名是否符合 `POSTER_NAMES`

### Q: 豆瓣没有数据？
豆瓣目前有 WAF 防护，可能返回 403。熔断器会自动暂停 24h。可通过设置面板手动输入豆瓣 ID 和评分。也可修改 `douban.py` 中的熔断器参数。

### Q: ffmpeg 有什么用？
自动从视频中截取缩略图。未安装也能正常使用，只是没有自动缩略图。

### Q: 用户数据存在哪里？
所有数据在 exe 同目录：
- `config.json` — 用户配置
- `library.db` — SQLite 数据库（媒体、元数据、评分、历史、收藏）
- `metadata_cache.json` — TMDB/豆瓣 API 缓存
- `static/generated/thumbs/` — 自动生成的视频缩略图
- `moviewall.log` — 应用日志

### Q: 如何切换播放器？
在 `config.json` 的 `players` 数组中添加多个播放器路径，在"更多"菜单中可切换。

### Q: 关闭窗口后还有后台进程吗？
桌面版在窗口关闭时自动终止 Flask 服务器，无残留进程。如遇到端口占用，运行 `Clean_Old_Background.bat`。

### Q: 如何重置所有数据？
关闭应用后删除 `library.db` 和 `metadata_cache.json`，重新启动应用即可。
