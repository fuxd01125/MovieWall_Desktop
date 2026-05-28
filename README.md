# MovieWall Desktop

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

本地影视海报墙桌面应用，打造类似 Netflix / Jellyfin 的本地流媒体浏览体验。

MovieWall 会自动扫描本地影视目录，建立媒体数据库，并通过 TMDB 数据源获取元数据，生成流媒体风格海报墙界面，支持调用 PotPlayer / VLC 等外部播放器进行播放。

---

## 功能特性

- 流媒体风格本地影视海报墙
- 自动目录发现系统 — 无需配置即可自动扫描所有子目录
- 动态分类系统 — 基于目录结构自动推断分类，无需硬编码
- TMDB 元数据独立落表 — season / episode / people / credits 独立存储
- 演员系统 — 支持演员详情页、作品列表
- 智能剧集结构识别 — 自动检测 Season / Episode 结构
- 独立用户评分系统
- 收藏功能与收藏分类 Tab
- 播放历史记录
- PotPlayer / VLC 外部播放器联动
- SQLite 本地数据库
- Flask + pywebview 轻量桌面架构
- PyInstaller 单文件 EXE 打包

---

## 项目定位

MovieWall 并不是一个视频在线播放器。

它更偏向于：

- 本地媒体管理系统
- 流媒体风格影视墙
- 轻量 HTPC 前端
- Jellyfin / Emby 风格桌面应用

项目专注于本地影视整理、海报墙展示、元数据管理、外部播放器联动，而不是视频解码本身。

---

## 应用展示

<div align="center">
  <img src="./screenshots/home.png" alt="首页海报墙" width="100%"/>
  <p><em>首页海报墙 - 浏览本地影视库</em></p>
</div>

<br/>

<div align="center">
  <img src="./screenshots/category.png" alt="分类界面" width="100%"/>
  <p><em>分类界面 - 按目录分类浏览</em></p>
</div>

<br/>

<div align="center">
  <img src="./screenshots/detail.png" alt="剧集详情页" width="100%"/>
  <p><em>剧集详情页</em></p>
</div>

<div align="center">
  <img src="./screenshots/season_episode.png" alt="剧集详情页" width="100%"/>
  <p><em>剧集季集展开</em></p>
</div>

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

或双击 `Install_Dependencies.bat`。

### 2. 配置应用

首次运行前，创建并编辑 `config.json`：

```bash
copy config.example.json config.json
```

| 配置项 | 默认值 | 说明 |
|---|---|---|
| library_root | — | 影视媒体根目录 |
| categories | {} | 分类显示名映射（可选） |
| players | [] | 播放器列表 |
| tmdb_api_key | — | TMDB API Key |
| tmdb_language | zh-CN | 元数据语言 |
| metadata_cache_days | 60 | 元数据缓存 TTL |
| generate_thumbnails | true | 是否生成缩略图 |
| thumbnail_second | 60 | 缩略图生成时间点 |
| ffmpeg_path | ffmpeg | ffmpeg 路径 |
| history_limit | 500 | 最大历史记录数 |
| potplayer_dpl_path | — | PotPlayer dpl 路径 |

> **注意**：`categories` 现在仅做显示名映射，新目录无需修改配置即可自动扫描和显示。

### 3. 运行应用

**桌面模式（推荐）**：运行 `release/dist/MovieWall.exe`

**开发模式**：

```bash
python run.py
```

启动后打开浏览器访问 `http://127.0.0.1:5000`

---

## 影视目录规范

推荐目录结构：

```text
F:/Download/影视
├── Movies/
│   └── Zootopia 2 (2025)/
│       └── Zootopia 2 (2025).mkv
│
├── TV Shows/
│   └── 汉尼拔/
│       └── Season 01/
│           └── Hannibal S01E01.mkv
│
└── 纪录片/
    └── ...（无需配置，自动发现）
```

> 新目录放入 `library_root` 后会自动发现并显示

---

## 媒体扫描逻辑

- **电影**：每个子文件夹识别为一部电影；根目录下单独视频文件也会识别
- **剧集**：子文件夹识别为剧集，`Season *` 子文件夹识别为季，自动建立 Season / Episode 结构
- **自动推断**：基于文件结构自动区分 movie / show，无需手动指定 media_type

---

## 剧集命名识别

支持格式：`S01E01`、`E01`、`第1集`、`第 1 集`、中文数字（十一~九十九）

---

## 已知问题

- 豆瓣元数据匹配存在局限（非官方 API，可能匹配错误）
- 特殊命名格式（SP / OVA / 多语言混合）可能降低识别准确率
- 首次扫描较慢（媒体识别 + TMDB 请求 + 缩略图生成 + 缓存建立）

---

## License

This project is licensed under the MIT License.
