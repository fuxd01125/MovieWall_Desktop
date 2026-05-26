# MovieWall Desktop

MovieWall 是一个本地影视海报墙桌面应用。它扫描本地影视目录，生成类似流媒体平台的海报墙界面，支持通过 PotPlayer / VLC 等外部播放器播放视频。对接 TMDB + 豆瓣双数据源获取元数据，提供独立的用户评分系统。

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

或双击：

```bash
Install_Dependencies.bat
```

---

### 2. 配置应用

首次运行前，需要创建并编辑 `config.json`：

```bash
# 复制示例配置
copy config.example.json config.json
```

然后编辑 `config.json`：

```json
{
  "library_root": "F:\\Download\\影视",

  "categories": {
    "Movies": "电影",
    "TV Shows": "剧集",
    "Anime": "动漫"
  },

  "players": [
    {
      "name": "PotPlayer",
      "path": "C:\\Program Files\\PotPlayer\\PotPlayerMini64.exe"
    },
    {
      "name": "VLC",
      "path": "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe"
    }
  ],

  "generate_thumbnails": true,
  "thumbnail_second": 60,

  "metadata_enabled": true,
  "tmdb_api_key": "your_tmdb_api_key_here",
  "tmdb_language": "zh-CN",
  "metadata_cache_days": 60,

  "douban_enabled": true,
  "douban_id_overrides": {},

  "ffmpeg_path": "ffmpeg",

  "log_level": "INFO",
  "enable_file_log": true,

  "history_limit": 500,

  "potplayer_dpl_path": "C:\\Program Files\\PotPlayer\\Playlist\\PotPlayerMini64.dpl"
}
```

---

## ⚙️ 配置项说明

| 配置项                   | 默认值      | 说明                         |
| --------------------- | -------- | -------------------------- |
| `library_root`        | —        | 影视媒体根目录                    |
| `categories`          | 见上       | 分类定义（key=文件夹名，value=显示名称）  |
| `players`             | []       | 播放器列表，支持多个播放器              |
| `tmdb_api_key`        | —        | TMDB API v3 Key（必填）        |
| `tmdb_language`       | `zh-CN`  | TMDB 元数据语言                 |
| `metadata_cache_days` | `60`     | TMDB / 豆瓣缓存 TTL（天）         |
| `douban_enabled`      | `true`   | 是否启用豆瓣元数据                  |
| `generate_thumbnails` | `true`   | 是否自动生成视频缩略图                |
| `thumbnail_second`    | `60`     | 缩略图截图时间点（秒）                |
| `ffmpeg_path`         | `ffmpeg` | ffmpeg 可执行文件路径             |
| `history_limit`       | `500`    | 最大播放历史记录数                  |
| `potplayer_dpl_path`  | —        | PotPlayer 播放记录 `.dpl` 文件路径 |
| `log_level`           | `INFO`   | 日志等级                       |
| `enable_file_log`     | `true`   | 是否启用文件日志                   |

---

## 🔑 TMDB API Key 获取

TMDB API Key 可免费申请：

[TMDB API 设置页面](https://www.themoviedb.org/settings/api?utm_source=chatgpt.com)

获取后填入：

```json
"tmdb_api_key": "your_tmdb_api_key_here"
```

---

## ▶️ 运行应用

### 桌面模式（推荐）

直接运行：

```bash
release/dist/MovieWall.exe
```

---

### 开发模式

```bash
python main.py
```

启动后打开浏览器访问：

```text
http://127.0.0.1:5000
```

---

## 📂 影视目录规范

推荐目录结构：

```text
F:/Download/影视
├── Movies/                            # 电影目录
│   └── Zootopia 2 (2025)/
│       ├── Zootopia 2 (2025).mkv
│       └── poster.jpg                 # 本地海报（可选）
│
├── TV Shows/                          # 剧集目录
│   └── 汉尼拔/
│       ├── poster.jpg                 # 剧集海报（可选）
│       └── Season 01/
│           ├── Hannibal S01E01.mkv
│           └── poster.jpg             # 季海报（可选）
│
└── Anime/                             # 动漫目录
    └── 葬送的芙莉莲 (2023)/
        └── Season 01/
            ├── Frieren - S01E29.mkv
            └── Frieren - S01E30.mkv
```

---

## 🔍 媒体扫描规则

### 电影

* 每个子文件夹识别为一部电影
* 根目录下的单独视频文件也会识别为电影

### 剧集 / 动漫

* 子文件夹识别为剧集
* `Season *` 子文件夹识别为季

### 剧集命名识别

自动识别以下格式：

```text
S01E01
E01
第1集
第 1 集
```

以及常见番剧、日剧、美剧命名格式。

---


## 🛠️ 常见问题

### PotPlayer 播放记录无法同步

请确认：

```json
"potplayer_dpl_path": ""
```

路径填写正确，并且 PotPlayer 已开启播放历史记录功能。

---

### 缩略图生成失败

请检查：

* 已正确安装 ffmpeg
* `ffmpeg_path` 配置正确
* 视频文件可正常播放

---

### TMDB 无法获取数据

请检查：

* `tmdb_api_key` 是否正确
* 网络是否可访问 TMDB
* API 请求额度是否超限

