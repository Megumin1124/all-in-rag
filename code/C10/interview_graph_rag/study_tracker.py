"""Progress tracking and spaced review scheduling."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List


@dataclass
class StudyRecord:
    chunk_id: str
    familiarity: int = 0
    review_count: int = 0
    last_reviewed_at: str = ""
    next_review_at: str = ""


class StudyTracker:
    """Persist study status and compute review schedules with a forgetting-curve style heuristic."""

    def __init__(self, store_path: Path, intervals: List[int]):
        self.store_path = Path(store_path)
        self.intervals = intervals
        self.records: Dict[str, StudyRecord] = self._load()

    def _load(self) -> Dict[str, StudyRecord]:
        if not self.store_path.exists():
            return {}
        raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        return {chunk_id: StudyRecord(**payload) for chunk_id, payload in raw.items()}

    def save(self) -> None:
        self.store_path.write_text(
            json.dumps({chunk_id: asdict(record) for chunk_id, record in self.records.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def update_mastery(self, chunk_id: str, familiarity: int) -> StudyRecord:
        familiarity = max(0, min(5, familiarity))
        now = datetime.utcnow()
        record = self.records.get(chunk_id, StudyRecord(chunk_id=chunk_id))
        record.familiarity = familiarity
        record.review_count += 1
        record.last_reviewed_at = now.isoformat()
        interval_idx = min(record.review_count - 1, len(self.intervals) - 1)
        next_days = self.intervals[interval_idx] + max(familiarity - 2, 0)
        record.next_review_at = (now + timedelta(days=next_days)).isoformat()
        self.records[chunk_id] = record
        self.save()
        return record

    def due_reviews(self, now: datetime | None = None) -> List[StudyRecord]:
        now = now or datetime.utcnow()
        due = []
        for record in self.records.values():
            if record.next_review_at and datetime.fromisoformat(record.next_review_at) <= now:
                due.append(record)
        return sorted(due, key=lambda item: item.next_review_at)
