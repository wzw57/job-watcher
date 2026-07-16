# 青岛国企种子数据 v1 质量报告

## 结论

权威输入选用 `青岛国企广义主体库_归属集团去重修复版.xlsx` 的 `主体公司` sheet。它是四个候选版本中时间最新、主体数最多且包含集团去重修复、应聘难度、学历门槛与 URL 校准字段的版本。

## 输出统计

- 企业：500 条
- 来源 URL：690 条
- 默认启用（P0/P1）：215 条
- 无可识别 URL：0 条
- 标准化名称重复组：0 组
- 优先级：{'P0': 85, 'P1': 130, 'P2': 143, 'P3': 123, 'P4': 19}
- 来源类型：{'commercial_platform': 22, 'government': 48, 'official_or_unknown': 527, 'official_recruitment': 81, 'public_platform': 12}

## 可公开性处理

- 保留：企业名称、集团归属、机构性质、区域、求职分层、岗位方向、公开 URL。
- 删除/替换：原始 `URL校准/备注` 自由文本，不进入公开种子；统一替换为不含个人信息的核验提示。
- 不纳入：`新增与筛查`、`修复记录`、旧版自由备注等过程性 sheet。
- 注意：公开 URL 不等同于已验证的官方招聘入口；系统应继续保留来源健康检查和人工核验状态。

## 版本选择说明

- `归属集团去重修复版`：500 条，作为主数据。
- `两表极简_终极补漏版`：同为 500 条但字段较少，作为生成历史参考。
- `集团展开版`：391 条，集团结构和来源谱系更丰富，但覆盖较旧；用于交叉核对。
- `预穿透合并去重版`：391 条，保留五个输入表的合并谱系；用于审计，不作为当前主表。

## 后续验收

将 `companies_seed.csv` 与 `company_sources_seed.csv` 放入仓库 `data/processed/` 后运行：

```bash
PYTHONPATH=src python -m job_watcher.cli seed-data-doctor
PYTHONPATH=src python -m job_watcher.cli import-seed
PYTHONPATH=src python -m job_watcher.cli migrate-legacy-leads
```
