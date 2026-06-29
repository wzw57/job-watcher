from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal runtime environments.
    yaml = None


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = ROOT_DIR / "config" / "settings.yaml"


@dataclass(frozen=True)
class AppConfig:
    name: str = "qingdao-job-watcher"
    timezone: str = "Asia/Shanghai"
    environment: str = "local"


@dataclass(frozen=True)
class PathConfig:
    data_dir: Path = ROOT_DIR / "data"
    database_path: Path = ROOT_DIR / "data" / "job_watcher.db"
    snapshots_dir: Path = ROOT_DIR / "data" / "snapshots"


@dataclass(frozen=True)
class DatabaseConfig:
    url: str = "sqlite:///data/job_watcher.db"


@dataclass(frozen=True)
class CrawlerConfig:
    user_agent: str = "Mozilla/5.0"
    timeout_seconds: int = 20
    max_concurrency: int = 3
    snapshot_enabled: bool = True


@dataclass(frozen=True)
class SearchProviderConfig:
    enabled: bool = False


@dataclass(frozen=True)
class SearchConfig:
    default_count: int = 5
    zhihu: SearchProviderConfig = field(default_factory=lambda: SearchProviderConfig(enabled=True))
    baidu: SearchProviderConfig = field(default_factory=lambda: SearchProviderConfig(enabled=True))
    bocha: SearchProviderConfig = field(default_factory=SearchProviderConfig)
    zhihu_api_key: str = ""
    zhihu_resolve_ip: str = ""
    baidu_api_key: str = ""
    baidu_resolve_ip: str = ""
    bocha_api_key: str = ""


@dataclass(frozen=True)
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True


@dataclass(frozen=True)
class FeishuConfig:
    enabled: bool = False
    webhook_url: str = ""


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    app: AppConfig
    paths: PathConfig
    database: DatabaseConfig
    crawler: CrawlerConfig
    search: SearchConfig
    web: WebConfig
    feishu: FeishuConfig
    priority_scope: tuple[str, ...]


def load_settings(path: str | Path | None = None) -> Settings:
    settings_path = Path(path or os.getenv("JOB_WATCHER_SETTINGS", DEFAULT_SETTINGS_PATH))
    if not settings_path.is_absolute():
        settings_path = ROOT_DIR / settings_path
    raw = read_yaml(settings_path)

    app_raw = raw.get("app", {})
    paths_raw = raw.get("paths", {})
    database_raw = raw.get("database", {})
    crawler_raw = raw.get("crawler", {})
    search_raw = raw.get("search", {})
    web_raw = raw.get("web", {})
    feishu_raw = raw.get("feishu", {})
    monitor_raw = raw.get("monitor", {})
    priority_scope = monitor_raw.get("default_priority_scope", ["P0", "P1"])
    if isinstance(priority_scope, dict):
        priority_scope = priority_scope.get("default_priority_scope", ["P0", "P1"])

    data_dir = resolve_path(paths_raw.get("data_dir", "data"))
    database_path = resolve_path(paths_raw.get("database_path", "data/job_watcher.db"))
    snapshots_dir = resolve_path(paths_raw.get("snapshots_dir", "data/snapshots"))

    providers = search_raw.get("providers", {})
    search = SearchConfig(
        default_count=int(search_raw.get("default_count", 5)),
        zhihu=SearchProviderConfig(enabled=bool(providers.get("zhihu", {}).get("enabled", True))),
        baidu=SearchProviderConfig(enabled=bool(providers.get("baidu", {}).get("enabled", True))),
        bocha=SearchProviderConfig(enabled=bool(providers.get("bocha", {}).get("enabled", False))),
        zhihu_api_key=os.getenv("ZHIHU_API_KEY", ""),
        zhihu_resolve_ip=os.getenv("ZHIHU_RESOLVE_IP", ""),
        baidu_api_key=os.getenv("BAIDU_SEARCH_API_KEY", ""),
        baidu_resolve_ip=os.getenv("BAIDU_RESOLVE_IP", ""),
        bocha_api_key=os.getenv("BOCHA_API_KEY", ""),
    )

    return Settings(
        root_dir=ROOT_DIR,
        app=AppConfig(
            name=str(app_raw.get("name", "qingdao-job-watcher")),
            timezone=str(app_raw.get("timezone", "Asia/Shanghai")),
            environment=str(app_raw.get("environment", "local")),
        ),
        paths=PathConfig(
            data_dir=data_dir,
            database_path=database_path,
            snapshots_dir=snapshots_dir,
        ),
        database=DatabaseConfig(url=str(database_raw.get("url", f"sqlite:///{database_path}"))),
        crawler=CrawlerConfig(
            user_agent=str(crawler_raw.get("user_agent", "Mozilla/5.0")),
            timeout_seconds=int(crawler_raw.get("timeout_seconds", 20)),
            max_concurrency=int(crawler_raw.get("max_concurrency", 3)),
            snapshot_enabled=bool(crawler_raw.get("snapshot_enabled", True)),
        ),
        search=search,
        web=WebConfig(
            host=str(web_raw.get("host", "127.0.0.1")),
            port=int(web_raw.get("port", 8000)),
            debug=bool(web_raw.get("debug", True)),
        ),
        feishu=FeishuConfig(
            enabled=bool(feishu_raw.get("enabled", False)),
            webhook_url=os.getenv("FEISHU_WEBHOOK_URL", ""),
        ),
        priority_scope=tuple(priority_scope),
    )


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Settings file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        if yaml is not None:
            data = yaml.safe_load(f) or {}
        else:
            data = parse_simple_yaml(f.read())
    if not isinstance(data, dict):
        raise ValueError(f"Settings file must contain a mapping: {path}")
    return data


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by config/settings.yaml.

    This fallback intentionally supports only nested mappings, scalar values,
    booleans, integers, and simple dash lists. Install PyYAML for general YAML.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    current_list_key: dict[int, str] = {}

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if line.startswith("- "):
            key = current_list_key.get(indent)
            if not key:
                raise ValueError(f"List item without parent key: {raw_line}")
            parent.setdefault(key, [])
            if not isinstance(parent[key], list):
                raise ValueError(f"YAML key is not a list: {key}")
            parent[key].append(parse_scalar(line[2:].strip()))
            continue

        if ":" not in line:
            raise ValueError(f"Unsupported YAML line: {raw_line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value == "":
            container: dict[str, Any] = {}
            parent[key] = container
            stack.append((indent, container))
            current_list_key[indent + 2] = key
        else:
            parent[key] = parse_scalar(value)

    return root


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value
