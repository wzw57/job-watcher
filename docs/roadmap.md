# 开发路线图

## 1. 当前阶段

当前项目处于工程化收口阶段。

已完成：

- 项目定位和范围讨论。
- 原始企业表结构清洗。
- 候选 URL 拆分。
- URL 核验脚本。
- 修正队列生成。
- 搜索任务生成。
- 搜索 Provider 接入：
  - 知乎
  - 百度
  - 博查，额度不足时备用
- 搜索结果评分。
- 人工复核表生成。
- 固定公共信息源配置。
- 需求、架构、数据核实文档。
- SQLite 数据库和种子导入。
- 本地 Web 看板 MVP。
- 来源/候选人工确认流程。
- 可信来源覆盖率页面和 CLI。
- 低风险来源保守自动确认。
- 轻量 crawler 第一版：
  - verified sources 抓取
  - HTML/text 快照保存
  - 内容 hash 去重
  - 2027 届校园招聘强证据线索生成
  - 招聘线索看板
  - 弱线索清理

尚未完成：

- 持续搜索监控：
  - 每日搜索 P0/P1 企业 + 2027 届 + 校招/秋招关键词
  - 对搜索结果做去重、评分和人工复核
  - 发现新的公告页和招聘路径后回写 sources/job_leads
- 飞书推送。

## 2. Milestone 0：数据核实准备，已基本完成

目标：

把原始 Excel 变成可导入数据库的候选数据，并建立搜索修正流程。

已完成产物：

- `scripts/audit_company_data.py`
- `scripts/verify_sources.py`
- `scripts/build_correction_queue.py`
- `scripts/build_search_tasks.py`
- `scripts/build_correction_candidates.py`
- `scripts/build_review_sheet.py`
- `data/processed/companies_seed.csv`
- `data/processed/company_sources_seed.csv`
- `data/audit/source_review_sheet.csv`
- `config/sources.yaml`

剩余事项：

- 不再继续堆脚本。
- 后续新增功能优先进入正式包结构和数据库。

## 3. Milestone 1：工程骨架与配置

目标：

把当前脚本项目整理成正式 Python 工程。

状态：进行中。

任务：

1. 创建 `pyproject.toml`。已完成。
2. 创建 `.env.example`。已完成。
3. 创建 `config/settings.yaml`。已完成。
4. 整理包结构。已完成：
   - `src/job_watcher/config.py`
   - `src/job_watcher/importers/`
   - `src/job_watcher/web/`
   - `src/job_watcher/search/`
   - `src/job_watcher/storage/`
   - `src/job_watcher/verification/`
5. 创建 CLI 入口。已完成：
   - `src/job_watcher/cli.py`
6. 保留现有脚本作为 CLI wrapper。待后续逐步迁移。

验收标准：

- 本地能安装或直接运行包。
- 配置和密钥读取规则明确。
- 不需要把 key 写入文件。

## 4. Milestone 2：数据库与导入器

目标：

建立 SQLite 数据库，并把现有 CSV/YAML 数据导入数据库。

状态：核心导入已完成。

任务：

1. 选型 SQLAlchemy 或 SQLModel。当前采用标准库 `sqlite3`，避免在本地和低配 VPS 上增加早期依赖；后续需要复杂查询时再迁移 ORM。
2. 定义模型。已完成 SQLite schema：
   - `Company`
   - `Source`
   - `SourceVerification`
   - `SearchTask`
   - `SearchResult`
   - `CorrectionCandidate`
3. 创建数据库初始化命令。已完成：`job-watcher db-init` / `python -m job_watcher.cli db-init`。
4. 实现企业导入。已完成。
5. 实现来源导入。已完成。
6. 实现固定公共源导入。已完成。
7. 实现搜索结果/修正候选导入。已完成候选导入，搜索结果导入待后续按 Provider 统一迁移。

验收标准：

- `companies_seed.csv` 能导入 500 条企业。已验证。
- `company_sources_seed.csv` 能导入 690 条候选来源。已验证。
- `config/sources.yaml` 能导入固定公共源。已验证，当前 15 条。
- 重复导入不产生重复记录。已验证。

## 5. Milestone 3：Web 看板 MVP

目标：

提供可管理、可展示、可人工确认的数据界面。

状态：MVP 已可用。

任务：

1. 创建 FastAPI 应用。暂缓；当前先使用标准库 `http.server` 实现本地 MVP，避免依赖安装阻塞。
2. 创建基础页面布局。已完成。
3. 企业库页面。已完成：
   - 列表
   - 筛选优先级/区域/状态
4. 来源页面。已完成：
   - 候选来源
   - 来源状态
   - URL
   - 来源类型
5. 修正候选页面。已完成：
   - 候选 URL
   - 分数
   - 命中原因
   - 人工确认按钮
6. 已确认来源页面。待实现，可先通过来源状态筛选查看；导航已提供“已确认官网/已确认招聘”入口。
7. 状态修改和备注保存。候选和来源状态更新已完成，备注仅候选支持。
8. 候选确认生成可信来源。已完成：
   - `accept_official` -> `verified_official`
   - `accept_recruitment` -> `verified_recruitment`
   - `accept_government` -> `verified_government`
   - `accept_platform` -> `verified_platform`
   - `accept_reference` -> 参考来源，不启用监控
9. 可信来源覆盖率页面。已完成：
   - P0/P1 总览
   - 按优先级统计
   - 待补全可信来源企业列表
   - CLI 命令：`python -m job_watcher.cli coverage`
10. 保守自动确认低风险来源。已完成：
   - CLI 命令：`python -m job_watcher.cli auto-confirm-sources`
   - `government` -> `verified_government`
   - `public_platform` / `campus` -> `verified_platform`
   - `official_recruitment` -> `verified_recruitment`
   - 不自动确认 `official_or_unknown`

验收标准：

- 浏览器能查看企业和来源。已验证。
- 用户能把候选 URL 确认为可信来源。基础表单已实现。
- 用户能拒绝低质量候选。基础表单已实现。
- 确认结果写回数据库。已验证。
- 接受候选后能生成/更新 verified source。已验证。
- 覆盖率页面可访问。已验证。

## 6. Milestone 4：可信来源管理

目标：

形成第一批可监控来源。

状态：进行中，第一批低风险来源已生成。

任务：

1. 从人工确认生成 verified sources。已完成基础流程。
2. 对 P0/P1 企业统计：
   - 已有可信官网。
   - 已有招聘入口。
   - 只有第三方来源。
   - 仍需搜索。
3. 输出可信来源覆盖率报告。已完成。
4. 支持人工新增来源。
5. 对低风险候选来源做保守自动确认。已完成第一轮。

当前覆盖率：

- P0/P1 企业：215 家
- 已有可信来源：31 家，覆盖率 14.42%
- 已有明确招聘入口：14 家，覆盖率 6.51%
- 仍只有候选来源：184 家

第一轮自动确认来源：

- 政府来源：53 条
- 公共平台/高校平台来源：19 条
- 明确招聘入口：28 条
- 合计：100 条

验收标准：

- P0/P1 企业可信来源覆盖率可查看。
- 每个可信来源有来源类型和证据。
- 未覆盖企业进入后续搜索队列。

## 7. Milestone 5：轻量监控 crawler

目标：

只对可信来源做低频监控，生成招聘线索。

状态：代码骨架已完成，本机和 VPS 均已跑通首轮抓取。规则已收紧：单独出现 `网申` 不再生成招聘线索。

任务：

1. HTTP 抓取。已完成第一版。
2. 页面标题/正文提取。已完成第一版。
3. 快照保存。已完成第一版，保存到 `data/snapshots`。
4. 内容 hash 去重。已完成第一版。
5. 关键词评分。已完成第一版。
6. 生成 `job_leads`。已完成第一版。
7. 看板展示招聘线索。已完成第一版：`/leads`。
8. 失败分类和浏览器队列。待实现。
9. 在 VPS 上跑通首轮成功抓取。已完成。
10. 清理弱线索。已完成：
   - CLI 命令：`python -m job_watcher.cli cleanup-weak-leads`
   - 缺少 2027 届或校园招聘语义的线索标为 `invalid`

关键规则：

- `sources` 可以保存招聘入口、网申系统、招聘官网。
- `job_leads` 只保存明确 2027 届校园招聘公告/岗位线索。
- `网申`、`投递`、`简历` 等词只作为上下文，不单独触发线索。

当前命令：

```powershell
python -m job_watcher.cli crawl-once --limit 20
python -m job_watcher.cli crawl-once --limit 5 --timeout 4
```

本机验证结果：

- `crawl_snapshots` 和 `job_leads` 表已创建。
- `/leads` 页面可访问。
- 本机关闭 TUN 后首轮抓取成功。
- VPS 首轮抓取成功。
- 铁塔网申入口类弱线索已标记为 `invalid`。

验收标准：

- 可以抓取一批 verified sources。
- 没变化的页面不会重复生成线索。
- 明确 2027 届校园招聘线索可在看板查看。

## 7.1 Milestone 5.5：持续搜索监控

目标：

不是只等已知 URL 更新，而是主动发现 2027 届央国企招聘公告和真实投递路径。

任务：

1. 建立每日搜索任务：
   - 公司名 + 2027届 + 校园招聘
   - 公司名 + 2027届 + 秋招
   - 公司名 + 2027届 + 网申
   - 公司名 + 网络安全 + 校园招聘
   - 青岛 + 国企/央企 + 2027届 + 校招
2. 搜索 Provider 统一入库：
   - 百度
   - 知乎全网搜索
   - 博查，额度可用时启用
3. 搜索结果生成候选：
   - 明确 2027 届公告 -> `job_leads`
   - 招聘入口/专题页 -> `sources`
   - 不确定结果 -> `correction_candidates`
4. 对 P0/P1 企业优先执行。
5. 飞书只推送高置信 `job_leads`，不推泛招聘入口。

验收标准：

- 每日能发现新增 2027 届相关搜索结果。
- 搜索结果不会因为只有 `网申` 就推送。
- 新公告能追溯到搜索 Provider、查询词、原始 URL 和快照。

## 8. Milestone 6：飞书推送

目标：

每天推送新增动态。

任务：

1. 接飞书 webhook。
2. 生成每日摘要。
3. 推送高价值线索。
4. 推送待确认线索数量。
5. 记录推送日志。

验收标准：

- 飞书能收到测试消息。
- 每日摘要能推送新增线索。

## 9. Milestone 7：VPS 部署

目标：

让系统在低配 VPS 上常驻。

任务：

1. 编写部署文档。
2. 创建 Python venv。
3. 配置 systemd。
4. 配置 Nginx 或 Caddy。
5. 配置 SQLite 备份。
6. 配置环境变量。

验收标准：

- VPS 上能访问看板。
- 定时任务能运行。
- 数据库可备份。

## 10. 后续阶段

### 10.1 邮箱模块

- QQ 邮箱 IMAP。
- 求职邮件筛选。
- 面试、笔试、测评、offer、拒信抽取。
- 更新任务和投递状态。

### 10.2 投递进度管理

- applications 表。
- 待投递、已投递、测评、笔试、面试、offer 状态。
- 下一步行动和提醒。

### 10.3 飞书双向助手

- 飞书自建应用。
- 消息回调。
- 自然语言查询。
- 状态更新。

### 10.4 大模型辅助

- 招聘公告结构化抽取。
- 邮件摘要。
- 每日总结。
- 低置信度判断。

## 11. 当前推荐下一步

阶段 A 数据底座和阶段 B 采集器已经完成验收。本文前面的 Milestone 1–3 属于历史 MVP 计划，
当前开发应以 `docs/codex_development_guide.md` 和 `docs/stage_c_implementation_plan.md` 为准。

下一步应执行阶段 C：

```text
招聘分类与字段提取
-> 企业别名匹配
-> 保守去重与证据归并
-> 个人匹配评分
-> 人工核验和招聘事件页面
```

先完成固定样本、幂等数据链路和数据库断言，再扩展页面与大规模采集。
