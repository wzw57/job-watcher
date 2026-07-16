from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol


@dataclass(frozen=True)
class CollectionResult:
    status: str
    requested_url: str
    final_url: str
    http_status: int | None = None
    content_type: str = ""
    title: str = ""
    text: str = ""
    html: str = ""
    content_hash: str = ""
    error_type: str = ""
    error_message: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status in {"success", "no_content_change"}


class Collector(Protocol):
    def collect(self, url: str) -> CollectionResult: ...
