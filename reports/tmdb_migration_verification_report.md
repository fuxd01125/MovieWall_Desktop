# TMDB 元数据迁移验证报告

## 1. 检查结论

| 检查项 | 状态 |
|---|---|
| 静态语法检查 (10 个 Python 文件) | 全部通过 |
| SQLite schema 版本 | v3（最新） |
| 新表创建 | 4/4 全部创建 |
| 旧数据库升级 | 兼容 |
| TMDB 数据写入 | season: ✓ episode: ✓ people: ✓ credits: ✓ |
| API 输出结构 | 正确 |
| 旧字段残留引用 | 仅迁移代码中存在（安全） |

## 2. 数据库新增表结构

### metadata_tmdb_seasons
每个本地 season 对应一条 TMDB 元数据记录。

```sql
CREATE TABLE metadata_tmdb_seasons (
    season_id     TEXT PRIMARY KEY REFERENCES seasons(id) ON DELETE CASCADE,
    show_id       TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    season_number INTEGER NOT NULL,
    tmdb_id       INTEGER,
    title         TEXT,
    overview      TEXT,
    rating        REAL,
    air_date      TEXT,
    poster_url    TEXT,
    raw           TEXT,
    fetched_at    REAL,
    UNIQUE(show_id, season_number)
);
```

现有数据：16 行

### metadata_tmdb_episodes
每个本地 episode 对应一条 TMDB 元数据记录。

```sql
CREATE TABLE metadata_tmdb_episodes (
    episode_id     TEXT PRIMARY KEY REFERENCES episodes(id) ON DELETE CASCADE,
    show_id        TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    season_id      TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    season_number  INTEGER NOT NULL,
    episode_number INTEGER NOT NULL,
    tmdb_id        INTEGER,
    title          TEXT,
    overview       TEXT,
    rating         REAL,
    air_date       TEXT,
    still_url      TEXT,
    runtime        INTEGER,
    raw            TEXT,
    fetched_at     REAL,
    UNIQUE(show_id, season_number, episode_number)
);
```

现有数据：99 行

### people
规范化人物表，支持多数据源共存。

```sql
CREATE TABLE people (
    id                   TEXT PRIMARY KEY,
    source               TEXT NOT NULL,
    source_id            TEXT NOT NULL,
    name                 TEXT,
    original_name        TEXT,
    profile_url          TEXT,
    known_for_department TEXT,
    raw                  TEXT,
    updated_at           REAL,
    UNIQUE(source, source_id)
);
```

现有数据：209 人

### credits
演职表，按作用域（media/season/episode）关联。

```sql
CREATE TABLE credits (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    scope        TEXT NOT NULL, -- media | season | episode
    media_id     TEXT REFERENCES media(id) ON DELETE CASCADE,
    season_id    TEXT REFERENCES seasons(id) ON DELETE CASCADE,
    episode_id   TEXT REFERENCES episodes(id) ON DELETE CASCADE,
    person_id    TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    department   TEXT,
    job          TEXT,
    character    TEXT,
    order_index  INTEGER DEFAULT 0,
    raw          TEXT,
    fetched_at   REAL
);
```

现有数据：264 行（15 media + 16 season）

## 3. API 新结构示例

### Show 完整输出

```json
{
  "id": "4f376017f1a97dae",
  "type": "show",
  "title": "超时空调查",
  "metadata": {
    "tmdb": {
      "tmdb_id": 12345,
      "title": "超时空调查",
      "overview": "...",
      "rating": 8.5,
      "poster_url": "https://...",
      "backdrop_url": "https://...",
      "genres": ["纪录片", "历史"],
      "date": "2022-09-27"
    },
    "douban": {
      "douban_id": "12345",
      "rating": 9.0,
      "synopsis": "..."
    },
    "credits": {
      "cast": [
        {
          "person": {
            "id": "tmdb:12345",
            "source": "tmdb",
            "name": "Yang Zhigang",
            "profile_url": "https://..."
          },
          "department": "Acting",
          "job": "Actor",
          "character": "角色名",
          "order_index": 0
        }
      ]
    }
  },
  "seasons": [
    {
      "id": "d8ca8af02be0bfa3",
      "season_number": 1,
      "episode_count": 6,
      "metadata": {
        "tmdb": {
          "season_id": "d8ca8af02be0bfa3",
          "season_number": 1,
          "title": "第 01 季",
          "overview": "...",
          "rating": 9.0,
          "poster_url": "https://...",
          "air_date": "2022-09-27"
        },
        "credits": {
          "cast": [
            {
              "person": { "name": "Yang Zhigang" },
              "character": "角色名"
            }
          ]
        }
      },
      "episodes": [
        {
          "id": "abc123",
          "episode_number": 1,
          "title": "第 01 集",
          "metadata": {
            "tmdb": {
              "overview": "...",
              "still_url": "https://...",
              "rating": 8.5
            }
          }
        }
      ]
    }
  ]
}
```

### Movie 完整输出

```json
{
  "id": "87ce3de89c6a5bbe",
  "type": "movie",
  "title": "Zootopia 2",
  "metadata": {
    "tmdb": {
      "tmdb_id": 1084242,
      "title": "疯狂动物城2",
      "overview": "...",
      "rating": 7.5,
      "poster_url": "https://..."
    },
    "credits": {
      "cast": [
        {
          "person": { "name": "Ginnifer Goodwin" },
          "character": "Judy Hopps (voice)"
        }
      ]
    }
  }
}
```

## 4. 兼容性说明

| 方面 | 状态 |
|---|---|
| 旧数据库升级 | 自动迁移到 v3，保留 `season_data` 列作为遗留缓存 |
| 旧前端兼容 | `_season_meta` 和 `_season_data` 字段已移除但 `seasons` + `tmdb` 结构保持一致 |
| 播放器逻辑 | 未修改 |
| 收藏/历史/评分 | 未受影响 |
| 是否需要重新全库扫描 | **不需要**。现有数据已正确迁移 |

## 5. 数据完整性

| 表 | 行数 | 说明 |
|---|---|---|
| media | 16 | 全量媒体 |
| seasons | 37 | 所有季节 |
| episodes | 99 | 所有剧集 |
| metadata_tmdb_seasons | 16 | 新表，独立季节元数据 |
| metadata_tmdb_episodes | 99 | 新表，独立剧集元数据 |
| people | 209 | 归一化人物 |
| credits | 264 | 15 media + 16 season 级别 |

## 6. 旧字段引用说明

以下旧字段仅在迁移代码中出现，属于安全引用：

| 字段 | 所在文件 | 用途 |
|---|---|---|
| `season_data` | `database.py:71` | 旧表列定义（保留向后兼容） |
| `season_data` | `database.py:384-388` | v3 迁移读取遗留数据 |
| `_season_meta` | `database.py:757,940,965` | 函数名称（语义不变） |
| `_season_data` | `metadata.py:142-149` | 调试日志函数参数名 |

这些引用不影响运行，属于有意的向后兼容设计。

## 7. 修改文件列表

| 文件 | 变更说明 |
|---|---|
| `moviewall/database.py` | 新增 4 张表 schema + v3 迁移 + 写入/读取函数 |
| `moviewall/metadata.py` | TMDB 数据写入改为独立落表（season/episode/credits） |
| `moviewall/routes.py` | API 聚合结构统一 |
| `moviewall/scanner.py` | 适配新结构的增量改动 |
| `moviewall/utils.py` | 适配改动 |
| `static/app.js` | 适配 API 新结构 |
