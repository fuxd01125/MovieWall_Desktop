# Season 识别与数据库同步修复报告

## 1. 高季数无法识别根因

### 问题 A：中文复合数字解析失败

`parse_season_number()` 中的中文数字解析：

```python
_CN_NUM_SEASON = {"一":1,"二":2,...,"十":10}
m = re.search(r"第\s*([一二三四五六七八九十]+)\s*季", s)
return _CN_NUM_SEASON.get(m.group(1), 1)
```

当文件夹名为 `第二十六季` 时，正则捕获到 `二十六`，但 `_CN_NUM_SEASON.get("二十六", 1)` 返回默认值 `1`，因为字典中没有 `二十六` 这个键。

### 问题 B：短格式 S 正则限制

```python
m = re.search(r"[Ss](\d{1,2})", s)
```

`{1,2}` 限制了只能匹配 1-2 位数字。虽然 `S26`（2位）能匹配，但 `S126`（3位）会失败。更严重的是 `_detect_season_folders` 中缺少对 `S\d+` 模式的检测。

## 2. Season 正则修复

### `parse_season_number`（utils.py）

| 修复项 | 修改前 | 修改后 |
|---|---|---|
| 中文数字解析 | `_CN_NUM_SEASON` 字典查找（仅支持单字） | `_chinese_num_to_int()` 支持复合数字（十一、二十、二十六、九十九） |
| `S\d+` 位数限制 | `[Ss](\d{1,2})` 仅 1-2 位 | `[Ss](\d+)` 任意位数 |
| 中文季字符集 | `[一二三四五六七八九十]` | `[一二三四五六七八九十百零]` |

### `_chinese_num_to_int()` 算法

```python
# 单字: 一(1) ~ 十(10)
# 十一 = 10 + 1 = 11
# 二十 = 2 * 10 = 20
# 二十六 = 2 * 10 + 6 = 26
# 九十九 = 9 * 10 + 9 = 99
```

支持范围：1 ~ 99。

## 3. 中文季识别增强

| 格式 | 示例 | 是否支持 |
|---|---|---|
| 第 N 季 | 第1季、第19季、第26季 | 是 |
| 第 N 季（中文数字） | 第一季、第十季、第二十六季 | 是 |
| S 短格式 | S01、S19、S26 | 是 |
| Season 格式 | Season 1、Season 19、Season 26 | 是 |
| 混合格式 | 空中浩劫 S26、剧名 第1季 | 是 |

## 4. 数据库脏数据根因

`_scan_single_show()` 使用 `upsert_season_batch()` 和 `upsert_episode_batch()` 进行数据写入:

```python
# upsert_season_batch 使用 ON CONFLICT(id) DO UPDATE
INSERT INTO seasons (...) VALUES (...)
ON CONFLICT(id) DO UPDATE SET ...
```

当用户将 `Season 1` 重命名为 `Season 5`：
1. `season_id = stable_id("season", new_folder.resolve(), 5)` → 生成**新 ID**
2. `ON CONFLICT(id) DO UPDATE` → 新 ID 无冲突 → **插入新行**
3. 旧 `Season 1` 的 ID 在 DB 中仍然存在 → **脏数据残留**

## 5. 为什么旧 Season 未删除

`_scan_single_show()` 的设计是"仅 upsert"，没有"先清理后写入"的步骤。它假设数据库中的剧集数据始终与磁盘一致，但这个假设在以下场景中都会失败：

- 用户重命名 Season 文件夹
- 用户删除 Season 文件夹
- 用户修改 Season 编号

## 6. 新同步机制设计

### `_rebuild_show_episodes()` — 全量重建

```
扫描 show "空中浩劫" 时:

1. 从磁盘检测到 Season 列表: [5, 6, 7]
2. 从数据库读取旧 Season 列表: [1, 5, 6, 7]
3. 比对: Season 1 不存在于磁盘
   → [REMOVE ORPHAN SEASON] show=空中浩劫 season=1
4. 删除数据库中该 show 的所有 seasons + episodes
5. 从磁盘数据重建所有 seasons + episodes
6. 结果: 数据库只有 [5, 6, 7] → 与磁盘一致
```

### 执行流程

```python
_scan_single_show(show_folder):
    1. 检测磁盘 Season 目录
    2. 构建 seasons 和 episodes 列表
    3. upsert_media_batch([show_item])  # 更新 show 元数据
    4. _rebuild_show_episodes(show_id, show_title, all_seasons, all_episodes)
       # ↑ 全量重建: 删除旧数据 → 写入新数据
```

## 7. Orphan 清理机制

`_rebuild_show_episodes()` 自动执行：

```sql
DELETE FROM episodes WHERE show_id = ?       -- 清除所有旧剧集
DELETE FROM seasons WHERE show_id = ?         -- 清除所有旧季
DELETE FROM metadata_douban_seasons WHERE show_id = ?  -- 清除豆瓣季元数据
INSERT INTO seasons (...) VALUES (...)        -- 写入新季
INSERT INTO episodes (...) VALUES (...)       -- 写入新剧集
```

新增 `[REMOVE ORPHAN SEASON]` 日志：

```
[REMOVE ORPHAN SEASON] show=Air Crash Investigation season=1 title=第 01 季 reason=folder_no_longer_exists
```

## 8. Season 重建机制

新机制与 `delete_all_media` 配合良好：

- `delete_all_media()` 在 full scan 时删除所有媒体数据
- `_rebuild_show_episodes()` 在单个 show 扫描时重建 season/episode
- 两者共同保证数据库始终与磁盘一致

## 9. 数据库约束修改

无需修改。现有约束已足够：

| 表 | 约束 | 作用 |
|---|---|---|
| `seasons` | `UNIQUE(show_id, season_number)` | 防止同一 show 内季节编号重复 |
| `episodes` | `UNIQUE(show_id, season_id, episode_number)` | 防止同一季内集数重复 |
| `seasons.show_id` | `REFERENCES media(id) ON DELETE CASCADE` | 删除 show 时自动删除 seasons |
| `episodes.show_id` | `REFERENCES media(id) ON DELETE CASCADE` | 删除 show 时自动删除 episodes |
| `episodes.season_id` | `REFERENCES seasons(id) ON DELETE CASCADE` | 删除 season 时自动删除 episodes |

## 10. Git 提交信息

```
fix: 修复高季数识别与数据库同步机制

- 新增 _chinese_num_to_int() 支持复合中文数字解析（十一~九十九）
- parse_season_number 移除 S 正则位数限制 [Ss](\d{1,2}) → [Ss](\d+)
- _detect_season_folders 增加 S\d+ 模式检测和 [SEASON DETECT] 日志
- 新增 _rebuild_show_episodes 全量重建：删除旧 season/episode 再写入
- 新增 [REMOVE ORPHAN SEASON] 日志跟踪脏数据清理
- 更新 reports/season_sync_fix_report.md
```
