from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PointInTimeRecord:
    name: str
    feature_as_of: datetime
    source_published_at: datetime
    decision_time: datetime


class PointInTimeViolation(ValueError):
    pass


def validate_record(record: PointInTimeRecord) -> None:
    if record.feature_as_of > record.decision_time:
        raise PointInTimeViolation(
            f"{record.name}: feature_as_of occurs after decision_time"
        )
    if record.source_published_at > record.decision_time:
        raise PointInTimeViolation(
            f"{record.name}: source_published_at occurs after decision_time"
        )


def validate_many(records: list[PointInTimeRecord]) -> None:
    for record in records:
        validate_record(record)
