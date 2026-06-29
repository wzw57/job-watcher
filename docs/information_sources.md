# 信息来源清单与接入策略

本文档用于整理青岛国企/央企 2027 秋招信息助手的外部信息源。目标不是一次性爬完全网，而是建立一个可分级、可维护、可复核的信息源地图。

## 1. 核心判断

很多企业招聘入口不在企业官网正文页面，而是在独立招聘系统或第三方合作平台上，例如国聘、前程无忧专题、智联专题、Hotjob、chinasyks 报名系统等。因此项目不能只做“官网 URL 定时抓取”，必须同时做：

1. 固定来源监控。
2. 企业级招聘入口发现。
3. 搜索 API/搜索引擎补漏。
4. 聚合招聘网站线索抓取。
5. 人工确认和来源可信度分级。

搜索不是最终依据，但搜索是发现隐藏招聘入口的必要能力。

## 2. 来源分层

### S0 企业表已有 URL

来源文件：

- `data/processed/company_sources_seed.csv`

当前规模：

- URL 来源记录：690 条
- 不同域名：265 个

这些来源是第一批监控种子，优先级由企业本身的 P0/P1/P2/P3 决定。

当前表格里出现较多的域名包括：

- `www.qdgsjt.com`
- `www.bianzhia.com`
- `www.gaoxiaojob.com`
- `qzpta39.chinasyks.org.cn`
- `www.qdjqt.com`
- `rczp.china-railway.com.cn`
- `www.iguopin.com`
- `zhaopin.sgcc.com.cn`
- `zhaopin.chinatowercom.cn`
- `campus.51job.com`
- `jobcareer.sdu.edu.cn`

接入策略：

- 优先导入为 `sources` 表。
- P0/P1 企业默认启用。
- URL 可访问性检测做成独立队列。
- 同一企业多个 URL 保留，不提前合并。

### S1 官方招聘入口

这类来源可信度最高，但入口经常是独立系统。

典型入口：

| 来源 | URL | 说明 | 接入策略 |
| --- | --- | --- | --- |
| 国家电网招聘平台 | https://zhaopin.sgcc.com.cn/sgcchr/static/home.html | 国网公告、网申、录用公示等 | 固定源监控，可能需要解析 JS/API |
| 中国移动招聘网站 | https://job.10086.cn/ | 中国移动集团招聘入口 | 固定源监控，关注山东/青岛岗位 |
| 中国联通官网校园招聘页 | https://www.chinaunicom.com.cn/46/menu01/528/column06 | 联通官网发布校招入口，可能跳转智联/国聘 | 固定源监控 + 跟踪外链 |
| 中国联通国聘专区 | https://zglt.iguopin.com/ | 联通校招合作专区 | JS 站点，先作为发现源 |
| 中国联通智联专区 | https://zglt.zhaopin.com/ | 联通校招合作专区 | 线索源，必要时浏览器抓取 |
| 中国电信招聘官网 | https://job.chinatelecom.com.cn/wt/TELE/web/index | 电信自建招聘系统 | 固定源监控，可能需要动态抓取 |
| 中国电信集团招聘页 | https://www.chinatelecom.com.cn/zp/ | 集团官网招聘公告页 | HTML 优先抓取 |

接入策略：

- 对表中 P0/P1 央企及驻青岛单位建立专门 source。
- 官方网站页面抓取频率高于搜索频率。
- 对跳转到第三方系统的入口，记录 `parent_source_id` 和 `final_url`。

### S2 国聘与国资央企平台

国聘是央企、国企和重点企业招聘的重要聚合平台。

典型入口：

| 来源 | URL | 说明 | 接入策略 |
| --- | --- | --- | --- |
| 国聘官网 | https://www.iguopin.com/ | 综合招聘平台 | JS 站点，优先作为搜索/浏览器源 |
| 国聘职位页 | https://www.iguopin.com/job | 职位检索入口 | 需要研究请求接口或低频浏览器抓取 |
| 国聘校园招聘 | https://xiaoyuan.iguopin.com/ | 校招入口 | JS 站点，适合专题发现 |
| 国资央企招聘平台 | https://cujiuye.iguopin.com/ | 国资央企促就业相关平台 | 重点监控专题、岗位 |

接入策略：

- 第一版不强行破解复杂接口。
- 先把国聘作为高价值搜索源和浏览器源。
- 关键词重点使用：青岛、山东、网络安全、信息安全、软件、信息技术、2027届、校园招聘。

### S3 青岛政府、人社、人才和国资相关来源

这类来源对青岛本地国企尤其重要。

典型入口：

| 来源 | URL | 说明 | 接入策略 |
| --- | --- | --- | --- |
| 青岛市人力资源和社会保障局 | https://hrss.qingdao.gov.cn/ | 人社资讯、就业创业、求职招聘入口 | HTML 监控 + 链接发现 |
| 青岛人社网上办事大厅 | https://hrsswb.qingdao.gov.cn/ | 求职招聘等办事入口 | 可访问性需单独检测 |
| 青岛人才网 | https://rc.qingdao.gov.cn/ | 人才服务入口 | 重点发现招聘、人才活动 |
| 青岛政务网就业招聘栏目 | https://www.qingdao.gov.cn/zfwf/zdlyzl/jiuyefw/jyaz/jyzp/ | 就业招聘、国有企业岗位等 | 栏目页监控 |
| 青岛政务网 | https://www.qingdao.gov.cn/ | 市政府综合信息入口 | 站内搜索和栏目监控 |

接入策略：

- 这些来源作为青岛本地高可信来源。
- 优先监控“就业招聘”“国有企业岗位”“公告”“公示”“动态”等栏目。
- 如果页面存在重定向或访问不稳定，保存搜索结果和入口页。

### S4 青岛区市和功能区来源

区属国企招聘常常发布在区市政务网、报名系统、人才平台或高校转载页。

典型入口：

| 来源 | URL | 说明 | 接入策略 |
| --- | --- | --- | --- |
| 即墨政务网国企招聘 | https://www.jimo.gov.cn/zwzt/jycy/zpxx/yqzp/ | 即墨区属国企招聘栏目 | 固定栏目监控 |
| 西海岸新区政务网 | https://www.xihaian.gov.cn/ | 西海岸招聘、引才、考试公告 | 站内栏目和搜索监控 |
| 西海岸区属国企报名系统示例 | https://url.jiuyejie.cn/xha/gqzp.php | 区属国企招聘报名入口示例 | 线索记录，不作为长期固定入口 |
| chinasyks 西海岸报名系统 | https://qzpta39.chinasyks.org.cn/ | 多次出现在区属国企报名中 | 监控具体专题入口 |
| 青岛高新区人才招聘服务平台 | https://qdgxqrc.51job.com/ | 高新区与前程无忧合作平台 | 低频监控，注意平台限制 |

接入策略：

- 区属国企入口变化快，固定域名和搜索发现都要做。
- 对报名系统保留历史入口，用于发现同域新专题。
- 对高校转载的区属国企公告，也要反向抽取官方报名入口。

### S5 高校就业网

高校就业网适合作为线索发现源，尤其能发现宣讲会、专场招聘和被官网隐藏的网申入口。

重点监控高校：

| 学校 | URL | 说明 | 接入策略 |
| --- | --- | --- | --- |
| 中国海洋大学就业中心 | https://career.ouc.edu.cn/ | 校园招聘、宣讲会、招聘会 | HTML/列表监控 |
| 中国海洋大学就业服务平台 | https://school.gxjy.sdei.edu.cn/ouc/front/NoticeListByParentId?deptId=5 | 招聘信息/通知公告入口 | 列表监控 |
| 中国石油大学（华东）学生就业信息网 | https://career.upc.edu.cn/ | 青岛/黄岛重要高校就业源 | 列表监控 |
| 山东大学就业网 | https://www.job.sdu.edu.cn/ | 山东重点高校，就业公告较多 | 列表监控 |
| 青岛大学学生就业中心 | https://job.qdu.edu.cn/ | 青岛本地高校就业源 | 列表监控 |
| 山东科技大学就业相关入口 | https://www.sdust.edu.cn/ | 需进一步定位就业信息栏目 | 站内发现 |
| 青岛科技大学就业/学院就业信息 | https://gfz.qust.edu.cn/ | 已出现西海岸国企招聘转载 | 线索源 |
| 哈工大就业网 | https://career.hit.edu.cn/ | 央企/地方引才转载多 | 线索源 |

接入策略：

- 不把高校就业网作为最终可信源。
- 高校线索入库状态默认为 `pending_review`。
- 自动提取正文中的官方报名入口。
- 同一公告被多校转载时按标题、公司、报名链接去重。

### S6 商业招聘和聚合平台

这些来源覆盖广，但可靠性和稳定性不如官方/政府/高校来源。

典型入口：

| 来源 | URL | 说明 | 接入策略 |
| --- | --- | --- | --- |
| 前程无忧校园招聘专题 | https://campus.51job.com/ | 很多央企/国企使用专题页 | 只抓专题或搜索结果 |
| 智联校园招聘 | https://xiaoyuan.zhaopin.com/ | 联通等央企可能使用智联专题 | 线索源 |
| 猎聘校园 | https://campus.liepin.com/ | 校招聚合 | 线索源 |
| 应届生求职网青岛频道 | https://www.yingjiesheng.com/qingdaojob/index.html | 青岛应届生招聘聚合 | 线索源 |
| 高校人才网青岛国企 | https://www.gaoxiaojob.com/rczhaopin/qingdao/guoqi_benke | 青岛国企公告聚合 | 线索源 |
| 编制啦青岛国企 | https://www.bianzhia.com/zt/gqqingdao/ | 青岛国企公告聚合 | 线索源 |

接入策略：

- 只作为线索发现，不直接确认。
- 抓标题、发布日期、原文链接、报名链接。
- 对商业平台结果降低默认可信度。
- 重点抽取指向官网、政府、国聘或报名系统的链接。

### S7 搜索 API 和搜索引擎

搜索用于发现隐藏入口，尤其是：

- 公司官网没有招聘栏目。
- 招聘入口在第三方专题页。
- 高校就业网转载包含报名链接。
- 政府公告栏目层级较深。
- 新专题 URL 没有被原表收录。

候选搜索 Provider：

| Provider | 作用 | 优先级 |
| --- | --- | --- |
| 知乎 global_search API | 中文讨论、经验帖、补充线索、面经、公司评价 | 中 |
| Bing Web Search / Brave Search / SerpAPI | 通用网页搜索，找官网、招聘入口、公告转载 | 高 |
| 站点内搜索 | 对政府、高校、聚合站做定向搜索 | 高 |
| 手动搜索导入 | 人工发现的结果直接入库 | 高 |

搜索关键词模板：

```text
{公司名} 2027届 校园招聘
{公司名} 2027 秋招
{公司名} 校园招聘 青岛
{公司名} 信息安全 招聘
{公司名} 网络安全 招聘
{公司名} 招聘 官网
{公司名} 网申
青岛 国企 2027届 校园招聘
青岛 央企 网络安全 校招
site:job.qdu.edu.cn 青岛 国企 校园招聘
site:career.ouc.edu.cn 青岛 国企 招聘
site:qingdao.gov.cn 国有企业岗位 招聘
site:iguopin.com 青岛 网络安全
```

接入策略：

- 搜索结果全部进入 `job_leads`，默认 `pending_review`。
- 搜索结果可信度低于官方/政府/高校固定源。
- 只有指向高可信域名或人工确认后，才转为 `job_posts`。

## 3. 招聘入口发现流程

对每家公司执行：

```text
公司名
  -> 使用原表 URL
  -> 抓取页面外链
  -> 搜索 “公司名 + 校园招聘/2027届/网申”
  -> 发现招聘入口或专题页
  -> 判断来源类型和可信度
  -> 入库为 source 或 job_lead
  -> 需要人工确认时进入看板
```

发现入口时优先级：

1. 企业官网/集团官网招聘页。
2. 企业官方招聘系统。
3. 国聘/央企招聘专题。
4. 政府/人社/国资/人才平台。
5. 高校就业网转载。
6. 商业招聘专题。
7. 普通聚合/论坛/社交内容。

## 4. 数据库字段建议补充

`sources` 表建议增加：

- `provider`：manual、excel_seed、official_site、iguopin、government、campus、search_api、commercial_platform
- `parent_source_id`：从哪个页面发现该入口
- `discovered_by`：excel、crawler、search、manual、llm
- `discovered_at`
- `last_verified_at`
- `verification_status`：unknown、ok、blocked、timeout、invalid、needs_browser
- `requires_browser`：是否需要浏览器渲染
- `trust_level`：0-100

`job_leads` 表建议增加：

- `search_query`
- `search_provider`
- `matched_source_domain`
- `original_platform`
- `application_platform`

## 5. 第一版实现建议

第一版不要追求“完整抓取所有平台”，而是先实现信息源管理能力：

1. 导入原表 690 条 URL。
2. 手动维护一批固定公共源。
3. 支持在看板中新增/禁用 source。
4. 对 source 做轻量抓取和快照。
5. 对 JS 站点标记 `requires_browser=true`。
6. 对搜索结果生成待确认线索。

第一批固定源建议：

- 青岛市人社局
- 青岛政务网就业招聘
- 青岛人才网
- 国聘官网
- 国聘校园招聘
- 国资央企招聘平台
- 即墨政务网国企招聘
- 西海岸新区政务网
- 中国海洋大学就业中心
- 中国石油大学（华东）就业网
- 山东大学就业网
- 青岛大学就业中心
- 应届生求职网青岛频道
- 高校人才网青岛国企
- 编制啦青岛国企

## 6. 风险和注意事项

1. 很多平台是 JS 应用，普通 requests 只能拿到空壳页面。
2. 商业招聘平台反爬和条款限制较多，第一版只做低频线索抓取。
3. 海外 VPS 访问国内网站可能更慢或被拦截，URL 检测结果要保留 `blocked/timeout` 状态。
4. 同一公告会在官网、国聘、高校就业网和聚合站重复出现，必须做去重。
5. 搜索 API 会产生噪声，不能直接推送所有搜索结果。

