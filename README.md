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



你可以在 README 里新增一个 `## ⚠️ 当前已知问题` 模块，放在“常见问题”前面会比较合适。
建议整理成这种偏工程化的说明：

------

## ⚠️ 当前已知问题

### 豆瓣元数据抓取存在不稳定情况

由于豆瓣缺少公开稳定 API，目前项目使用非官方方式获取数据，因此可能出现以下问题：

- 部分影视无法正确匹配豆瓣条目
- 多季剧集可能错误匹配为电影
- 剧集第二季、第三季等，可能错误复用第一季剧情简介
- 部分番剧 / 日剧 / 同名作品可能识别错误
- 豆瓣评分与简介偶尔无法更新
- 网络环境变化可能导致抓取失败

------

### TMDB 与豆瓣数据可能不一致

由于数据来源不同：

- TMDB 季信息通常更准确
- 豆瓣中文简介更完整
- 两者在年份、标题、季编号上可能存在差异

因此部分作品可能出现：

- 海报正确但简介错误
- 剧集匹配正确但评分错误
- 季信息缺失

------

### 剧集命名依赖规范化

虽然系统支持：

```text
S01E01
E01
第1集
第 1 集
```

但对于以下情况，识别准确率会下降：

- 文件名缺少集数
- 多语言混合命名
- 无码番剧命名
- 特别篇 / SP / OVA
- 年份缺失
- 同名影视作品

建议尽量使用规范命名格式。

------

### PotPlayer 播放记录同步存在局限

当前播放记录依赖：

```text
PotPlayerMini64.dpl
```

因此：

- 必须开启 PotPlayer 历史记录
- 异常退出播放器可能导致记录未及时刷新
- 部分情况下需重新播放或关闭播放器后才会同步

------

### 首次扫描速度可能较慢

首次扫描时会执行：

- 媒体识别
- TMDB 请求
- 豆瓣匹配
- 缩略图生成
- 本地缓存建立

媒体库较大时属于正常现象。
