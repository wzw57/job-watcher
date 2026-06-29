# 主动搜索监控设计

## 1. 核心原则

本项目不是只监控已有企业 URL，而是主动发现面向青岛岗位的央国企 2027 届机会。

已有企业表的作用是确定优先级，不是限制搜索范围。

主动搜索覆盖四类任务：

1. 已知重点企业搜索：P0/P1 企业精确搜索。
2. 全国央国企青岛岗位搜索：发现表外央国企在青岛/山东的岗位。
3. 核心网站定向搜索：国聘、人社、国资委、高校就业网、聚合站。
4. 地点 + 岗位方向搜索：青岛 + 网络安全/信息安全/信息技术 + 2027 届。

## 2. 核心网站表

核心网站维护在：

```text
config/search_sources.csv
```

字段：

- `name`：来源名称。
- `url`：入口 URL。
- `tier`：S/A/B/C。
- `source_kind`：government、public_platform、campus、aggregator、ats。
- `scope`：覆盖范围。
- `access_method`：site_search、direct_crawl、api_search、browser_later。
- `frequency`：建议频率。
- `trust_level`：来源可信度。
- `site_query_host`：用于 `site:` 搜索。
- `notes`：备注。

第一批核心源包括：

- 中央企业招聘应届高校毕业生信息公开。
- 国务院国资委招聘栏目。
- 国聘、国聘校园、国资央企招聘平台。
- 青岛政务网就业招聘栏目。
- 青岛人社、青岛人才网。
- 即墨、西海岸等区市政务人才就业栏目。
- 高校人才网、编制啦、应届生求职网等聚合站。
- 中国海洋大学、中国石油大学华东、山东大学、青岛大学等高校就业网。
- 国家电网、中国移动、中国电信、中国铁塔等招聘系统。

## 3. 搜索任务类型

### 3.1 已知企业搜索

任务标记：

```text
known_company_2027
```

模板：

```text
{公司名} 2027届 校园招聘
{公司名} 2027届 秋招
{公司名} 2027届 提前批
{公司名} 2027届 网申
{公司名} 网络安全 2027届 校招
{集团名} 青岛 2027届 校园招聘
{集团名} 山东 青岛 2027届 校招
```

### 3.2 广域发现搜索

任务标记：

```text
broad_discovery
```

模板：

```text
青岛 国企 2027届 校园招聘
青岛 央企 2027届 秋招
央企 2027届 校园招聘 青岛
央企 山东 青岛 2027届 网络安全
网络安全 信息安全 青岛 2027届 校园招聘
数据安全 青岛 2027届 校园招聘
```

### 3.3 站点定向搜索

任务标记：

```text
site_search
```

模板：

```text
site:{host} 2027届 校园招聘
site:{host} 2027届 秋招
site:{host} 2027届 青岛
site:{host} 网络安全 2027届
```

## 4. 分类规则

搜索结果进入统一分类器：

| 分类 | 入库位置 | 规则 |
| --- | --- | --- |
| confirmed_2027_lead | `job_leads` | 已知企业 + 明确 2027 届 + 校园招聘语义 |
| external_company_lead | `discovered_companies` + `correction_candidates` | 表外企业 + 明确 2027 届 + 青岛/山东相关 |
| recruitment_portal | `sources` 或 `correction_candidates` | 招聘官网、网申系统、报名入口，但缺少明确 2027 届公告 |
| review_candidate | `correction_candidates` | 有相关信号但证据不足 |
| invalid | `correction_candidates` rejected | 旧届别、社招、弱相关噪声 |

重点边界：

- `网申`、`投递入口`、`招聘系统` 不能单独生成 `job_leads`。
- 飞书未来只推高置信 `job_leads`。
- 聚合站结果需要二次核验，不能直接视为最终事实。

## 5. CLI 命令

生成搜索任务：

```powershell
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

## 6. 当前第一版状态

已实现：

- `config/search_sources.csv`
- `search_sources` 表
- `discovered_companies` 表
- 搜索任务生成器
- 搜索任务 runner
- 搜索结果分类器
- `/search-results` 看板页面
- `/discovered-companies` 看板页面

待完善：

- 搜索 API key 配置到本机/VPS 环境变量。
- 对搜索结果页面正文做二次抓取和快照。
- 表外企业接受后自动加入 `companies`。
- 搜索任务定时器。
- 飞书只推高置信 2027 届线索。
