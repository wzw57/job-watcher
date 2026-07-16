# 阶段 C：招聘事件解析、归并与个人匹配实施计划

## 1. 目标

阶段 C 把已经采集并保留证据的 `raw_items` 转化为用户可用的招聘事件和岗位：

```text
raw_items
  -> 招聘分类
  -> 字段提取
  -> 企业识别
  -> 候选事件检索与保守归并
  -> job_events + job_positions
  -> 个人匹配评分
  -> 人工核验或今日雷达
```

本阶段不是重新设计采集器，也不得继续依赖旧版 `job_leads` 作为事实中心。所有事件必须能
通过一个或多个 `raw_items.job_event_id` 追溯到原始 URL、正文、附件和来源。

## 2. 范围与非目标

本阶段必须完成：

1. 招聘内容分类与拒绝原因；
2. 招聘事件字段提取；
3. 岗位列表拆分；
4. 企业标准名和别名匹配；
5. 同一公告跨来源去重与证据保留；
6. 低置信度人工核验；
7. 个人匹配分、等级和可解释理由；
8. 幂等 CLI、仓储函数、固定样本和数据库断言；
9. 招聘事件页展示全部证据来源和归并状态。

本阶段不承诺：

- 使用大模型作为主流程依赖；
- 自动绕过登录、验证码或访问限制；
- 微信公众号完全自动抓取；
- 自动 OCR 或旧 Office 转换服务；
- 完成覆盖中心、每日简报或生产部署。

## 3. 输入资格与安全门槛

默认只处理同时满足以下条件的原始记录：

- `crawl_status = 'success'`；
- `parse_status = 'parsed'`；
- `merge_status = 'unprocessed'`；
- 正文非空且质量分不低于采集配置阈值；
- 存在 `source_id` 或 `search_task_id`，能够追溯来源。

以下情况不得直接创建正式招聘事件：

- 只有“招聘官网、加入我们、人才招聘”等入口词，没有具体批次、公告或岗位证据；
- 搜索摘要、社区讨论或转载标题尚未取得可核实正文；
- 企业、届别、地点或用工关系存在关键歧义；
- 正文质量过低、附件需要 OCR、旧 Office 尚未转换；
- 疑似劳务派遣但无法确认用工主体；
- 归并分处于人工核验区间。

这些记录应设置为 `needs_review`，并创建幂等 `review_tasks`，不得静默丢弃。

阶段 C 应统一补充并使用 `merge_status` 常量，至少包括 `unprocessed`、`linked`、
`not_recruitment`、`needs_review` 和 `possible_duplicate`，避免在解析器、仓储和页面中散落字符串。

## 4. 解析契约

建议新增 `parsers/recruitment.py`，输出纯数据对象，不直接写数据库。至少包含：

- `is_recruitment`、`classification_confidence`、`classification_reasons`；
- `title`、`recruitment_type`、`cohorts`；
- `publisher_name`、`employer_name`、`contract_name`；
- `published_at`、`deadline_at`、`application_url`；
- `locations`、`qingdao_level`；
- `degree_requirements`、`major_requirements`、`political_requirement`；
- `employment_type`、`headcount`；
- `positions`；
- 每个关键字段的证据片段或提取理由；
- `warnings` 和整体置信度。

日期必须保留原始文本并输出标准化值。无法确定年份、地点或主体时保持未知，不得根据当前日期
强行猜测。规则解析是稳定主路径；未来的大模型只能作为可关闭、可审计的辅助 Provider。

## 5. 招聘分类规则

第一版优先使用可测试的确定性规则，至少区分：

- `campus`：校园招聘、应届生、届别、校招；
- `social`：社会招聘、有工作经验要求；
- `internship`：实习、暑期实习；
- `public_exam`：事业单位、公开招聘、考试录用；
- `talent_program`：人才引进、博士后、高层次人才；
- `unknown`：有招聘证据但类型不明。

单纯命中“招聘、报名、简历、网申”不得自动创建事件。至少还应存在事件级证据，例如明确届别、
公告标题、发布日期/截止日期、具体岗位、招录人数或公开招聘批次。

## 6. 企业识别

建议新增 `matching/entities.py`，匹配顺序为：

1. `source.company_id` 的已核实主体；
2. 企业标准名称精确匹配；
3. `normalized_name` 精确匹配；
4. `aliases` 中的明确别名匹配；
5. 有边界的高置信包含匹配。

不得仅因集团名称相同就把子公司公告合并到母公司。多个候选同分、发布主体与用工主体不同、
分公司/子公司关系不明确时，创建 `entity_match` 核验任务。

## 7. 归并规则

`raw_items` 始终保留多条；同一招聘只生成一个 `job_events`。建议评分：

| 维度 | 分值 |
|---|---:|
| 招聘主体一致 | 25 |
| 规范化标题/批次相似 | 20 |
| 届别一致 | 15 |
| 发布时间接近 | 10 |
| 截止时间一致 | 10 |
| 报名 URL 一致 | 10 |
| 岗位集合相似 | 10 |

- 85–100：自动归并；
- 60–84：创建 `possible_duplicate` 核验任务，不自动合并；
- 0–59：创建新事件。

硬性保护条件：明确属于不同子公司、不同招聘类型、不同届别或不同批次时，不得因为标题相似而
自动合并。归并后必须把所有证据 `raw_items.job_event_id` 指向同一事件。

## 8. 个人匹配

匹配以用户当前背景为默认配置，但规则必须可配置：2027 届网络空间安全硕士、青岛优先、
国企/央企/银行/事业单位/外企优先，岗位采用宽口径。

评分至少考虑：

- 青岛/山东/全国分配关系；
- 是否接收 2027 届和硕士；
- 网络空间安全、计算机、电子信息等专业范围；
- 安全、信息化、运维、科技风险、数字化、项目管理、合规、技术支持、售前等方向；
- 企业优先级、用工性质、政治面貌/户籍/经验限制；
- 截止日期紧迫度和条件不明项。

输出 `match_score`、`match_level` 和 `match_reasons_json`。不符合单一条件不能直接删除；明确
硬门槛不符才可标记 `mismatch`，其余使用 `pending` 或 `possible`。

## 9. 推荐模块和 CLI

```text
src/job_watcher/
├── parsers/recruitment.py
├── matching/entities.py
├── matching/deduplication.py
├── matching/personal.py
├── processing/recruitment.py
└── storage/repositories.py
```

新增命令建议：

```bash
PYTHONPATH=src python -m job_watcher.cli parse-recruitment-items --limit 100 --dry-run
PYTHONPATH=src python -m job_watcher.cli parse-recruitment-items --limit 100
PYTHONPATH=src python -m job_watcher.cli parse-recruitment-items --raw-item-id 123
```

命令必须输出：扫描数、非招聘数、新事件数、自动归并数、岗位数、待核验数、跳过数和错误数。
重复运行不能新增重复事件、岗位或核验任务。

## 10. 固定样本与测试

提交至少 12 个脱敏、短文本固定样本，覆盖：

1. 企业官方校招公告；
2. 政府公开招聘；
3. 高校就业网转载同一公告；
4. PDF 正文；
5. XLSX 多岗位；
6. 招聘官网入口但没有具体公告；
7. 社招与校招区分；
8. 届别/地点不明；
9. 同一公告三个来源；
10. 标题相似但不同子公司；
11. 劳务派遣或合同主体不明；
12. 网络安全以外但适合用户的宽口径岗位。

测试必须断言：

- 三个转载只生成一个事件，但保留三个 `raw_items`；
- 不同子公司不误合并；
- 多岗位能拆分且重复运行数量不变；
- 非招聘入口不生成事件；
- 低置信度进入核验；
- 每个事件至少有一条原始证据；
- 外键检查无违规；
- 旧表和既有 500/705 数据不减少。

## 11. 实施顺序

1. 先补状态常量、解析数据对象和固定样本；
2. 实现招聘分类、字段和岗位提取；
3. 实现企业识别与核验任务；
4. 实现事件仓储、幂等处理命令和证据关联；
5. 实现保守去重；
6. 实现个人匹配；
7. 更新招聘事件页面，展示全部来源、岗位、匹配理由和待核验状态；
8. 跑完整测试、真实种子校验和固定样本数据库验收；
9. 更新本文档、开发基线和草稿 PR 说明。

不得先做漂亮页面再补数据链路；不得为了让测试通过而放宽到“见到招聘二字就创建事件”。

## 12. 完成标准

阶段 C 完成必须同时满足：

- `raw_items -> job_events -> job_positions` 可追溯链路在新数据上成立；
- 同一公告多来源归并、不同子公司隔离均有测试；
- 解析、企业匹配、归并和个人匹配均输出可解释理由；
- 所有自动决策都有置信度或规则依据；
- 所有不确定情况进入人工核验；
- 命令幂等，外键无违规，旧数据不丢失；
- 测试、编译检查、`seed-data-doctor` 和 `git diff --check` 通过。
