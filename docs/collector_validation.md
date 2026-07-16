# Collector 实际页面验证记录

验证时间：2026-07-16。该记录用于区分采集器能力、站点自身状态和当前运行环境网络限制。

| 类型 | URL | 结果 | HTTP | 正文字符 | 结论 |
|---|---|---:|---:|---:|---|
| 青岛人社政府站 | `https://hrss.qingdao.gov.cn/` | success | 200 | 2301 | 静态正文可提取 |
| 央企区域官网 | `https://sd.ccic.com/` | success | 200 | 4511 | 静态正文可提取 |
| 央企官网 | `https://www.china-tower.com/` | success | 200 | 2852 | 静态正文可提取 |
| 招聘平台 | `https://www.iguopin.com/` | needs_browser | 200 | 2 | 正确识别 JavaScript 页面 |
| 青岛政府门户 | `https://www.qingdao.gov.cn/` | http_error | 502 | 97 | 当前网络链路返回 502，不应记为无新增 |
| 政府 PDF | 国家铁路局公开 PDF | success | 200 | 6196 | PDF 原文件 231637 字节，文本提取成功 |

验证使用 6–10 秒超时、单次尝试和 5–10 MiB 响应限制。上述结果不是永久站点健康结论；
生产运行应以 `source_runs` 历史、连续失败次数和人工复核共同判断。

后续阶段 B 验收仍需扩展到至少 20 个固定样本，覆盖政府列表页、公告详情页、高校就业网、
企业招聘系统、PDF、DOCX、XLSX、JavaScript 页面、403/验证码和已失效链接。
