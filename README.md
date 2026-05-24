# MovieWall Desktop V15 使用说明

MovieWall 是一个本地影视海报墙桌面应用。

它会读取你的本地影视目录，生成类似流媒体平台的海报墙界面，并通过 PotPlayer 播放本地视频。

## V15 更新内容





### V15 小修：评分不再混入媒体信息行

卡片信息行现在只显示：

```text
年份
季数
集数
TMDB / 豆瓣公开评分
```

不再把“我的评分”放进这一行。

“我的评分”只在详情页独立显示：

```text
我的评分 9.0    修改评分
```

这样不会再出现类似：

```text
我的 9.0
2019
1 季
3 集
```

这种混乱排版。

### V14 小修：我的评分显示统一

评分显示已统一为：

```text
我的评分 9.0
```

包括：

- 首页卡片
- 剧集卡片
- 每一季卡片
- 详情页评分按钮

评分后只显示 `我的评分 9.0` 和 `修改评分`，点击后才重新展开 1–10 分按钮。

### 1. 添加应用图标

已加入你提供的图标文件：

```text
MovieWall.ico
```

打包 EXE 时会自动使用这个图标：

```text
dist/MovieWall/MovieWall.exe
```

### 2. 完善“我的评分”系统

现在支持评分的对象包括：

```text
电影
剧集
每一季
```

评分交互已优化：

- 第一次进入详情页时显示 1–10 分评分按钮
- 第一次评分后，评分按钮会自动收起
- 收起后只显示 `我的评分 x.x / 10`
- 旁边保留 `修改评分` 按钮
- 点击 `修改评分` 后才重新展开 1–10 分按钮
- 每一季剧集也可以单独评分
- 季海报卡片会显示该季的 `我的 x.x`

评分数据保存在本机 WebView 的本地存储里，不会上传网络。

### 3. 修复 ffmpeg 弹窗

扫描生成缩略图时，ffmpeg 会在后台运行，不再反复弹出 `ffmpeg.exe` 窗口。

### 4. 中文 README

本说明已改为中文。

---

## 你的默认路径

当前配置文件 `config.json` 已保留你的路径：

```json
{
  "library_root": "F:/Download/影视",
  "potplayer_path": "D:/software/PotPlayer/PotPlayerMini64.exe"
}
```

如果你的路径发生变化，请打开 `config.json` 修改。

---

## 目录结构建议

推荐你的影视目录保持这样：

```text
F:/Download/影视
├─ Movies/
│  └─ Zootopia 2 (2025)/
│     └─ Zootopia 2 (2025).mkv
│
├─ TV Shows/
│  └─ Inside No. 9 (2014)/
│     └─ Season 06/
│        ├─ Inside No. 9 - S06E01.mkv
│        └─ Inside No. 9 - S06E02.mkv
│
└─ Anime/
   └─ 葬送的芙莉莲 (2023)/
      └─ Season 01/
         ├─ Frieren - S01E29.mkv
         └─ Frieren - S01E30.mkv
```

---

## 海报和缩略图放法

### 电影海报

放在电影文件夹里：

```text
F:/Download/影视/Movies/Zootopia 2 (2025)/poster.jpg
```

也支持：

```text
cover.jpg
folder.jpg
海报.jpg
封面.jpg
任意图片名.jpg
```

### 剧集海报

放在剧集根目录：

```text
F:/Download/影视/TV Shows/Inside No. 9 (2014)/poster.jpg
```

也支持：

```text
Inside No. 9 (2014).jpg
剧集主图.png
封面.webp
```

### 季海报

放在 Season 文件夹里：

```text
F:/Download/影视/TV Shows/Inside No. 9 (2014)/Season 06/poster.jpg
```

### 分集缩略图

分集不使用竖版海报，只使用 16:9 缩略图。

推荐和视频同名：

```text
Inside No. 9 - S06E01.mkv
Inside No. 9 - S06E01.jpg
```

如果没有分集缩略图，且安装了 ffmpeg，MovieWall 会自动从视频里截图。

---

## 生成桌面 EXE

解压 V12 后，双击：

```text
Build_EXE.bat
```

或者：

```text
一键生成EXE.bat
```

打包成功后，打开：

```text
dist/MovieWall/MovieWall.exe
```

注意：不要只移动 `MovieWall.exe`，请保留整个：

```text
dist/MovieWall/
```

因为里面还包含模板、静态资源、配置文件和缓存文件。

---

## 运行方式

以后直接双击：

```text
dist/MovieWall/MovieWall.exe
```

打开后就是 MovieWall 桌面窗口。

关闭这个窗口，MovieWall 的本地服务也会一起关闭。

---

## 如果你之前运行过旧版

可以先双击：

```text
Clean_Old_Background.bat
```

它会清理旧版本可能残留的后台进程。

---

## 如果打包失败

V12 会生成错误日志：

```text
build_error.log
```

把这个文件里的内容发给我，我可以继续帮你修。

---

## 如果想不打包直接测试

先双击：

```text
Install_Dependencies.bat
```

再双击：

```text
Run_Desktop_Debug.bat
```

这样可以不生成 EXE，直接测试桌面窗口。

---

## TMDB 信息

如果你想显示 TMDB 简介、评分、类型和远程海报，需要在 `config.json` 里填写：

```json
"tmdb_api_key": "你的 TMDB API Key"
```

不填写也可以正常使用本地海报墙。

---

## 豆瓣信息

豆瓣信息通过 `local_metadata.json` 手动维护，例如：

```json
{
  "items": {
    "Inside No. 9": {
      "summary": "这里可以写简介。",
      "douban": {
        "title": "9号秘事",
        "rating": "9.0",
        "url": "https://movie.douban.com/subject/xxxxxxx/"
      }
    }
  }
}
```

---

## 常见问题

### 1. 扫描时没有海报怎么办？

先确认海报图片放在影片或剧集文件夹里，然后重新点击扫描。

### 2. ffmpeg 有什么用？

ffmpeg 用来自动从视频里截取分集缩略图。

### 3. 为什么我的评分没有同步？

“我的评分”目前是本机本地评分，只保存在当前电脑当前 WebView 环境里。

### 4. 关闭窗口后还会不会有后台服务？

V12 桌面版会在窗口关闭时关闭本地服务。正常情况下不会残留后台服务。
