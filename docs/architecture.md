# 系统架构设计

## 1. 架构目标

本系统采用轻量、可追溯、可分阶段扩展的架构。第一版以本地 Windows 开发为主，后续部署到低配 Rocky Linux VPS 常驻运行。

架构目标：

- 数据先核实，再监控。
- 数据库作为事实中心。
- 搜索和爬虫只产生候选，不直接覆盖事实。
- 人工确认是可信来源进入监控的关键步骤。
- 大模型只作为可选辅助，不参与主流程稳定性。

## 2. 总体架构（当前 V1）

```text
青岛国企.xlsx
  -> audit_company_data.py
  -> companies_seed.csv
  -> company_sources_seed.csv

候选来源
  -> verify_sources.py
  -> source_verification_results.csv
  -> build_correction_queue.py
  -> source_correction_queue.csv

修正队列
  -> build_search_tasks.py
  -> Search Providers
       - Zhihu
       - Baidu
       - Bocha
       - Manual
  -> manual_search_results.csv
  -> build_correction_candidates.py
  -> correction_candidates.csv
  -> build_review_sheet.py
  -> source_review_sheet.csv

可信来源 / 搜索 / 人工导入
  -> Collector
  -> source_runs
  -> raw_items + 原始附件
  -> 招聘分类与字段提取
  -> 企业识别
  -> 候选事件检索与保守归并
  -> job_events + job_positions
  -> applications + review_tasks

Web 看板
  -> 今日雷达
  -> 招聘事件与全部证据来源
  -> 企业和来源管理
  -> 覆盖中心
  -> 投递进度与人工核验

后续
  -> 每日简报 / 飞书
  -> 邮箱 / 日程
```

## 3. 模块划分

### 3.1 importers

负责从外部文件导入项目数据。

输入：

- `companies_seed.csv`
- `company_sources_seed.csv`
- `config/sources.yaml`

输出：

- `companies`
- `sources`

要求：

- 幂等。
- 可重复执行。
- 保留原始字段。

### 3.2 verification

负责 URL 核验和来源状态判断。

能力：

- HTTP/TLS 访问检测。
- 页面标题提取。
- 内容类型检测。
- JS 外壳判断。
- 低权威来源识别。
- 生成修正队列。

### 3.3 search

负责搜索 Provider 和候选打分。

Provider：

- `ZhihuGlobalSearchProvider`
- `BaiduWebSearchProvider`
- `BochaWebSearchProvider`
- `ManualSearchProvider`，后续实现为导入 CSV。

输出统一格式：

- title
- url
- snippet
- provider
- rank
- query

### 3.4 scoring

负责搜索结果和招聘线索的规则评分。

第一版评分维度：

- 标题是否匹配公司名。
- URL 是否匹配公司名。
- 摘要是否匹配公司名。
- 是否命中招聘关键词。
- 是否命中网络安全/计算机关键词。
- 域名是否政府、国聘、高校、招聘平台、低权威来源。

### 3.5 storage

负责数据库模型、连接和导入。

第一版数据库：

- SQLite

核心事实表（V1 数据底座）：

- `companies`：企业、事业单位、分支机构及集团层级。
- `sources`：官网、公众号、公共平台、社区和搜索引擎渠道。
- `search_tasks`：主动搜索与新主体/新渠道发现任务。
- `raw_items`：逐来源保存的原始采集证据。
- `job_events`：多来源归并后的招聘事件。
- `job_positions`：招聘事件中的具体岗位。
- `applications`：个人投递流程。
- `review_tasks`：所有无法自动确认的问题。

旧表 `crawl_snapshots`、`job_leads` 和 `correction_candidates` 在迁移期保留，
后续通过归并任务逐步写入新的事实表，不进行破坏性删除。

后续可迁移：

- PostgreSQL

### 3.6 web

负责 Web 看板。

当前看板使用 Python 标准库 HTTP 服务和服务端 HTML，默认只绑定本机地址；阶段 C 继续复用
现有页面完成证据和归并状态展示。数据链路稳定后再迁移 FastAPI/Jinja2，不引入复杂前端框架。

### 3.7 collectors 与 crawler

负责可信来源抓取、正文与附件解析、证据保存和运行状态记录。

当前已实现统一 HTTP/可选浏览器采集契约、失败分类、附件解析、质量评分、二进制证据保存和
22 个真实站点固定验收池。采集层只生成 `raw_items`，不直接制造不可追溯的招聘事实。

### 3.8 recruitment processing（当前阶段）

负责把合格 `raw_items` 转换为 `job_events` 和 `job_positions`，包含招聘分类、字段提取、
企业匹配、保守去重、个人匹配和人工核验。详细契约见 `stage_c_implementation_plan.md`。

### 3.9 notify，后续阶段

负责飞书推送。

第一版 MVP 可暂不实现，下一阶段实现单向 webhook。

## 4. 数据流

### 4.1 企业数据流

```text
Excel 原始表
  -> 清洗
  -> companies_seed.csv
  -> 数据库 companies
```

原则：

- 原始 Excel 不覆盖。
- 数据库保存原始值和标准化值。
- 修正后的事实写入数据库。

### 4.2 来源数据流

```text
company_sources_seed.csv
  -> sources(candidate)
  -> source_verification
  -> source_correction_queue
  -> search_tasks
  -> search_results
  -> correction_candidates
  -> 人工确认
  -> sources(verified_*)
```

原则：

- 候选来源不直接参与正式监控。
- 可信来源必须经过规则高置信或人工确认。
- 错误来源优先修正，而不是删除。

### 4.3 搜索数据流

```text
query
  -> provider
  -> raw results
  -> normalized search_results
  -> scoring
  -> correction_candidates
```

搜索结果只作为候选。

### 4.4 监控与招聘事件数据流

```text
verified source / search clue / manual import
  -> collector
  -> raw_items
  -> content quality gate
  -> recruitment parser
  -> entity matching
  -> deduplication or review_tasks
  -> job_events + job_positions
  -> personal matching
  -> radar / applications / briefs
```

原则：旧 `crawl_snapshots` 和 `job_leads` 仅用于兼容迁移；所有新增招聘事实必须从
`raw_items` 建立证据关联，不得直接写入旧线索模型后再反向补证据。

## 5. 数据库设计草案

### 5.1 companies

企业主数据。

字段：

- `id`
- `company_key`
- `original_group_name`
- `group_name`
- `original_company_name`
- `company_name`
- `normalized_name`
- `aliases`
- `entity_type`
- `region`
- `priority_raw`
- `priority`
- `difficulty`
- `education_barrier`
- `recommended_directions`
- `action_status`
- `ownership_type`
- `verification_status`
- `enabled`
- `notes`
- `created_at`
- `updated_at`

唯一键：

- `company_key`

### 5.2 sources

来源 URL。

字段：

- `id`
- `company_id`
- `name`
- `url`
- `original_url`
- `source_type`
- `provider`
- `trust_level`
- `verification_status`
- `requires_browser`
- `enabled`
- `parent_source_id`
- `discovered_by`
- `discovered_at`
- `last_verified_at`
- `last_checked_at`
- `notes`
- `created_at`
- `updated_at`

### 5.3 source_verifications

URL 核验日志。

字段：

- `id`
- `source_id`
- `url`
- `http_status`
- `final_url`
- `content_type`
- `page_title`
- `verification_status`
- `error`
- `verified_at`

### 5.4 search_tasks

搜索任务。

字段：

- `id`
- `company_id`
- `source_id`
- `query`
- `provider`
- `status`
- `reason`
- `created_at`
- `executed_at`
- `error`

### 5.5 search_results

搜索结果。

字段：

- `id`
- `task_id`
- `company_id`
- `provider`
- `rank`
- `title`
- `url`
- `snippet`
- `created_at`

### 5.6 correction_candidates

修正候选。

字段：

- `id`
- `company_id`
- `source_id`
- `search_result_id`
- `candidate_url`
- `candidate_title`
- `candidate_snippet`
- `candidate_source_type`
- `score`
- `confidence`
- `score_reasons`
- `review_status`
- `decision`
- `review_notes`
- `reviewed_at`

### 5.7 crawl_snapshots，后续

抓取快照。

字段：

- `id`
- `source_id`
- `url`
- `status_code`
- `final_url`
- `title`
- `raw_html_path`
- `raw_text_path`
- `content_hash`
- `fetched_at`
- `error`

### 5.8 job_leads，后续

招聘线索。

字段见 `docs/development.md`。

## 6. 状态机

### 6.1 企业核实状态

```text
candidate
  -> verified
  -> corrected
  -> needs_review
  -> out_of_scope
```

说明：

- `candidate`：来自原始表，结构完整但事实未核实。
- `verified`：关键事实已核实。
- `corrected`：原始数据有错误，已修正。
- `needs_review`：自动判断不确定。
- `out_of_scope`：不符合项目范围。

### 6.2 来源核实状态

```text
candidate
  -> verified_official
  -> verified_recruitment
  -> verified_government
  -> verified_platform
  -> needs_search
  -> needs_browser
  -> invalid_replaced
  -> invalid_unresolved
```

### 6.3 修正候选状态

```text
pending
  -> accepted
  -> rejected
  -> needs_more_search
```

候选决策：

- `accept_official`
- `accept_recruitment`
- `accept_government`
- `accept_platform`
- `accept_reference`
- `reject`
- `needs_more_search`

## 7. 配置与密钥

配置文件：

- `config/sources.yaml`
- 后续 `config/settings.yaml`

密钥只能来自环境变量：

- `ZHIHU_API_KEY`
- `ZHIHU_RESOLVE_IP`
- `BAIDU_SEARCH_API_KEY`
- `BAIDU_RESOLVE_IP`
- `BOCHA_API_KEY`
- 后续 `FEISHU_WEBHOOK_URL`

禁止：

- 把 key 写入源码。
- 把 key 写入文档。
- 把 key 写入 CSV。
- 把 `.env` 提交。

## 8. 部署架构

### 8.1 本地开发

本地负责：

- 数据清洗。
- API 调试。
- Web 看板开发。
- 大批量核实。

### 8.2 VPS 常驻

VPS 负责：

- SQLite 数据库。
- Web 看板。
- 轻量定时任务。
- 飞书推送。

VPS 约束：

- 1GB RAM。
- 不常驻 Playwright。
- 不跑本地大模型。
- 不使用重型数据库。

## 9. 下一阶段实现边界

下一阶段只实现：

- 数据库。
- 导入器。
- Web 看板基础页面。
- 人工确认可信来源。

不实现：

- 正式招聘监控 crawler。
- 飞书推送。
- 邮箱/日程。
- 大模型助手。
