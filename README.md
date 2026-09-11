# Kickstarter 数据采集工具

Python 编写的 Kickstarter 项目 URL 收集、项目元数据批量采集工具，附带本地 Web 控制台和 MySQL 存储支持。

新版控制台支持地区、金额和筹款比例筛选，以及多状态分批采集、独立续跑和统一去重。G13 反馈修复增加了跨任务请求间隔、HTTP 错误分类和年份跳过统计，可继续使用上一版分批断点。详见 [分批采集指南](GUIDE_BATCH_COLLECTION.md) 与 [内测记录](TEST_REPORT_COLLECTION.md)。

## 本地运行（Windows PowerShell）

```powershell
git clone https://github.com/jinyuyang-ll/kickstarter.git
cd kickstarter
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-metadata.txt
Copy-Item config.example.json config.json
```

编辑 `config.json`，填写自己的 MySQL 和可选代理配置；已有配置时请勿覆盖。

```powershell
.\.venv\Scripts\python.exe web_app.py
```

访问 `http://127.0.0.1:8765`。控制台可以启动本地采集任务，保持默认本机监听地址，不应直接开放到公网。GitHub 仓库用于存储代码；运行此 Python 后端需要本地电脑或单独配置的服务器。

## MySQL（可选 Docker）

先安装并启动 Docker，再执行：

```powershell
$cfg = Get-Content -Raw config.json | ConvertFrom-Json
$env:MYSQL_ROOT_PASSWORD = $cfg.db_config.password
$env:MYSQL_DATABASE = $cfg.db_config.database
docker compose -f docker-compose.metadata.yml up -d --wait
```

完整的数据库初始化、URL 导入、批量采集和排错步骤见 [使用说明](README_METADATA.md)。

## 文件说明

- `web_app.py`、`web/index.html`：本地控制台。
- `url_collector.py`、`url_importer.py`：收集和导入项目 URL。
- `project_metadata_spider.py`、`metadata_batch_spider.py`：项目元数据采集。
- `*_spider.py`、`download_video.py`：其他项目内容采集和视频下载脚本。
- `metadata_schema.sql`、`docker-compose.metadata.yml`：数据库结构和本地 MySQL 服务。
- `build_*_doc.py`：交付与排错文档生成脚本，生成文档另需安装 `python-docx`。

本地真实配置、虚拟环境、下载依赖、运行结果及生成的文档和压缩包由 `.gitignore` 排除。文档生成脚本保留在仓库中。

## 后续更新代码

在项目目录中执行，提交前检查文件列表，确认没有真实凭据：

```powershell
git status
git add .
git diff --cached --stat
git commit -m "Update project"
git push
```
