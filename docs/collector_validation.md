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

## 固定样本池验收

`config/collector_samples.csv` 已固定 22 个公开样本，覆盖 5 个政府入口、4 个高校就业网、
3 个国聘动态平台、3 个聚合站、3 个企业官网、3 个招聘入口和 1 个文本型 PDF。验收命令：

```bash
PYTHONPATH=src python -m job_watcher.cli validate-collector-samples --timeout 10 --strict
```

2026-07-16 最终使用 10 秒超时、3 个并发和单次尝试的严格验收结果：22/22 状态符合预期，
包含 13 个 `success`、4 个 `http_error`、1 个 `blocked`、3 个 `needs_browser` 和 1 个
`network_error`。成功样本正文
从 4 到 7408 字符不等；固定政府 PDF 提取 6196 字符、质量分 70。三个国聘入口均以
HTTP 200 返回极短 JavaScript 壳，正确识别为 `needs_browser`；中车四方所招聘 SaaS 虽为
HTTP 200，但只抽取 4 个字符、质量分 24，会进入 `content_quality` 人工核验。

同一环境使用 4 秒超时时只有 4 个成功，16 个网络超时且 6 个状态超出预期，证明严格模式
会暴露超时配置或出口网络退化，而不会把无法访问记作“无新增”。实时结果只表示该次运行，
不替代 `source_runs` 长期健康趋势。

解析器固定测试另覆盖 DOCX、XLSX、图片附件发现、扫描 PDF `ocr_required`、图片公告
`ocr_required` 和旧 DOC/XLS `legacy_office_conversion_required`。二进制原文件按哈希保留，
OCR 和旧格式转换作为可选外部处理能力，不在基础采集进程中静默执行。
