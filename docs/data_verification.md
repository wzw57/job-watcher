# 企业数据核实与修正规则

本文档定义项目在正式抓取前如何处理 `青岛国企.xlsx` 中不确定、不完整或错误的数据。

## 1. 核心原则

原始表格是候选数据，不是最终事实来源。项目必须尽量把错误数据修正为可信数据，而不是仅仅标记错误后放弃。

处理原则：

1. 不覆盖原始 Excel。
2. 所有修正写入项目主数据表。
3. 保留原始值、修正值、修正来源和修正时间。
4. 对低置信度修正保留人工确认状态。
5. 对明显错误 URL，应尽量检索正确官网或招聘入口。
6. 对企业名称、集团归属、国企属性等关键字段，应给出可追溯来源。

## 2. 数据状态

企业和来源都需要区分“候选、已修正、已确认”。

企业核实状态：

- `candidate`：来自原始表，结构完整但事实未核实。
- `verified`：企业名称、归属、官网或权威来源已核实。
- `corrected`：原始数据存在错误，已根据检索结果修正。
- `needs_review`：自动修正不确定，需要人工确认。
- `out_of_scope`：不符合项目范围，例如不在青岛相关、不属于国企/央企相关、不适合目标岗位方向。

来源核实状态：

- `candidate`：原表或搜索发现的候选 URL。
- `verified_official`：已确认是官网或官方招聘入口。
- `verified_government`：已确认是政府、人社、国资、公共人才平台。
- `verified_platform`：已确认是国聘、前程无忧、智联等招聘平台入口。
- `corrected`：原 URL 错误或过期，已找到替代 URL。
- `needs_browser`：需要浏览器渲染或手工打开核实。
- `needs_search`：当前 URL 不可用或信息不足，需要搜索补全。
- `invalid_replaced`：原 URL 无效，已有替代来源。
- `invalid_unresolved`：原 URL 无效，检索后仍未找到可靠替代。

## 3. 修正优先级

第一轮只处理高价值范围：

1. `P0 必看`
2. `P1 优先`
3. 表格中推荐方向含网络安全、信息安全、软件、信息技术、数字化、信息化的企业
4. 青岛本地平台、央企山东/青岛分支、区属国企平台

后续再逐步扩展到 P2/P3/P4。

## 4. URL 修正流程

对每条候选 URL：

```text
候选 URL
  -> HTTP 可访问性检测
  -> 页面标题/正文提取
  -> 判断是否与企业相关
  -> 判断是否招聘相关
  -> 若无效或不相关，触发搜索修正
  -> 找到更可信 URL 后写入 corrected_url
  -> 保留 original_url 和 correction_source
```

当前已落地脚本：

- `scripts/verify_sources.py`：对候选 URL 做可限量、可恢复的核验，输出 `data/audit/source_verification_results.csv` 和 `data/audit/source_verification_summary.md`。
- `scripts/build_correction_queue.py`：根据核验结果生成修正队列，输出 `data/audit/source_correction_queue.csv`。
- `scripts/build_search_tasks.py`：根据修正队列生成搜索任务，输出 `data/audit/search_tasks.csv`。
- `scripts/build_correction_candidates.py`：读取人工或 API 搜索结果并打分，输出 `data/audit/correction_candidates.csv`。

推荐执行顺序：

```text
python scripts/audit_company_data.py --max-urls 0
python scripts/verify_sources.py --priority P0 P1 --max 50 --max-time 8 --resume
python scripts/build_correction_queue.py
python scripts/build_search_tasks.py --max-companies 50 --queries-per-company 4 --providers bing zhihu
```

说明：URL 核验结果中的 `timeout` 不等于 URL 错误。国内站点、JS 站点、反爬站点或网络不稳定都可能导致超时。所有 `timeout/error/blocked/not_found` 记录都应优先进入检索修正流程。

搜索修正关键词：

```text
{公司名} 官网
{公司名} 招聘
{公司名} 校园招聘
{公司名} 2027届 校园招聘
{公司名} 网申
{公司名} 国聘
{公司名} 前程无忧 校园招聘
{公司名} 智联 校园招聘
{公司名} 青岛 招聘
```

如果公司名搜索结果质量差，再加入集团名：

```text
{归属集团} {主体公司} 招聘
{归属集团} 青岛 校园招聘
```

## 5. 企业属性修正流程

对企业名称、集团归属、国企属性进行核实时，优先使用以下来源：

1. 企业官网“关于我们”。
2. 集团有限公司官网组织架构、成员单位、分支机构页面。
3. 政府、国资委、人社、公共人才平台公告。
4. 国家企业信用信息公示系统。
5. 上市公司公告、年报、公开披露。
6. 高校就业网或招聘平台，仅作辅助来源。

字段修正规则：

- 原始企业名称保留为 `original_company_name`。
- 修正企业名称写入 `company_name`。
- 常见简称写入 `aliases`。
- 原始集团归属保留为 `original_group_name`。
- 修正集团归属写入 `group_name`。
- 国企属性写入 `ownership_type`。
- 修正证据写入 `verification_evidence_url`。

## 6. 招聘入口发现流程

招聘入口经常不在官网，因此修正时不仅找官网，还要找招聘入口。

优先级：

1. 企业官网招聘页。
2. 集团统一招聘平台。
3. 官方跳转的第三方招聘专题。
4. 国聘专题或职位页。
5. 政府、人社、国资、人才平台公告。
6. 高校就业网转载。
7. 商业招聘平台专题。

对找到的招聘入口，新增 source，而不是只替换原 URL。

建议字段：

- `original_url`
- `corrected_url`
- `source_type`
- `trust_level`
- `correction_method`：http_check、search_api、manual_search、browser_check、llm_assist
- `correction_query`
- `evidence_title`
- `evidence_snippet`
- `evidence_url`
- `verified_at`
- `review_status`

## 7. 搜索 Provider

项目应支持多个搜索 Provider，避免依赖单一入口。

第一阶段可支持：

- 手动搜索结果导入
- 通用网页搜索 API，后续选择 Bing、Brave 或 SerpAPI
- 知乎 global_search API，用于中文线索、经验帖、面经和讨论补充
- 百度搜索 API，用于低成本中文网页搜索和官网/招聘入口发现
- 博查 Web Search API，用于结构化网页搜索，作为高质量备用源

知乎搜索适合做补充线索，不适合作为企业官网和招聘入口的最终依据。

### 7.0 知乎 global_search Provider

当前已落地脚本：

- `src/job_watcher/search/zhihu_provider.py`
- `scripts/run_zhihu_search_tasks.py`

知乎全网搜索 API 信息：

- HTTP URL：`https://developer.zhihu.com/api/v1/content/global_search`
- Method：`GET`
- Header：
  - `Authorization: Bearer <your_access_secret>`
  - `X-Request-Timestamp: 秒级 Unix 时间戳`
  - `Content-Type: application/json`
- Query：
  - `Query`
  - `Count`
  - `Filter`
  - `SearchDB`

响应解析：

- `Data.Items[].Title`
- `Data.Items[].ContentText`
- `Data.Items[].Url`
- `Data.Items[].AuthorityLevel`

安全要求：

- API key 不写入代码、文档、CSV 或配置文件。
- 本地运行时只通过环境变量传入：

```powershell
$env:ZHIHU_API_KEY="your_access_secret"
```

运行示例：

```powershell
$env:ZHIHU_RESOLVE_IP="43.159.108.169"  # 可选：仅在本机 TUN/DNS 解析 developer.zhihu.com 失败时使用
python scripts/run_zhihu_search_tasks.py --max-tasks 10 --count 5 --search-db all --resume
python scripts/build_correction_candidates.py --input data/manual_search_results.csv
```

说明：当前本机 TUN 模式下 `developer.zhihu.com` 可能 DNS 超时。Provider 已支持通过 `ZHIHU_RESOLVE_IP` 临时指定解析 IP，底层使用 curl 的 `--resolve` 绕过系统 DNS。该 IP 可能随时间变化，若失效可通过可用网络或 DoH 重新查询。

### 7.1 搜索任务表

搜索任务由 `data/audit/search_tasks.csv` 管理。字段包括：

- `task_id`
- `company_key`
- `company_name`
- `priority`
- `original_url`
- `recommended_action`
- `reason`
- `query`
- `provider`
- `search_url`
- `status`

第一版可以人工打开 `search_url`，也可以后续由 API Provider 自动执行。

### 7.1.1 百度搜索 Provider

当前已落地脚本：

- `src/job_watcher/search/baidu_provider.py`
- `scripts/run_baidu_search_tasks.py`

环境变量：

```powershell
$env:BAIDU_SEARCH_API_KEY="your_baidu_search_key"
$env:BAIDU_RESOLVE_IP="45.113.194.71"  # 可选：仅在本机 TUN/DNS 解析 qianfan.baidubce.com 失败时使用
```

运行示例：

```powershell
python scripts/run_baidu_search_tasks.py --query "青岛 国企 2027届 校园招聘 网络安全" --count 5
```

当前验证结果：

- 百度 API 已在本机跑通。
- 本机 TUN 模式下 `qianfan.baidubce.com` 可能 DNS 超时，已支持 `BAIDU_RESOLVE_IP` 绕过系统 DNS。
- 百度结果偏中文网页和招聘平台，适合低成本搜索，但仍需要评分和人工确认。

### 7.1.2 博查 Web Search Provider

当前已落地脚本：

- `src/job_watcher/search/bocha_provider.py`
- `scripts/run_bocha_search_tasks.py`

环境变量：

```powershell
$env:BOCHA_API_KEY="your_bocha_api_key"
```

运行示例：

```powershell
python scripts/run_bocha_search_tasks.py --query "青岛 国企 2027届 校园招聘 网络安全" --count 5
```

当前验证结果：

- 博查接口可以连通。
- 当前 key 返回 `You do not have enough money or package quota`，说明该账号暂无可用余额或套餐额度。
- 因此博查先保留为备用 Provider，等额度可用后再跑批量任务。

### 7.2 搜索结果导入格式

搜索结果统一导入到：

```text
data/manual_search_results.csv
```

字段格式参考：

```text
data/manual_search_results.example.csv
```

必需字段：

- `task_id`
- `company_key`
- `company_name`
- `query`
- `provider`
- `rank`
- `title`
- `url`
- `snippet`

导入后执行：

```text
python scripts/build_correction_candidates.py --input data/manual_search_results.csv
```

脚本会输出：

```text
data/audit/correction_candidates.csv
```

该文件用于人工确认哪些候选 URL 可以作为 corrected_url 或新增 source。

### 7.3 人工复核表

执行：

```powershell
python scripts/build_review_sheet.py
```

输出：

```text
data/audit/source_review_sheet.csv
```

该表是给人工确认或后续 Web 看板使用的轻量视图，包含候选 URL、候选分数、来源类型、命中原因和人工确认字段。

当前经验：

- 知乎 `global_search` 可以补充线索，尤其能找到高校就业网转载、聚合招聘页和经验帖。
- 但搜索结果摘要可能包含查询词，不能只凭摘要判断候选有效。
- 官网/招聘入口修正需要更重视标题、域名和来源类型。
- 对官网修正，后续仍建议接入 Bing/Brave/SerpAPI 这类通用网页搜索 Provider。

## 8. 自动修正与人工确认

自动修正可以分级：

- 高置信：官方域名、标题匹配公司名、页面含招聘或关于我们信息，可自动采用。
- 中置信：政府/高校/国聘来源，进入人工确认。
- 低置信：商业聚合、论坛、社交内容，只作为候选线索。

自动采用也必须保留审计记录，避免后续误修正无法追溯。

## 9. 第一轮验收标准

对 P0/P1 企业，第一轮数据核实应尽量达到：

1. 每家企业至少有一个可信官网或权威来源。
2. 有招聘入口则记录招聘入口。
3. 原 URL 错误时尽量给出 corrected_url。
4. 无法自动修正时，给出检索关键词和待人工确认原因。
5. 所有修正都有 evidence_url 或 correction_query。

## 10. 当前阶段产物

- `data/processed/companies_seed.csv`：结构清洗后的企业种子表。
- `data/processed/company_sources_seed.csv`：从原表拆分出的候选 URL 来源。
- `data/audit/company_data_audit.md`：企业表结构审计报告。
- `data/audit/source_verification_results.csv`：URL 核验结果。
- `data/audit/source_verification_summary.md`：URL 核验摘要。
- `data/audit/source_correction_queue.csv`：待搜索修正队列。
- `data/audit/search_tasks.csv`：待执行搜索任务。
- `data/audit/correction_candidates.csv`：正式搜索结果打分后的修正候选。
- `data/audit/source_review_sheet.csv`：人工复核用候选表。
- `data/manual_search_results.example.csv`：人工搜索结果导入模板。
- `config/sources.yaml`：第一批固定公共信息源配置。
