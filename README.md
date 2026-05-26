# MovieWall Desktop

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

本地影视海报墙桌面应用，打造类似 Netflix / Jellyfin 的本地流媒体浏览体验。

MovieWall 会自动扫描本地影视目录，建立媒体数据库，并通过 TMDB + 豆瓣双数据源获取元数据，生成流媒体风格海报墙界面，支持调用 PotPlayer / VLC 等外部播放器进行播放。

---

# ✨ 功能特性

* 🎬 流媒体风格本地影视海报墙
* 📁 自动扫描电影 / 剧集 / 动漫
* 🌐 TMDB + 豆瓣双元数据源
* 🖼️ 自动海报匹配与缩略图生成
* 📺 Season / Episode 完整支持
* ⭐ 独立用户评分系统
* ❤️ 收藏与播放历史记录
* ▶️ PotPlayer / VLC 外部播放器联动
* 🧠 自动识别剧集命名格式
* 💾 SQLite 本地数据库
* ⚡ Flask + pywebview 轻量桌面架构
* 📦 PyInstaller 单文件 EXE 打包

---

# 🧠 项目定位

MovieWall 并不是一个视频在线播放器。

它更偏向于：

* 本地媒体管理系统
* 流媒体风格影视墙
* 轻量 HTPC 前端
* Jellyfin / Emby 风格桌面应用

项目专注于：

* 本地影视整理
* 海报墙展示
* 元数据管理
* 外部播放器联动

而不是视频解码本身。

视频播放由成熟播放器负责，例如：

* PotPlayer
* VLC

---

# 📸 应用展示

<div align="center">
  <img src="./screenshots/home.png" alt="首页海报墙" width="100%"/>
  <p><em>首页海报墙 - 浏览本地影视库</em></p>
</div>

<br/>

<div align="center">
  <img src="./screenshots/category.png" alt="分类界面" width="100%"/>
  <p><em>分类界面 - 按电影/剧集/动漫分类浏览</em></p>
</div>

<br/>

<div align="center">
  <img src="./screenshots/detail.png" alt="剧集详情页" width="100%"/>
  <p><em>剧集详情页</em></p>
</div>

---

# 🚀 快速开始

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

或双击：

```text
Install_Dependencies.bat
```

---

## 2. 配置应用

首次运行前，需要创建并编辑：

```text
config.json
```

执行：

```bash
copy config.example.json config.json
```

然后编辑配置：

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

# ⚙️ 配置项说明

| 配置项                 | 默认值    | 说明               |
| ------------------- | ------ | ---------------- |
| library_root        | —      | 影视媒体根目录          |
| categories          | 见上     | 分类定义             |
| players             | []     | 播放器列表            |
| tmdb_api_key        | —      | TMDB API Key     |
| tmdb_language       | zh-CN  | 元数据语言            |
| metadata_cache_days | 60     | 元数据缓存 TTL        |
| douban_enabled      | true   | 是否启用豆瓣           |
| generate_thumbnails | true   | 是否生成缩略图          |
| thumbnail_second    | 60     | 缩略图生成时间点         |
| ffmpeg_path         | ffmpeg | ffmpeg 路径        |
| history_limit       | 500    | 最大历史记录数          |
| potplayer_dpl_path  | —      | PotPlayer dpl 路径 |

---

# 🔑 TMDB API Key 获取

TMDB API Key 可免费申请：

<a href="https://www.themoviedb.org/settings/api" target="_blank">
  <img src="https://img.shields.io/badge/✨_Free_TMDB_API_Key-000?style=for-the-badge&logo=themoviedatabase&logoColor=01b4e4&labelColor=black" alt="TMDB API">
</a>

获取后填入：

```json
"tmdb_api_key": "your_tmdb_api_key_here"
```

---

# ▶️ 运行应用

## 桌面模式（推荐）
修改`config.json` 后直接运行：

```text
release/dist/MovieWall.exe
```

---

## 开发模式

```bash
python run.py
```

启动后打开浏览器：

```text
http://127.0.0.1:5000
```

---

# 📦 打包 EXE

使用 `Build_EXE.bat`, 输出目录：

```text
release/dist/
```

---

# 📂 影视目录规范

推荐目录结构：

```text
F:/Download/影视
├── Movies/
│   └── Zootopia 2 (2025)/
│       ├── Zootopia 2 (2025).mkv
│       └── poster.jpg
│
├── TV Shows/
│   └── 汉尼拔/
│       ├── poster.jpg
│       └── Season 01/
│           ├── Hannibal S01E01.mkv
│           └── poster.jpg
│
└── Anime/
    └── 葬送的芙莉莲 (2023)/
        └── Season 01/
            ├── Frieren - S01E29.mkv
            └── Frieren - S01E30.mkv
```

说明：

* `poster.jpg` 为本地海报（可选）
* 本地海报优先级高于 TMDB 海报
* 推荐使用规范化目录命名

---

# 🔍 媒体扫描规则

## 电影

* 每个子文件夹识别为一部电影
* 根目录下单独视频文件也会识别为电影

---

## 剧集 / 动漫

* 子文件夹识别为剧集
* `Season *` 子文件夹识别为季
* 自动建立 Season / Episode 结构

---

# 📺 剧集命名识别

支持以下格式：

```text
S01E01
E01
第1集
第 1 集
```

以及常见：

* 美剧
* 日剧
* 番剧
* 动漫

命名格式。

建议尽量使用规范命名方式，以提升识别准确率。

---

# 🎞️ 支持视频格式

支持常见视频格式：

* mp4
* mkv
* avi
* mov
* flv
* ts

实际支持能力取决于外部播放器。

---


# 🛠️ 常见问题

## PotPlayer 播放记录无法同步

请确认：

```json
"potplayer_dpl_path": ""
```

路径填写正确，并且 PotPlayer 已开启播放历史记录。

---

## 缩略图生成失败

请检查：

* 已正确安装 ffmpeg
* `ffmpeg_path` 配置正确
* 视频文件可正常播放

---

## TMDB 无法获取数据

请检查：

* `tmdb_api_key` 是否正确
* 网络是否可访问 TMDB
* API 请求额度是否超限

---

# ⚠️ 当前已知问题

## 豆瓣元数据匹配存在局限

由于豆瓣不存在稳定公开 API，目前项目使用非官方方式获取数据。

在部分情况下可能出现：

* 多季剧集匹配错误
* 同名影视识别错误
* 季简介复用错误
* 豆瓣评分更新失败
* 网络环境导致抓取失败

TMDB 通常用于：

* 海报
* 季结构
* 剧集信息

豆瓣通常用于：

* 中文简介
* 中文评分
* 演员信息

两者数据偶尔可能存在差异。

---

## 特殊命名格式可能影响识别

以下情况可能降低识别准确率：

* 文件名缺少集数
* 特别篇 / SP / OVA
* 多语言混合命名
* 无码番剧命名
* 缺少年份
* 同名影视作品

建议尽量使用规范命名格式。

---

## 首次扫描速度可能较慢

首次扫描会执行：

* 媒体识别
* TMDB 请求
* 豆瓣匹配
* 缩略图生成
* 本地缓存建立

大型媒体库属于正常现象。

---

# 🚧 Roadmap

未来计划：

* [ ] 更精准的剧集匹配算法
* [ ] 后端支持剧集多类型分类

---

# 📄 License

This project is licensed under the MIT License.
