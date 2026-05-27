# 媒体库自动目录发现系统报告

## 1. 当前 categories 架构问题

重构前，`scan_library()` 的核心扫描循环是：

```python
existing_cats = [(fn, cat) for fn, cat in categories.items() if (root / fn).exists()]
for idx, (folder_name, cat) in enumerate(existing_cats):
    folder = root / folder_name
    display = cat["name"]
    cat_items = _scan_category(folder, folder_name, display)
```

即扫描入口完全由 `config.json → categories` 驱动。

这意味着：只有 config 中显式声明的分类才允许被扫描。用户新增 `F:/Download/影视/KDrama` 目录后，即使该目录真实存在于磁盘上，系统也不会扫描它。

## 2. 为什么过度依赖 config

根本原因：系统将 config 的职责错误地扩大为：

1. **扫描入口** — 决定扫描哪些目录
2. **分类定义** — 定义 category 的存在性
3. **显示名映射** — 提供友好的中文分类名

而正确的架构应该是：

1. **扫描入口** → 由文件系统决定
2. **分类定义** → 由数据库决定
3. **显示名映射** → 由 `config.categories` 可选提供

## 3. 扫描入口修改说明

### 修改前（错误）

```python
categories = normalize_categories()
existing_cats = [(fn, cat) for fn, cat in categories.items() if (root / fn).exists()]
```

### 修改后（正确）

```python
display_map = normalize_categories()
dir_names = sorted([d.name for d in root.iterdir() if d.is_dir()],
                   key=lambda n: n.lower())
for idx, folder_name in enumerate(dir_names):
    folder = root / folder_name
    display = display_map.get(folder_name, {}).get("name", folder_name)
```

## 4. 自动目录发现实现

### 核心逻辑

```python
# 列出 library_root 下所有一级子目录
# 每个目录自动成为一个分类
# 无需 config 配置
dir_names = [d.name for d in root.iterdir() if d.is_dir()]
```

目录中所有的一级子目录都会被自动发现，包括：

```
F:/Download/影视/
├── Movies          → 自动发现 + 扫描
├── TV Shows        → 自动发现 + 扫描
├── Anime           → 自动发现 + 扫描
├── Reality Show    → 自动发现 + 扫描
├── Docuseries      → 自动发现 + 扫描
├── KDrama          → 自动发现 + 扫描（新增无需修改 config）
├── 国产剧          → 自动发现 + 扫描
├── Documentary     → 自动发现 + 扫描
└── ...             → 所有目录
```

## 5. category_name 映射机制

```
display_map = normalize_categories()  # 从 config 加载显示名映射
display = display_map.get(folder_name, {}).get("name", folder_name)
#                                            └────────────┘
#                                       无映射时使用目录名本身
```

| 目录名 | config 映射 | 显示名 |
|---|---|---|
| Movies | "电影" | 电影 |
| Reality Show | "综艺" | 综艺 |
| KDrama | 无 | KDrama |
| 国产剧 | 无 | 国产剧 |

## 6. 数据库修改说明

无需修改。`media` 表的 `category_key` 和 `category_name` 字段已是 TEXT 类型，支持任意字符串。

自动发现的新分类（如 `KDrama`）会直接写入数据库，无需预先注册。

`build_library_dict()` 中的 `stats.categories` 自动聚合所有存在的 category_key，无需 config 参与。

## 7. 前端数据源修改

前端分类数据的完整链路：

```
[磁盘目录] → scanner.py 自动发现
    ↓
[数据库 media 表] → category_key + category_name 自动保存
    ↓
[/api/library] → stats.categories 聚合返回
    ↓
[renderCategoryTabs()] → 动态渲染分类标签
```

前端不再依赖 `/api/config` 返回的 categories 来决定显示哪些分类标签。config 仅用于显示名映射，在 settings 页面中编辑。

## 8. 兼容性说明

- **旧 config.json**：已有的 `categories` 映射仍然有效，仅作为显示名映射
- **新增目录**：无需修改 config，自动发现
- **显示名缺失**：无映射时自动使用目录名作为显示名
- **旧数据库**：完全兼容，无需迁移
- **增量扫描**：未改变增量扫描逻辑（仍基于 root mtime）

## 9. 新增日志说明

| 日志前缀 | 触发时机 | 示例 |
|---|---|---|
| `[DISCOVER CATEGORY]` | 发现新目录 | `folder=KDrama display_name=KDrama` |
| `[DISPLAY NAME MAP]` | 显示名映射匹配 | `folder=Reality Show mapped_name=综艺` |
| `[SCAN] library_root=` | 扫描开始 | `discovered=6 directories: [...]` |

## 10. Git 提交信息

```
refactor: 实现媒体库自动目录发现系统

- scan_library 不再依赖 config.categories 决定扫描入口
- 改为 os.listdir(library_root) 自动发现所有一级子目录
- config.categories 仅做显示名映射（可选）
- 新目录无需修改 config 即可自动扫描
- 新增 [DISCOVER CATEGORY] / [DISPLAY NAME MAP] 日志
- 更新 reports/library_auto_discovery_report.md
```
