# 动态分类系统修复报告

## 1. 根因分析

上一轮重构虽然完成了动态分类的基本框架，但存在三个核心残留问题：

### 问题 A：frontend 中 category 与 media_type 混用
`renderCategoryTabs()` 在生成动态分类标签的同时，仍然硬编码了 `{key:"movie", label:"电影"}` 和 `{key:"show", label:"剧集"}` 两个 media_type 标签。当用户的 category 中恰好有名为"电影"的分类（如 Movies → 电影）时，就会出现两个"电影"标签。

### 问题 B：_detect_show_folder 对单文件剧集支持不足
当剧集文件夹只有 1 个视频文件（如仅有 S01E01）时，检测逻辑返回 `False`，因为 `len(videos) > 1` 条件不满足，且没有独立处理单文件含剧集编号的情况。

### 问题 C：getFilteredItems/getContinueItems 残留 media_type 过滤
即使用户点击的是动态分类标签，过滤逻辑中仍然保留了对 `movie` 和 `show` 类型的检查，导致分类过滤与类型过滤产生冲突。

---

## 2. Reality Show 识别失败原因

假设目录结构为：

```
Reality Show/
└── Running Man/
    ├── S01E01.mkv
    └── S01E02.mkv
```

原 `_detect_show_folder()` 执行流程：

1. **检查季目录**：Running Man 下没有 Season/第X季 子目录 → 跳过
2. **检查文件模式**：找到 2 个视频文件，`parse_episode_number` 对两者都返回 >0（S01E01 → 1, S01E02 → 2）
3. **判断**：`ep_count=2 >= len(videos)*0.5=1` → `True` → 应正确识别为 show

但原逻辑中 `len(videos) <= 1` 时直接返回 `False`，导致**单集剧集**检测失败。

根本原因是：检测函数只考虑了"多数文件有剧集编号"的情况，没有处理"单个文件但有剧集编号"的边界情况。

---

## 3. 双电影标签原因

`renderCategoryTabs()` 的 tab 数组构造：

```javascript
// 修复前
const tabs = [
  {key:"all", label:"全部"},
  {key:"movie", label:"电影"},         // ← media_type 标签
  {key:"show", label:"剧集"},          // ← media_type 标签
  ...catStats.map(c => ({key:"cat:" + c.key, label: c.name}))
  // 如果 catStats 包含 {key:"Movies", name:"电影"} → 又一个"电影"
];
```

导致页面上出现 `全部 | 电影 | 剧集 | 电影 | TV Shows | Anime` 的标签顺序。

**修复方案**：删除 `{key:"movie"}` 和 `{key:"show"}`，只保留 `全部` + 动态分类。media_type 不再参与前端 Tab 导航。

---

## 4. 扫描器修复说明

### 改进的 `_detect_show_folder(folder, cat_name)`：

```python
# 检测信号
# Signal 1: 季节目录 (Season X, 第X季)
# Signal 2: 文件剧集编号 (S01E01, E01, 第X集)
# Signal 3: 多文件启发式 (>=3个视频文件 → show)
#
# 关键修复: 单文件含剧集编号 → show
# 关键修复: 3+个视频文件无编号 → show (多文件启发式)
```

### 新增 [SCAN] 调试日志：

每条检测都会输出详细日志，例如：

```
[SCAN] category=Reality Show folder=Running Man detected_type=show reason=2/2 files have episode patterns
[SCAN] category=综艺 folder=奔跑吧兄弟 detected_type=show reason=Season dir: Season 1
[SCAN] category=Movies folder=盗梦空间 detected_type=movie reason=ep_count=0/1 no season dirs
[SCAN] category=Reality Show scanned=3 items (movies=0 shows=3)
```

---

## 5. 前端修复说明

### renderCategoryTabs() — 删除 media_type 标签

```javascript
// 修复后
const tabs = [
  {key:"all", label:"全部"},
  ...catStats.map(c => ({key:"cat:" + c.key, label: c.name}))
];
// 输出示例: 全部 | Movies | TV Shows | Anime | Reality Show
```

### getFilteredItems() — 仅分类过滤

删除 `activeTab === "movie"` 和 `activeTab === "show"` 分支，不再支持 media_type 过滤。只保留 `activeTab.startsWith("cat:")` 的分类过滤。

### renderHome() — 仅动态分类区块

- **"全部"页面**：仅显示 继续观看 + 动态分类行 + 最近添加，不再有"电影"和"剧集"固定区块
- **分类页面**：显示该分类下所有内容的网格

---

## 6. 删除的旧逻辑

| 文件 | 删除内容 |
|---|---|
| `scanner.py` | `_detect_show_folder` 的单文件 fallback `False` 逻辑 |
| `app.js` | `renderCategoryTabs()` 中的 `{key:"movie"}` 和 `{key:"show"}` tab |
| `app.js` | `getFilteredItems()` 中的 `activeTab === "movie"` 分支 |
| `app.js` | `getFilteredItems()` 中的 `activeTab === "show"` 分支 |
| `app.js` | `getContinueItems()` 中的 `activeTab === "movie"` 分支 |
| `app.js` | `getContinueItems()` 中的 `activeTab === "show"` 分支 |
| `app.js` | `renderHome()` 中的 `movies`/`shows` 固定区块和 `gridMovies`/`gridShows` 条件渲染 |
| `config.py` | 无——已在上轮清理 |

---

## 7. category/media_type 解耦说明

| 概念 | 数据库字段 | 前端显示 | 来源 |
|---|---|---|---|
| **category** | `category_key`, `category_name` | 标签 Tab、分类区块 | `config.json` 配置 |
| **media_type** | `media_type` (→ API 中为 `type`) | 卡片标签（电影/剧集）、详情页结构 | 扫描器自动推断 |

**交互规则**：
- category 仅用于用户分类和前端导航
- media_type 仅用于确定显示格式（单视频 or 季/集结构）和 TMDB 搜索类型
- 二者在 API 返回中同时存在，但前端完全独立使用
- "Movies" 分类下可以同时有 `movie` 和 `show` 类型的条目
- "Anime" 分类下的单视频文件会被正确归类为 `movie` 类型

---

## 8. 调试日志新增内容

```python
log.info("[SCAN] category=%s folder=%s detected_type=%s reason=%s", ...)
```

输出位置：
- `_detect_show_folder()` 每次检测决策
- `scan_library()` 每个分类开始/结束

日志查看方式：
- 控制台
- `moviewall.log` 文件

---

## 9. 剩余风险

1. **混合内容的分类**：如果一个分类目录下同时有剧集文件夹（含 S01E01）和独立电影文件夹，扫描器能正确识别，但前端"全部"页面会将该分类的所有条目混在一起显示。这是功能需求还是问题由用户决定。
2. **单集剧集命名**：单集剧集（如只含 1 个文件的特别篇）必须文件名中包含 `S01E01` 或 `E01` 等剧集编号模式才能被正确识别为`show`。
3. **category_key 中的空格**：分类名如 "Reality Show" 包含空格，在 HTML attribute 中已通过 escapeJs 处理。但应避免在 category_key 中使用特殊字符。

---

## 10. Git 提交信息

```
fix: 彻底修复动态分类系统与媒体类型混用问题

- 修复 _detect_show_folder 单文件剧集检测失败
- 删除前端所有 media_type 硬编码标签（movie/show/anime）
- renderCategoryTabs/getFilteredItems/renderHome 全面清理
- 新增 [SCAN] 调试日志跟踪自动检测决策
- category 与 media_type 完全解耦
- 新增 reports/dynamic_category_fix_report.md
```
