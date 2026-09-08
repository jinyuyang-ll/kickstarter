# Kickstarter 项目 URL 收集与元数据批量采集

> 2026-09-08 更新：控制台已改为分批计划，支持地区与自定义金额/比例范围。新版操作、停止状态及旧断点处理以 [分批采集指南](GUIDE_BATCH_COLLECTION.md) 为准；以下原始命令行与数据库说明保留供参考。

完整流程分为四个独立阶段：

```text
Kickstarter Discover / Search
  → url_collector.py（候选 URL CSV）
  → url_importer.py（检查、规范化、去重、导入 MySQL）
  → metadata_batch_spider.py（项目、创作者、协作者采集）
  → MySQL 数据表
```

`web_app.py` 提供本地可视化控制台，可以在浏览器中依次完成 URL 收集、Dry-run、正式导入、3/10/50 条批量采集、冒烟测试和代理预检。

## 1. 本次新增功能

### url_collector.py

- 低频访问 Kickstarter 公开 Discover JSON 结果；
- 支持直接粘贴浏览器当前 Discover/Search URL；
- 支持关键词、类别 ID、项目状态、排序和多个年份；
- 从 `launched_at` 计算真实上线年份；
- 输出包含来源、搜索条件、页码和采集时间的可审计 CSV；
- 重复执行自动按规范项目 URL 去重；
- 每页原子写入 CSV，并保存 `.checkpoint.json` 断点；
- 使用 `--resume` 从断点页继续；
- 遇到 403、429、安全验证或网络失败时停止并保留已有进度；
- Newest 排序向后翻页时，连续越过目标年份后可自动停止；
- 只建立候选 URL 文件，不直接写数据库。

### web_app.py 与 web/index.html

- 本地可视化操作界面，默认仅监听 `127.0.0.1`；
- 表单配置搜索地址、关键词、类别、年份、状态、页数和数量；
- 展示任务实时日志、状态和真实退出码；
- 一键执行 URL 收集、Dry-run、正式导入、批量采集、冒烟测试和代理预检；
- 限制只能选择项目目录内的 CSV/TXT/JSON；
- 后台任务只允许调用白名单内的交付脚本。

## 2. “最新”能否代替 launch_date

可以用于候选发现和增量采集，但不能把它理解为“严格历史全量”的保证。

Kickstarter 当前页面的排序参数是 `newest`。官方帮助仍将其解释为按 launch date 排序，但 2026 年新版 Discover 默认优先展示 Live、Late Pledges 和 Upcoming，完成项目需要额外筛选。正确做法是：

1. 用“最新/Newest”从新到旧收集候选项目；
2. 收集器读取每条结果的 `launched_at`；
3. 按真实 `launched_year` 保留目标年份；
4. 多年份时分批、断点向后翻页；
5. 如果要求失败项目或多年历史严格全量，仍需历史 URL 清单、旧数据库或明确授权的数据源，不能只靠公开 Discover 声称全量。

官方资料：

- Advanced Search：https://help.kickstarter.com/hc/en-us/articles/115005066253-How-does-Advanced-Search-work
- 2026 搜索与发现更新：https://start.kickstarter.com/kickstarter-release-notes/smarter-search-discovery

## 3. 首次安装

不要复制其他机器的 `.venv`，应在实际运行机器重新创建：

```powershell
cd C:\Users\Administrator\Desktop\kickstarter_fixed
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-metadata.txt
.\.venv\Scripts\python.exe -m pip check
Copy-Item config.example.json config.json
```

修改 `config.json` 中的 MySQL 配置。代理不可用时保持 `"enable_proxy": 0`。不要把真实 `config.json` 提交到公共仓库或公开压缩包。

## 4. 启动可视化界面

```powershell
.\.venv\Scripts\python.exe web_app.py
```

浏览器会打开 `http://127.0.0.1:8765`。不自动打开浏览器：

```powershell
.\.venv\Scripts\python.exe web_app.py --no-browser
```

界面具有启动本地任务的能力，不要暴露到公网；正常情况下保持默认 `127.0.0.1`。

### 界面操作顺序

1. 粘贴 Kickstarter 当前 Discover 搜索页地址；
2. 选择状态、排序和年份，第一轮最多收集 30～50 个；
3. 点击“开始低频收集”；
4. 日志显示 `success / exit code 0` 后执行“Dry-run 检查”；
5. 核对有效 URL 数量后点击“正式导入 MySQL”；
6. 依次点击“先跑 3 条”“再跑 10 条”“再跑 50 条”；
7. 出现连续 403/429、407 或大量失败时停止扩大批次。

## 5. 命令行收集 URL

### 最新 Live 项目

```powershell
.\.venv\Scripts\python.exe url_collector.py `
  --sort newest --state live `
  --max-pages 3 --max-projects 50 `
  --output candidate_urls.csv
```

### 使用浏览器搜索地址并筛选年份

```powershell
.\.venv\Scripts\python.exe url_collector.py `
  --discover-url "https://www.kickstarter.com/discover/advanced?category_id=12&sort=newest" `
  --year 2025 --max-pages 20 `
  --output games_2025.csv
```

### 多年份、多状态

```powershell
.\.venv\Scripts\python.exe url_collector.py `
  --category-id 12 --sort newest `
  --state successful --state failed `
  --year 2023 --year 2024 --year 2025 `
  --max-pages 100 --output games_2023_2025.csv
```

### 断点续跑

首次运行会生成 CSV 和同名 `.checkpoint.json`。继续时使用完全相同的搜索条件并增加 `--resume`：

```powershell
.\.venv\Scripts\python.exe url_collector.py `
  --category-id 12 --sort newest `
  --state successful --state failed `
  --year 2023 --year 2024 --year 2025 `
  --max-pages 100 --output games_2023_2025.csv --resume
```

条件不一致会返回 `checkpoint_query_mismatch`，防止把不同范围误写进同一批次。

## 6. CSV 字段

输出包含：`project_url`、`project_id`、`project_name`、`launched_at`、`launched_year`、`project_state`、`category`、`subcategory`、`country`、`source`、`source_query`、`source_page`、`collected_at`。

请保留原始 CSV，它是 URL 来源和搜索条件的审计记录。

## 7. 检查、导入和批量运行

```powershell
# 只检查，不写数据库
.\.venv\Scripts\python.exe url_importer.py candidate_urls.csv --dry-run

# 正式导入
.\.venv\Scripts\python.exe url_importer.py candidate_urls.csv

# 按 3 → 10 → 50 扩大
.\.venv\Scripts\python.exe metadata_batch_spider.py --limit 3
.\.venv\Scripts\python.exe metadata_batch_spider.py --limit 10
.\.venv\Scripts\python.exe metadata_batch_spider.py --limit 50

# 只保存指定筹款开始年份
.\.venv\Scripts\python.exe metadata_batch_spider.py --limit 50 --year 2025
```

`metadata_batch_spider.py --year` 仍只是复核已导入候选 URL。应优先在 `url_collector.py` 阶段按年份建立候选集，再由批量采集器复核。

## 8. MySQL

```powershell
$cfg = Get-Content -Raw config.json | ConvertFrom-Json
$env:MYSQL_ROOT_PASSWORD = $cfg.db_config.password
$env:MYSQL_DATABASE = $cfg.db_config.database
docker compose -f docker-compose.metadata.yml up -d --wait
.\.venv\Scripts\python.exe metadata_batch_spider.py --init-schema --limit 1
```

检查任务状态：

```sql
SELECT crawl_status, COUNT(*)
FROM metadata_crawl_tasks
GROUP BY crawl_status;
```

## 9. 代理与安全验证

URL 收集器读取 `config.json` 的代理开关。使用代理前必须取得有效 Host、端口、应用凭据或公网 IP 白名单，并确认支持 HTTPS CONNECT。

HTTP 407 是代理认证失败，请求通常尚未到达 Kickstarter。HTTP 403/429 或验证页表示目标站风控，应停止高频重试并保留断点。程序不会尝试破解交互式验证码。

## 10. 文件说明

- `url_collector.py`：候选 URL 收集器；
- `web_app.py`、`web/index.html`：本地可视化控制台；
- `test_url_collector.py`：URL 收集器单元测试；
- `url_importer.py`：检查、规范化、去重和导入；
- `project_metadata_spider.py`：单项目详情采集；
- `metadata_batch_spider.py`：MySQL 批量任务和失败恢复；
- `metadata_schema.sql`：数据库表；
- `smoke_test.py`：3 个真实项目冒烟测试；
- `proxy_probe.py`：代理检查；
- `requirements-metadata.txt`：Python 依赖。

## 11. 本次实际测试结果（2026-09-05）

### 自动测试

```text
py_compile：url_collector.py、web_app.py、test_url_collector.py 通过
unittest：3 tests，全部通过
```

覆盖 Discover URL 校验、查询参数、年份过滤、URL 去重、CSV/checkpoint 写入和断点续跑。

### Kickstarter 真实小样本

```text
查询：Discover / newest / live
范围：1 页，最多 5 个项目
页面返回：12 个项目
写入：5 个规范 URL
退出码：0
url_importer.py --dry-run：5 个有效且去重 URL
```

### 可视化前端

```text
GET /                       HTTP 200
GET /api/health             ok=true
POST /api/jobs/collect      success
真实收集数量                2
任务退出码                  0
CSV 文件                    已生成
```

当前执行环境没有可用的浏览器自动化实例，因此已完成 HTML、HTTP API 和真实后台任务链路测试，但没有生成浏览器截图。前端为响应式单页布局，可在实际 Windows 浏览器中打开验收。

## 12. 已知边界

- Discover 页面/API和参数可能变化，需要维护 `url_collector.py`；
- 公开搜索不能证明多年历史项目，尤其失败项目的严格全量覆盖；
- `newest` 是候选发现顺序，年份最终以 `launched_at` 为准；
- 大批量仍应单线程、低频、分批并监控 403/429；
- URL 收集和详情采集保持分离，便于审计、重跑和维护；
- 前端是本地运维工具，不含账号系统，不应部署到公网。
