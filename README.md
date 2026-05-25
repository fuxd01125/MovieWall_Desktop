# MovieWall Desktop

MovieWall 是一个本地影视海报墙桌面应用。它会读取你的本地影视目录，生成类似流媒体平台的海报墙界面，并通过 PotPlayer 播放本地视频。支持 TMDB / 豆瓣元数据、自定义评分、缩略图自动生成。

## 功能特性

- 自动扫描本地影视文件夹，生成电影 / 剧集 / 动漫海报墙
- 对接 TMDB API 获取简介、评分、类型、海报等元数据
- 豆瓣评分与简介抓取（支持分季评分）
- 独立的"我的评分"系统，支持电影、剧集、每一季单独评分
- ffmpeg 自动截取视频缩略图
- 自定义播放器（默认 PotPlayer）
- 本地海报支持（`poster.jpg` / `cover.jpg` / `folder.jpg` 等）
- 单文件 EXE 打包，开箱即用

## 目录结构

```
MovieWall_Desktop_V15_Rating_UI/
├── moviewall/                  # Flask 后端
│   ├── __init__.py             # 应用工厂
│   ├── scanner.py              # 媒体文件扫描
│   ├── database.py             # SQLite 数据库操作
│   ├── metadata.py             # TMDB / 豆瓣元数据
│   ├── config.py               # 配置加载
│   ├── routes.py               # API 路由
│   ├── utils.py                # 工具函数
│   ├── artwork.py              # 海报查找
│   ├── constants.py            # 常量定义
│   ├── douban.py               # 豆瓣爬虫
│   └── log.py                  # 日志配置
├── static/                     # 前端静态资源
├── templates/                  # Jinja2 模板
├── config.json                 # 配置文件
├── library.db                  # SQLite 数据库
├── metadata_cache.json         # TMDB / 豆瓣缓存
├── desktop_app.py              # 桌面入口（pywebview）
├── run.py                      # 开发服务器入口
├── requirements.txt            # Python 依赖
├── build_desktop.py            # EXE 构建脚本
├── MovieWall.spec              # PyInstaller 配置
├── Build_EXE.bat               # 一键构建 EXE
├── Install_Dependencies.bat    # 依赖安装
├── Run_Desktop_Debug.bat       # 调试运行
├── Clean_Old_Background.bat    # 清理旧进程
├── release/                    # 打包输出目录
│   ├── build.bat               # 重新打包脚本
│   ├── README.txt              # 发布版使用说明
│   ├── logs/                   # 运行日志
│   └── dist/
│       ├── MovieWall.exe       # 单文件 exe
│       ├── config.json         # 配置文件
│       └── MovieWall.ico       # 应用图标
└── MovieWall.ico               # 应用图标
```

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
    "TV Shows": "剧集",
    "Anime": "动漫"
  },
  "tmdb_api_key": "你的 TMDB API Key",
  "players": [],
  "ffmpeg_path": "ffmpeg",
  "metadata_enabled": true,
  "douban_enabled": true
}
```

> TMDB API Key 在 [themoviedb.org](https://www.themoviedb.org/settings/api) 免费申请。

### 3. 运行

**桌面模式**（推荐）：双击 `Run_Desktop_Debug.bat`

**开发模式**：

```bash
python run.py
```

打开浏览器访问 `http://127.0.0.1:5000`。

**发布版**：运行 `release/dist/MovieWall.exe`（单文件，无需 Python 环境）。

## 影视目录规范

推荐目录结构：

```
F:/Download/影视
├── Movies/                          # 电影
│   └── Zootopia 2 (2025)/
│       ├── Zootopia 2 (2025).mkv
│       └── poster.jpg
├── TV Shows/                        # 剧集
│   └── Inside No. 9 (2014)/
│       ├── poster.jpg
│       └── Season 06/
│           ├── Inside No. 9 - S06E01.mkv
│           └── Inside No. 9 - S06E01.jpg
└── Anime/                           # 动漫
    └── 葬送的芙莉莲 (2023)/
        └── Season 01/
            ├── Frieren - S01E29.mkv
            └── Frieren - S01E30.mkv
```

## 海报命名规则

| 位置 | 支持的文件名 |
|------|-------------|
| 电影文件夹内 | `poster.jpg`, `cover.jpg`, `folder.jpg`, `海报.jpg`, `封面.jpg` |
| 剧集根目录 | `poster.jpg`, `{剧集名}.jpg`, `剧集主图.png`, `封面.webp` |
| Season 文件夹内 | `poster.jpg` |
| 分集缩略图 | `{视频同名}.jpg`（自动用 ffmpeg 截图） |

## 豆瓣信息

通过 `local_metadata.json` 手动维护：

```json
{
  "items": {
    "Inside No. 9": {
      "summary": "简介内容",
      "douban": {
        "title": "9号秘事",
        "rating": "9.0",
        "url": "https://movie.douban.com/subject/xxxxxxx/"
      }
    }
  }
}
```

## 构建 EXE

### 方式一：一键构建

双击 `Build_EXE.bat` 或 `一键生成EXE.bat`，自动完成依赖安装 + 打包。

### 方式二：命令行

```bash
python build_desktop.py
```

### 构建说明

- 使用 PyInstaller `--onefile` 单文件模式
- 自动隐藏控制台窗口（`--noconsole`）
- 自动包含 `templates/`、`static/`、`MovieWall.ico` 等资源
- 自动处理 `pywebview` 的 hidden-import

### 输出

打包完成后所有文件位于 `release/dist/`：

```
release/dist/
├── MovieWall.exe    ← 单文件 exe（约 22 MB）
├── config.json      ← 配置文件（用户数据）
└── MovieWall.ico    ← 图标
```

运行时会在 exe 同目录自动生成 `library.db`、`metadata_cache.json`、`static/generated/thumbs/` 等用户数据。

## 常见问题

**Q: 扫描没有找到影片？**  
检查 `config.json` 中的 `categories` 和 `library_root` 配置是否正确，然后重启应用重新扫描。

**Q: 没有海报怎么办？**  
确认海报图片放在影片或剧集文件夹中，然后重新扫描。若配置了 TMDB API Key，会自动拉取远程海报。

**Q: ffmpeg 有什么用？**  
自动从视频中截取分集缩略图。不安装也能正常使用，只是没有自动缩略图。

**Q: 构建的 EXE 报"缺少 pywebview"？**  
使用打包好的 `release/dist/MovieWall.exe` 不应出现此问题。如出现，请确保已安装所有依赖并重新打包。

**Q: 用户数据存在哪里？**  
所有用户数据保存在 exe 同目录下：`config.json`（配置）、`library.db`（媒体库）、`metadata_cache.json`（元数据缓存）。

**Q: 关闭窗口后还有后台服务吗？**  
桌面版在窗口关闭时自动关闭本地服务，不会残留后台进程。
