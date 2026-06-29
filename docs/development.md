# 青岛国企 2027 秋招信息助手开发文档

## 0. 文档索引

本项目从当前阶段开始按软件工程流程推进。后续开发以以下文档为准：

- `docs/requirements.md`：需求规格说明，定义 MVP 做什么、不做什么、验收标准。
- `docs/architecture.md`：系统架构设计，定义模块、数据流、数据库和状态机。
- `docs/roadmap.md`：开发路线图，定义里程碑和当前下一步。
- `docs/data_verification.md`：企业数据核实与修正规则。
- `docs/information_sources.md`：信息来源清单与接入策略。
- `docs/development.md`：主开发说明和历史上下文。

当前推荐执行顺序：

```text
Milestone 1：工程骨架与配置
Milestone 2：数据库与导入器
Milestone 3：Web 看板 MVP
```

当前工程进展：

- SQLite 数据库、种子导入和候选导入已可用。
- 本地 Web 看板已可用，默认入口：`http://127.0.0.1:8000/companies`。
- 来源、修正候选、覆盖率页面已可用。
- 低风险来源保守自动确认已完成第一轮，P0/P1 可信来源覆盖 31 / 215，明确招聘入口覆盖 14 / 215。
- 轻量监控 crawler 第一版已完成，待在 VPS 或配置本机代理后跑通成功抓取。

## 1. 项目定位

本项目是一个面向个人使用的招聘信息汇总与求职进度助手，重点关注青岛地区国企、央企驻青岛单位，以及相关泛计算机岗位，尤其是网络安全方向。

项目核心不依赖大模型。基础能力由传统程序完成，包括企业数据管理、信息源监控、网页抓取、规则过滤、数据库存储、原文快照、表格展示和飞书推送。大模型只作为辅助模块，用于低频、高价值的信息抽取、相关性判断、摘要生成和后续对话问答。

## 2. 当前已知条件

- 初始企业表：`青岛国企.xlsx`
- 主要数据表：`主体公司`
- 企业记录数：约 500 条
- 重点优先级：
  - `P0 必看`
  - `P1 优先`
- 目标区域：青岛为主，兼顾山东/青岛相关和央企青岛岗位
- 目标岗位：泛计算机类，以网络安全为核心
- 手机端：Android
- 移动交互方案：飞书机器人优先
- 邮箱：QQ 邮箱，后续通过 IMAP 接入
- 部署方式：
  - 本地 Windows 优先开发和调试
  - VPS 后续长期常驻运行
- VPS 条件：
  - Rocky Linux 9.6
  - 2 核 CPU
  - 1GB RAM + 545MB Swap
  - 21.6GB Disk

## 3. 总体目标

第一阶段目标是做出一个稳定可用的 MVP：

1. 先完成本地企业表的数据核实与清洗。
2. 导入并管理企业种子库。
3. 对企业官网、招聘入口和公共信息源做轻量监控。
4. 抓取并保存原文快照。
5. 通过规则筛选出疑似招聘线索。
6. 将招聘线索写入数据库。
7. 在 Web 看板中展示、筛选、修改状态和备注。
8. 每天通过飞书推送新增线索和摘要。

中长期目标是在此基础上扩展：

1. 大模型辅助抽取和摘要。
2. QQ 邮箱求职邮件整理。
3. 面试、笔试、测评日程和待办管理。
4. 飞书双向对话助手。
5. Windows 本机重任务与 VPS 轻量常驻协同。

## 4. 设计原则

### 4.0 数据先核实再监控

原始企业表只作为候选数据。项目启动前必须先做数据核实与清洗，尤其是 P0/P1 企业。对错误或过期的数据，应尽量通过检索修正为可信官网、招聘入口、集团归属或权威来源，而不是仅标记错误后放弃。

详细规则见：

- `docs/data_verification.md`

### 4.1 稳定优先

不要把核心流程交给大模型 Agent 或浏览器 Agent。监控、过滤、存储、调度必须由可复现的传统程序完成。

### 4.2 低成本运行

VPS 配置较低，因此常驻服务必须轻量：

- 第一版不依赖 Docker。
- 第一版不常驻 Playwright/Chrome。
- 第一版使用 SQLite。
- 控制抓取并发和频率。
- 快照压缩保存。

### 4.3 来源可追溯

所有招聘线索必须保留：

- 来源 URL
- 来源类型
- 抓取时间
- 原始标题
- 原始正文或 HTML 快照
- 内容哈希
- 规则命中原因
- 可信度评分

### 4.4 人工可校正

自动抓取一定会误判。因此每条线索都应该能在看板中手动修改：

- 公司匹配
- 招聘类型
- 目标届别
- 截止时间
- 是否网络安全相关
- 状态
- 备注

### 4.5 大模型只处理高价值候选

大模型调用必须经过规则过滤，避免对所有网页全文调用模型。

推荐流程：

```text
网页抓取
  -> 正文提取
  -> 关键词和规则打分
  -> 生成候选线索
  -> 高分或低置信关键项调用大模型
  -> 结构化入库
```

## 5. 系统架构

```text
青岛国企.xlsx
  -> 企业导入器
  -> companies 企业主数据

定时调度器
  -> 信息源抓取器
  -> 原文快照 snapshots
  -> 规则过滤器
  -> 招聘线索 job_leads
  -> 飞书推送

Web 看板
  -> 企业库
  -> 招聘线索
  -> 已确认岗位
  -> 我的投递进度
  -> 待办事项

后续模块
  -> QQ 邮箱解析
  -> 大模型抽取/摘要
  -> 飞书双向对话
  -> Windows 重任务执行器
```

## 6. 技术选型

### 6.1 后端

- Python 3.11+
- FastAPI
- Uvicorn
- SQLAlchemy 或 SQLModel
- Alembic 可后续加入

### 6.2 数据库

第一版：

- SQLite

后续可迁移：

- PostgreSQL

### 6.3 抓取和正文提取

第一版：

- httpx
- BeautifulSoup4
- trafilatura 或 readability-lxml

后续：

- Playwright 仅用于动态页面，优先在 Windows 本机低频运行。

### 6.4 定时任务

本地开发：

- APScheduler

VPS 部署：

- systemd service 常驻
- 或 cron 调用 CLI 任务

### 6.5 Web 看板

第一版建议轻量实现：

- FastAPI + Jinja2
- HTMX 可选
- 少量原生 CSS/JS

不建议第一版引入复杂前端框架。

### 6.6 手机推送

第一版：

- 飞书自定义机器人 Webhook

第二阶段：

- 飞书自建应用
- 支持双向消息回调

### 6.7 大模型

第一版可先预留接口，不强制接入。

后续可支持：

- OpenAI API
- 兼容 OpenAI 接口的其他模型服务

## 7. 数据模型草案

### 7.1 companies 企业主数据

来源：`青岛国企.xlsx` 的 `主体公司` sheet。

字段建议：

- `id`
- `group_name`：归属集团
- `company_name`：主体公司/机构
- `entity_type`：层级/性质
- `region`
- `priority`
- `difficulty`
- `education_barrier`
- `recommended_directions`
- `action_status`
- `source_urls`
- `url_notes`
- `normalized_name`
- `aliases`
- `ownership_type`：央企、地方国企、国资控股、待核
- `is_active`
- `created_at`
- `updated_at`

### 7.2 sources 信息源配置

用于管理需要定期监控的网站或页面。

- `id`
- `company_id`
- `source_type`：official、government、campus、platform、search、manual
- `name`
- `url`
- `crawl_frequency`
- `trust_level`
- `enabled`
- `last_checked_at`
- `last_success_at`
- `last_error`
- `created_at`
- `updated_at`

### 7.3 crawl_snapshots 抓取快照

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

快照文件建议保存在：

```text
data/snapshots/yyyy/mm/dd/{snapshot_id}.html.gz
data/snapshots/yyyy/mm/dd/{snapshot_id}.txt.gz
```

### 7.4 job_leads 招聘线索

自动发现但未必确认的信息。

- `id`
- `company_id`
- `source_id`
- `snapshot_id`
- `title`
- `url`
- `source_type`
- `published_at`
- `deadline`
- `target_year`
- `recruitment_type`
- `location`
- `matched_keywords`
- `computer_relevance_score`
- `security_relevance_score`
- `trust_score`
- `overall_score`
- `status`：new、pending_review、confirmed、ignored、duplicate、invalid、expired
- `llm_used`
- `llm_confidence`
- `summary`
- `created_at`
- `updated_at`

### 7.5 job_posts 已确认招聘公告/岗位

由 `job_leads` 人工确认或高可信自动转入。

- `id`
- `lead_id`
- `company_id`
- `title`
- `application_url`
- `deadline`
- `target_year`
- `recruitment_type`
- `locations`
- `directions`
- `is_security_related`
- `is_computer_related`
- `status`：watching、to_apply、applied、closed、ignored
- `notes`
- `created_at`
- `updated_at`

### 7.6 applications 我的投递进度

- `id`
- `job_post_id`
- `company_id`
- `position_name`
- `status`：interested、to_apply、applied、assessment、written_exam、interview_1、interview_2、final_interview、offer、rejected、closed、ignored
- `resume_version`
- `account_hint`
- `submitted_at`
- `next_action`
- `next_action_at`
- `notes`
- `created_at`
- `updated_at`

### 7.7 tasks 待办事项

- `id`
- `related_type`：lead、post、application、email
- `related_id`
- `title`
- `due_at`
- `priority`
- `status`：open、done、cancelled
- `created_at`
- `updated_at`

### 7.8 notifications 推送记录

- `id`
- `channel`：feishu
- `related_type`
- `related_id`
- `title`
- `content`
- `sent_at`
- `send_status`
- `error`

### 7.9 email_events 邮件事件，后续实现

- `id`
- `mailbox`
- `message_id`
- `from_addr`
- `subject`
- `received_at`
- `company_id`
- `application_id`
- `event_type`：application_confirmed、assessment、written_exam、interview、offer、rejection、unknown
- `event_time`
- `meeting_url`
- `summary`
- `status`
- `created_at`
- `updated_at`

## 8. 信息源分级

详细来源清单见：

- `docs/information_sources.md`

### P0 官方源

- 企业官网
- 集团招聘官网
- 官方招聘系统
- 官方公众号文章

可信度高，可以作为确认依据。

### P1 政府和公共平台

- 青岛市国资委相关网站
- 青岛市人社局
- 公共就业服务平台
- 国聘
- 地方人才集团平台

适合发现本地国企招聘和公共招聘公告。

### P2 高校就业网

重点关注：

- 中国海洋大学
- 中国石油大学华东
- 青岛大学
- 山东大学
- 山东科技大学
- 青岛科技大学
- 青岛理工大学
- 哈工大威海

这类来源适合作为线索源，后续再核验官方链接。

### P3 搜索发现

用于发现官网入口和新公告，不作为最终可信来源。

关键词示例：

```text
青岛 国企 2027届 校园招聘 网络安全
青岛 央企 2027届 信息安全
公司名 2027届 校招
公司名 校园招聘 青岛 信息技术
公司名 招聘 官网
公司名 网申
```

### P4 商业招聘平台

- 前程无忧
- 智联招聘
- 猎聘
- BOSS 直聘
- 应届生求职网

第一版只作为补充线索，不作为核心源。

## 9. 关键词和评分规则

重要边界：

- 招聘入口不是招聘公告。
- `网申`、`投递`、`简历`、`截止时间` 等只能作为上下文词，不能单独生成 `job_leads`。
- 第一版 `job_leads` 必须同时满足：
  - 明确命中 2027 届：`2027届`、`2027 届`、`27届`、`2027年应届`、`2027毕业` 等。
  - 明确命中校园招聘语义：`校园招聘`、`校招`、`秋招`、`秋季招聘`、`应届生`、`管培生`、`招聘简章` 等。
- 不满足上述条件的招聘系统、网申入口、公司招聘首页，应保留为 `sources`，不进入 `job_leads`。

### 9.1 招聘相关关键词

强相关：

```text
2027届、2027 届、27届、2027年应届、2027毕业、校园招聘、秋招、秋季招聘、校招、应届生、管培生、招聘简章
```

辅助相关：

```text
网申、宣讲会、双选会、笔试、面试、测评、投递、简历、截止时间
```

### 9.2 网络安全关键词

```text
网络安全、信息安全、数据安全、等保、渗透测试、安全运营、SOC、应急响应、漏洞、攻防、密码、商用密码、信创安全
```

### 9.3 泛计算机关键词

```text
软件开发、后端、Java、Python、C++、前端、算法、数据分析、大数据、云计算、运维、系统工程师、数据库、IT、信息技术、数字化、信息化、网络管理
```

### 9.4 线索分级

- 高价值线索：
  - 官方/政府源
  - 明确同时出现 2027 届和校园招聘语义
  - 匹配 P0/P1 企业
  - 命中计算机或网络安全关键词

- 中价值线索：
  - 高校就业网或国聘
  - 公司匹配明确
  - 2027 届明确，但岗位方向或公司匹配需要复核

- 低价值线索：
  - 商业平台或搜索结果
  - 公司匹配不稳定
  - 招聘类型、届别、岗位方向不清晰，只能作为搜索/复核候选，不能直接推送

## 10. Web 看板视图

### 10.1 企业库

功能：

- 查看企业列表
- 按优先级、区域、集团、岗位方向筛选
- 查看 URL 状态
- 查看最近检查时间
- 查看最近线索
- 修改备注和启用状态

### 10.2 招聘线索

功能：

- 查看新发现线索
- 筛选来源、可信度、相关性、状态
- 查看原文快照
- 标记确认、忽略、重复、无关
- 编辑公司匹配、截止时间、招聘类型、备注

### 10.3 已确认招聘

功能：

- 管理正式关注的招聘公告和岗位
- 标记待投递、已投递、已关闭
- 管理网申链接和截止时间

### 10.4 我的投递进度

功能：

- 查看每家公司/岗位状态
- 管理下一步行动
- 管理面试、笔试、测评时间
- 添加备注

### 10.5 每日更新

功能：

- 展示当天新增线索
- 展示高价值线索
- 展示待确认线索
- 展示系统抓取统计和错误

## 11. 飞书推送

### 11.1 第一版推送内容

- 每日摘要
- 高价值新线索
- 待确认线索汇总
- 抓取失败提醒

### 11.2 推送格式

示例：

```text
【青岛国企秋招助手】今日新增 6 条线索

高价值 2 条：
1. 中国中车 - 2027届校园招聘
   来源：官网
   方向：软件/网络安全
   链接：https://...

待确认 4 条：
1. 青岛地铁 - 校园招聘公告
   来源：高校就业网
   命中：校招、信息技术

看板：http://your-server/...
```

### 11.3 后续双向对话

第二阶段可支持：

```text
今天有什么新线索？
哪些 P0 企业还没更新？
最近有哪些网络安全岗位？
把第 12 条标记为已投递。
中国中车现在是什么状态？
```

## 12. 大模型辅助设计

### 12.1 调用场景

- 抽取招聘公告结构化字段
- 判断是否 2027 秋招
- 判断是否网络安全/泛计算机相关
- 总结每日新增线索
- 后续处理飞书自然语言查询

### 12.2 不调用场景

- 不对所有网页全文调用
- 不用大模型做持续网页浏览
- 不用大模型替代数据库查询
- 不用大模型保存唯一事实来源

### 12.3 推荐输出 JSON

```json
{
  "is_relevant": true,
  "company": "公司名称",
  "target_year": "2027",
  "recruitment_type": "秋招",
  "is_computer_related": true,
  "is_security_related": true,
  "deadline": null,
  "application_url": "https://...",
  "confidence": 0.86,
  "reason": "标题和正文出现 2027届校园招聘，并包含信息安全岗位。"
}
```

## 13. 部署方案

### 13.1 本地开发

本地路径：

```text
E:\job_watcher
```

本地负责：

- 开发调试
- 企业表导入
- 看板开发
- 飞书推送测试
- 大批量 URL 校验
- Playwright 动态页面调试

### 13.2 VPS 常驻

VPS 负责：

- 轻量抓取
- 数据库常驻
- Web 看板
- 定时任务
- 飞书推送

建议部署方式：

- Python venv
- systemd service
- Nginx 或 Caddy 反向代理
- SQLite 数据文件定期备份

### 13.3 不建议第一版使用

- Docker
- 本地大模型
- 常驻 Chrome/Playwright
- Elasticsearch
- 重型前端构建服务

## 14. 配置文件草案

建议使用：

```text
config/settings.yaml
```

示例：

```yaml
app:
  name: qingdao-job-watcher
  timezone: Asia/Shanghai

database:
  url: sqlite:///data/job_watcher.db

crawler:
  user_agent: Mozilla/5.0
  timeout_seconds: 20
  max_concurrency: 3
  snapshot_enabled: true

monitor:
  default_frequency_hours: 24
  priority_scope:
    - P0
    - P1

feishu:
  enabled: false
  webhook_url: ""

llm:
  enabled: false
  provider: openai_compatible
  model: ""
  api_key_env: LLM_API_KEY
```

## 15. 推荐项目结构

```text
job_watcher/
  docs/
    development.md
  config/
    settings.yaml
  data/
    job_watcher.db
    snapshots/
  src/
    job_watcher/
      __init__.py
      main.py
      config.py
      db.py
      models.py
      importers/
        company_excel.py
      crawler/
        fetcher.py
        extractor.py
        snapshots.py
      filters/
        keywords.py
        scoring.py
      sources/
        official.py
        campus.py
        government.py
      notify/
        feishu.py
      web/
        app.py
        templates/
        static/
      scheduler/
        jobs.py
      llm/
        extractor.py
  scripts/
    import_companies.py
    run_crawl_once.py
    send_daily_digest.py
  tests/
```

## 16. MVP 开发顺序

### Milestone 0：本地表格核实与清洗

1. 读取 `青岛国企.xlsx` 的 `主体公司` sheet。
2. 标准化字段名、优先级、企业名称和 URL。
3. 拆分一家公司对应的多个 URL。
4. 检查必填字段缺失、疑似重复主体、优先级异常和 URL 格式异常。
5. 对 P0/P1 企业优先做事实核实。
6. 对错误或过期 URL 尽量检索修正，补充可信官网、招聘入口或权威来源。
7. 生成清洗后的企业种子表和 URL 来源种子表。
8. 生成数据审计报告，原始 Excel 不直接覆盖。

当前产物：

- `scripts/audit_company_data.py`
- `scripts/verify_sources.py`
- `scripts/build_correction_queue.py`
- `scripts/build_search_tasks.py`
- `scripts/build_correction_candidates.py`
- `data/processed/companies_seed.csv`
- `data/processed/company_sources_seed.csv`
- `data/audit/company_data_audit.md`
- `data/audit/company_cleaning_issues.csv`
- `data/audit/url_check_results.csv`
- `data/audit/source_verification_results.csv`
- `data/audit/source_verification_summary.md`
- `data/audit/source_correction_queue.csv`
- `data/audit/search_tasks.csv`
- `data/manual_search_results.example.csv`
- `config/sources.yaml`

当前结果：

- 企业记录：500 条
- 拆分 URL 来源：690 条
- 第一版默认启用 P0/P1 企业：215 条
- 必填字段缺失：0 条
- 疑似重复主体：0 条
- 第一批 URL 核验样本：20 条
- 第一批 URL 修正队列：20 条
- 第一批搜索任务：160 条
- 已导入固定公共来源：15 条
- 已导入修正候选：19 条
- 已自动确认低风险来源：100 条
- P0/P1 已有可信来源企业：31 家
- P0/P1 已有明确招聘入口企业：14 家

注意：URL 在线可访问性检测应作为独立队列处理，不能阻塞表格清洗主流程。部分站点会拦截自动请求或临时超时，不可访问不等同于数据错误。

验收标准：

- 原始 Excel 保持不变。
- 清洗后的企业种子表可被数据库导入。
- URL 来源表可被后续 crawler/sources 模块使用。
- 数据问题清单可在看板中逐步复核。
- 错误 URL 不只是标记 invalid，应优先进入搜索修正流程。

### Milestone 1：数据底座

1. 创建项目结构。
2. 创建配置文件。
3. 创建 SQLite 数据库和模型。
4. 实现 `data/processed/companies_seed.csv` 和 `data/processed/company_sources_seed.csv` 导入。
5. 导入 `docs/information_sources.md` 中确定的第一批固定公共源。
6. 支持重复导入时更新企业记录和 source 记录。

验收标准：

- 500 条企业数据可导入。
- P0/P1 企业可筛选。
- URL 字段可拆分成多个 source。
- 固定公共源可作为全局 source 导入。

### Milestone 2：看板雏形

1. 创建 FastAPI Web 服务。
2. 实现企业库页面。
3. 实现招聘线索页面。
4. 支持状态和备注修改。

验收标准：

- 浏览器可查看企业库。
- 可按优先级和区域筛选。
- 可修改企业启用状态或备注。

### Milestone 3：轻量抓取

1. 实现 HTTP 抓取。
2. 保存快照。
3. 提取标题和正文。
4. 关键词打分。
5. 生成 job_leads。

当前实现：

- CLI：`python -m job_watcher.cli crawl-once --limit 20`
- 临时超时覆盖：`python -m job_watcher.cli crawl-once --limit 5 --timeout 4`
- 弱线索清理：`python -m job_watcher.cli cleanup-weak-leads`
- 数据表：`crawl_snapshots`、`job_leads`
- 看板页面：`/leads`
- 快照目录：`data/snapshots/yyyy/mm/dd/`
- 线索生成规则：必须同时命中 2027 届和校园招聘语义；单独 `网申` 不生成线索。

当前本机限制：

- 多个招聘/政府站点在本机出现 DNS 解析超时。
- 第一轮本机抓取测试没有生成快照和线索。
- 后续应优先在 VPS 上跑首轮抓取，或在本机设置 `HTTP_PROXY` / `HTTPS_PROXY` 后重试。

验收标准：

- 可对 P0/P1 企业 URL 跑一次抓取。
- 新线索入库。
- 重复内容不会反复生成线索。

### Milestone 4：飞书推送

1. 实现飞书 webhook 推送。
2. 实现每日摘要。
3. 实现高价值线索即时或定时推送。

验收标准：

- 本地可以向飞书发送测试消息。
- 每日摘要包含新增线索和待确认线索。

### Milestone 5：VPS 部署

1. 编写部署说明。
2. 配置 systemd。
3. 配置反向代理和访问认证。
4. 配置备份。

验收标准：

- VPS 可持续运行。
- 每天自动抓取和推送。
- Web 看板可访问。

## 17. 后续扩展

### 17.1 QQ 邮箱

- IMAP 授权码接入。
- 只扫描求职相关关键词。
- 抽取面试、笔试、测评、offer、拒信等事件。
- 更新 application 和 task。

### 17.2 飞书双向助手

- 接收消息回调。
- 支持自然语言查询。
- 支持状态更新。
- 大模型只负责意图解析和摘要，数据库作为事实来源。

### 17.3 Windows 重任务执行器

- 批量 Playwright 动态页面抓取。
- 大模型批量结构化。
- 结果回写 SQLite 或导出同步文件。

## 18. 当前待确认问题

1. 飞书第一版使用自定义机器人 webhook，还是直接创建飞书自建应用？
2. Web 看板是否需要公网访问，还是只通过 Tailscale/内网访问？
3. 第一版监控范围是否限定为 `P0 必看` 和 `P1 优先`？
4. 大模型第一版是否先预留接口、不实际接入？
5. 快照保留策略：长期全部保留，还是 6-12 个月后压缩归档？
