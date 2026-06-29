# VPS 部署记录

## 1. 当前 VPS

- 系统：Rocky Linux 9.6
- 项目目录：`/opt/job-watcher`
- Python：`python3.12`
- 虚拟环境：`/opt/job-watcher/.venv`
- 数据库：`/opt/job-watcher/data/job_watcher.db`
- 快照目录：`/opt/job-watcher/data/snapshots`

## 2. 代码同步

代码通过 GitHub 中转：

```bash
cd /opt/job-watcher
git pull --ff-only
```

本地私有数据不进入 GitHub，包括：

- 原始 Excel
- SQLite 数据库
- audit/processed 中间数据
- 搜索结果和快照
- API key 和 webhook

数据库使用 SSH 单独同步：

```powershell
scp -i C:\Users\12989\.ssh\id_ed25519 E:\job_watcher\data\job_watcher.db root@97.64.27.86:/opt/job-watcher/data/job_watcher.db
```

## 3. 已安装依赖

```bash
dnf install -y python3.12 python3.12-pip
cd /opt/job-watcher
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
```

当前项目第一版主要使用 Python 标准库，不依赖重型运行时。

## 4. 常用命令

```bash
cd /opt/job-watcher
. .venv/bin/activate
PYTHONPATH=/opt/job-watcher/src python -m job_watcher.cli config-check
PYTHONPATH=/opt/job-watcher/src python -m job_watcher.cli coverage
PYTHONPATH=/opt/job-watcher/src python -m job_watcher.cli crawl-once --limit 5 --timeout 8
```

## 5. systemd 服务

Web 看板：

```text
/etc/systemd/system/job-watcher-web.service
```

状态：

```bash
systemctl status job-watcher-web.service
```

每日抓取 timer：

```text
/etc/systemd/system/job-watcher-crawl.timer
/etc/systemd/system/job-watcher-crawl.service
```

状态：

```bash
systemctl list-timers job-watcher-crawl.timer
systemctl status job-watcher-crawl.service
```

手动运行每日抓取：

```bash
systemctl start job-watcher-crawl.service
```

## 6. 访问看板

VPS Web 服务只监听 `127.0.0.1:8000`，不直接暴露公网。

从本机使用 SSH 隧道访问：

```powershell
ssh -i C:\Users\12989\.ssh\id_ed25519 -L 18000:127.0.0.1:8000 root@97.64.27.86
```

然后打开：

```text
http://127.0.0.1:18000/companies
http://127.0.0.1:18000/coverage
http://127.0.0.1:18000/leads
```

## 7. 当前验证结果

VPS 首轮抓取：

- checked：5
- fetched：5
- snapshots_inserted：5
- leads_inserted：2
- errors：0

本地关闭 TUN 后首轮抓取：

- checked：5
- fetched：5
- snapshots_inserted：5
- leads_inserted：2
- errors：0

当前新增线索主要来自中国铁塔网申系统，命中关键词为 `网申`。

## 8. 下一步

1. 增加线索状态修改能力。
2. 增加抓取失败分类和 `requires_browser` 自动标记。
3. 接入飞书 webhook，推送每日新增线索。
4. 增加数据库备份 timer。
