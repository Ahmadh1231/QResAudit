"""Local literature/material records; citations are accepted only when supplied."""

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class KnowledgeRecord:
    record_id: str
    kind: str
    title: str
    source_identifier: str | None
    evidence_quality: str
    claims: tuple[str, ...]
    properties: dict[str, float | str]
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.record_id or self.kind not in {"literature", "material", "fabrication"}:
            raise ValueError("invalid knowledge record")
        if self.evidence_quality not in {"measured", "reported", "derived", "unknown"}:
            raise ValueError("invalid evidence quality")


class KnowledgeBase:
    def __init__(self, records: list[KnowledgeRecord] | None = None) -> None:
        self.records = list(records or [])

    def add(self, record: KnowledgeRecord) -> None:
        self.records.append(record)

    def query(
        self, text: str = "", *, kind: str | None = None, minimum_quality: str | None = None
    ) -> list[KnowledgeRecord]:
        quality = {"unknown": 0, "derived": 1, "reported": 2, "measured": 3}
        if minimum_quality is not None and minimum_quality not in quality:
            raise ValueError("unknown quality")
        needle = text.casefold()
        return [
            r
            for r in self.records
            if (not kind or r.kind == kind)
            and (not minimum_quality or quality[r.evidence_quality] >= quality[minimum_quality])
            and (not needle or needle in (r.title + " " + " ".join(r.claims)).casefold())
        ]

    def to_json(self) -> str:
        return json.dumps([asdict(r) for r in self.records], indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> "KnowledgeBase":
        return cls([KnowledgeRecord(**r) for r in json.loads(value)])
