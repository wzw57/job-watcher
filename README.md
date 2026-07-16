# Job Watcher

青岛国企/央企 2027 秋招信息汇总与求职助手。

当前阶段：V1 数据底座重构与多来源采集管线开发。

V1 在保留旧数据的基础上新增：企业层级、渠道健康度、原始证据、招聘事件、
具体岗位、个人投递和人工核验等核心模型。`db-init` 可重复执行，并会为旧数据库
补充兼容字段，不会清空已有企业、来源或招聘线索。

主要文档：

- `docs/requirements.md`：需求规格说明
- `docs/architecture.md`：系统架构设计
- `docs/roadmap.md`：开发路线图
- `docs/data_verification.md`：企业数据核实与修正规则
- `docs/information_sources.md`：信息来源清单与接入策略
- `docs/development.md`：主开发说明
- `docs/vps_deployment.md`：VPS 部署记录和运维命令
- `docs/search_monitoring.md`：主动搜索监控核心设计
- `docs/collector_validation.md`：真实页面采集与失败分类验证记录

## 本地配置检查

```powershell
$env:JOB_WATCHER_SETTINGS="config/settings.yaml"
python -m job_watcher.cli config-check
```

## 初始化数据库并导入种子数据

```powershell
$env:PYTHONPATH="E:\job_watcher\src"
python -m job_watcher.cli db-init
python -m job_watcher.cli seed-data-doctor
python -m job_watcher.cli import-seed
python -m job_watcher.cli migrate-legacy-leads
```

当前导入结果：

- 企业：500 条
- 来源：705 条
  - 表格拆分来源：690 条
  - 固定公共源：15 条
- P0/P1 企业：215 条

`seed-data-doctor` 会校验必需字段、重复 `company_key`、跨文件关联、manifest 数量和 SHA-256。
`import-seed` 可重复执行；`migrate-legacy-leads` 非破坏性保留旧表，并建立
`sources -> raw_items -> job_events -> job_positions` 可追溯链路。

## 启动本地 Web 看板

当前本地看板使用 Python 标准库实现，避免早期开发阶段被未安装的 Web 依赖阻塞。默认只绑定本机地址。

```powershell
$env:PYTHONPATH="E:\job_watcher\src"
python -m job_watcher.cli import-candidates
python -m job_watcher.cli web --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000/companies
http://127.0.0.1:8000/coverage
http://127.0.0.1:8000/sources
http://127.0.0.1:8000/candidates
http://127.0.0.1:8000/leads
http://127.0.0.1:8000/search-results
http://127.0.0.1:8000/discovered-companies
```

命令行查看覆盖率：

```powershell
$env:PYTHONPATH="E:\job_watcher\src"
python -m job_watcher.cli coverage
```

保守自动确认低风险来源：

```powershell
$env:PYTHONPATH="E:\job_watcher\src"
python -m job_watcher.cli auto-confirm-sources
```

当前自动确认结果：

- 自动确认来源：100 条
  - 政府来源：53 条
  - 公共平台/高校平台来源：19 条
  - 明确招聘入口：28 条
- P0/P1 企业可信来源覆盖：31 / 215
- P0/P1 企业明确招聘入口覆盖：14 / 215

自动确认只处理 `government`、`public_platform`、`campus`、`official_recruitment`。原始表格中类型为 `official_or_unknown` 的链接仍需人工复核，不会自动升级为可信来源。

## 运行一轮轻量抓取

```powershell
$env:PYTHONPATH="E:\job_watcher\src"
python -m job_watcher.cli db-init
python -m job_watcher.cli crawl-once --limit 20
```

每次采集都会写入 `source_runs`，并将最新原始证据写入 `raw_items`，同时保留旧版
`crawl_snapshots` 兼容链路。运行状态会区分成功、成功但内容未变化、HTTP 错误、
网络错误、访问阻断、需要浏览器和正文解析失败；无法自动处理的异常会进入
`review_tasks`，不会显示为“成功无新增”。

HTML 公告会自动发现 PDF、DOC/DOCX、XLS/XLSX 和 CSV 附件。PDF、DOCX、XLSX、CSV
可提取文本并作为独立 `raw_items` 证据保存；旧版 DOC/XLS 或解析失败的附件进入人工核验，
主页面仍记录为成功但本次运行标记为 `partial_success`。

采集器默认限制单响应 25 MiB、单页 10 个附件，并对临时网络错误和 429/5xx 做有限重试。
附件原文件按内容哈希保存在快照目录。动态页面可通过 `job-watcher[browser]` 安装
Playwright 后启用 `browser_fallback_enabled`；未安装浏览器时会留下明确核验状态。

单 URL 诊断不会写数据库：

```bash
PYTHONPATH=src python -m job_watcher.cli collect-url https://example.com/recruit
PYTHONPATH=src python -m job_watcher.cli collect-url https://example.com/recruit --browser
```

固定采集验收池位于 `config/collector_samples.csv`，当前包含 22 个政府、高校、招聘平台、
企业官网和文档样本。批量验收同样只读，不写数据库；默认输出完整 JSON，`--strict` 会在
实际状态超出样本允许范围时返回非零退出码：

```bash
PYTHONPATH=src python -m job_watcher.cli validate-collector-samples --timeout 5
PYTHONPATH=src python -m job_watcher.cli validate-collector-samples --category document --strict
PYTHONPATH=src python -m job_watcher.cli validate-collector-samples --output data/collector-validation.json
```

成功采集结果会写入可解释的正文质量分和质量标记。低于
`content_quality_review_threshold` 的内容仍保留证据，但 `parse_status` 为 `needs_review`，
并创建幂等的 `content_quality` 核验任务。扫描型 PDF 使用 `ocr_required` 明确降级；旧版
DOC/XLS 使用 `legacy_office_conversion_required`；链接型 PNG/JPG/TIFF/WebP 公告也会作为附件
保存并标记 `ocr_required`。原文件均保留供 OCR、格式转换或人工核验。

本地网络不稳定时可以临时缩短超时：

```powershell
python -m job_watcher.cli crawl-once --limit 5 --timeout 4
```

清理弱线索：

```powershell
python -m job_watcher.cli cleanup-weak-leads
```

线索生成规则：

- 招聘入口、网申系统、招聘官网保留在 `sources` 中。
- `job_leads` 只保存明确 2027 届校园招聘公告/岗位线索。
- 单独命中 `网申`、`投递`、`简历`、`截止时间` 不生成线索。

## 主动搜索监控

主动搜索是项目核心能力。企业表只决定优先级，不限制搜索范围。

生成搜索任务：

```powershell
$env:PYTHONPATH="E:\job_watcher\src"
python -m job_watcher.cli generate-search-tasks --max-companies 80 --providers baidu zhihu
```

运行搜索任务：

```powershell
python -m job_watcher.cli run-search-tasks --limit 20 --count 5 --timeout 20
```

分类搜索结果：

```powershell
python -m job_watcher.cli classify-search-results --limit 200
```

搜索结果分类：

- 明确 2027 届 + 校园招聘 + 已知企业：进入 `job_leads`。
- 明确 2027 届 + 青岛/山东 + 表外企业：进入 `discovered_companies` 和待复核。
- 招聘入口/网申系统：进入 `sources` 或待复核，不当作招聘公告。
- 旧届别或弱相关：标记为无效/忽略。

当前本机验证结果：

- `crawl_snapshots` 表已创建。
- `job_leads` 表已创建。
- 看板 `/leads` 页面可访问。
- 本机 DNS 对多个招聘/政府站点解析超时，第一轮抓取没有生成快照和线索。

如果本机需要走 v2rayN/v2rayNG 代理，可在运行前设置标准代理环境变量，例如：

```powershell
$env:HTTPS_PROXY="http://127.0.0.1:7890"
$env:HTTP_PROXY="http://127.0.0.1:7890"
```

修正候选处理规则：

- `accept_official`：生成/更新 `verified_official` 来源。
- `accept_recruitment`：生成/更新 `verified_recruitment` 来源。
- `accept_government`：生成/更新 `verified_government` 来源。
- `accept_platform`：生成/更新 `verified_platform` 来源。
- `accept_reference`：保存为参考来源，默认不启用监控。
- `reject`：拒绝候选。
- `needs_more_search`：保留待继续搜索。

如果没有安装包，可以临时设置 `PYTHONPATH`：

```powershell
$env:PYTHONPATH="E:\job_watcher\src"
python -m job_watcher.cli config-check
```
