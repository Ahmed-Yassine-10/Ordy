"""Retention policy evaluation (doc 06 §5, doc 08 §7).

Defaults are tenant-tunable *downward* only — a tenant may keep less than the platform
default, never more than the legal ceiling. The retention worker asks this module what is
due; it holds no database knowledge itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

DAY = timedelta(days=1)


@dataclass(slots=True)
class RetentionPolicy:
    audio_days: int = 30
    transcript_days: int = 365
    audit_days: int = 730
    webhook_delivery_days: int = 90
    ingestion_artifact_days: int = 90

    # Platform ceilings — a tenant override may only shorten these.
    CEILINGS = {
        "audio_days": 90,
        "transcript_days": 365 * 2,
        "audit_days": 730,
        "webhook_delivery_days": 180,
        "ingestion_artifact_days": 365,
    }

    def tightened_by(self, overrides: dict) -> "RetentionPolicy":
        values = {}
        for field_name, ceiling in self.CEILINGS.items():
            requested = int(overrides.get(field_name, getattr(self, field_name)))
            values[field_name] = max(1, min(requested, ceiling))
        return RetentionPolicy(**values)


@dataclass(slots=True)
class RetentionCutoffs:
    audio_before: datetime
    transcripts_before: datetime
    audit_before: datetime
    webhooks_before: datetime
    artifacts_before: datetime


def cutoffs(now: datetime, policy: RetentionPolicy) -> RetentionCutoffs:
    return RetentionCutoffs(
        audio_before=now - policy.audio_days * DAY,
        transcripts_before=now - policy.transcript_days * DAY,
        audit_before=now - policy.audit_days * DAY,
        webhooks_before=now - policy.webhook_delivery_days * DAY,
        artifacts_before=now - policy.ingestion_artifact_days * DAY,
    )


def is_due(created_at: datetime, cutoff: datetime) -> bool:
    return created_at < cutoff
