"""Phase 9 hardening tests: redaction, DSR, rate limits, cost breaker, vault, retention."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from ordy_security.dsr import (
    anonymize_customer,
    build_export,
    erase_customer,
    pseudonymize,
    redact_turn,
    strip_order_pii,
)
from ordy_security.limits import BreakerState, CostBreaker, RateLimiter, TokenBucket
from ordy_security.redaction import REDACTED, redact, redact_text, safe_phone
from ordy_security.retention import RetentionPolicy, cutoffs, is_due
from ordy_security.vault import (
    EnvelopeSecret,
    assert_no_plaintext_secrets,
    decrypt_secret,
    encrypt_secret,
    is_vault_ref,
)

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


# ---------- redaction ----------


def test_redacts_pii_shapes_in_free_text() -> None:
    text = "call +216 20 000 000 or amine@example.com, key ordy_live_abcd1234efgh"
    out = redact_text(text)
    assert "20 000 000" not in out and "amine@example.com" not in out
    assert "ordy_live_abcd1234efgh" not in out
    assert out.count(REDACTED) >= 3


def test_redacts_card_numbers() -> None:
    assert "4111111111111111" not in redact_text("card 4111111111111111 charged")


def test_secret_keys_are_masked_regardless_of_value() -> None:
    payload = {
        "password": "hunter2",
        "Authorization": "Bearer abc",
        "connection_string": "postgres://u:p@host/db",
        "note": "harmless",
        "nested": {"api_key": "x", "items": ["amine@example.com"]},
    }
    out = redact(payload)
    assert out["password"] == REDACTED
    assert out["Authorization"] == REDACTED
    assert out["connection_string"] == REDACTED
    assert out["note"] == "harmless"
    assert out["nested"]["api_key"] == REDACTED
    assert REDACTED in out["nested"]["items"][0]


def test_safe_phone_keeps_last_four_only() -> None:
    assert safe_phone("+21620123456") == "***3456"
    assert safe_phone(None) == ""


# ---------- DSR: erasure must not break the books ----------


def _customer() -> dict:
    return {
        "id": "cus_1", "phone_e164": "+21620000000", "name": "Amine",
        "addresses": [{"line1": "Rue X"}], "preferences": {"usual": "pepperoni"},
        "consent": {"memory": True}, "language": "fr",
    }


def _orders() -> list[dict]:
    return [{
        "id": "ord_1", "customer_id": "cus_1", "created_at": "2026-07-01",
        "subtotal_minor": 32_000, "discount_minor": 0, "delivery_fee_minor": 2_000,
        "total_minor": 34_000, "currency": "TND", "status": "completed", "type": "delivery",
        "address": {"line1": "Rue X"}, "note": "ring twice", "items": [],
    }]


def test_erasure_destroys_identity() -> None:
    scrubbed = anonymize_customer(_customer(), salt="s", now=NOW)
    assert scrubbed["phone_e164"] is None
    assert scrubbed["name"] == "Deleted customer"
    assert scrubbed["addresses"] == [] and scrubbed["preferences"] == {}
    assert scrubbed["anonymized_at"] == NOW
    assert len(scrubbed["pseudonym"]) == 16


def test_erasure_preserves_financial_integrity() -> None:
    """The books must still balance after a customer exercises Art. 17."""
    kept = strip_order_pii(_orders()[0])
    assert kept["total_minor"] == 34_000
    assert kept["currency"] == "TND" and kept["status"] == "completed"
    assert kept["address"] is None and kept["note"] is None
    assert kept["customer_id"] == "cus_1"  # still points at the anonymized row


def test_pseudonym_is_stable_and_non_reversible() -> None:
    a = pseudonymize("+21620000000", salt="s")
    assert a == pseudonymize("+21620000000", salt="s")
    assert a != pseudonymize("+21620000000", salt="other")
    assert "216" not in a


def test_transcript_redaction_preserves_shape_not_content() -> None:
    assert redact_turn("I want a large pepperoni") == "[erased:24]"
    assert redact_turn(None) == ""


def test_full_erasure_result() -> None:
    result = erase_customer(
        customer=_customer(), orders=_orders(), turns=[{"content": "hi"}, {"content": "yes"}],
        salt="s", now=NOW, audio_object_keys=["t/r/audio/1.ogg"],
    )
    assert result.customer["phone_e164"] is None
    assert result.orders[0]["total_minor"] == 34_000
    assert result.turns_redacted == 2
    assert result.objects_deleted == ["t/r/audio/1.ogg"]


def test_export_bundle_is_portable() -> None:
    bundle = build_export(customer=_customer(), orders=_orders(), conversations=[], generated_at=NOW)
    assert bundle["format"] == "ordy.dsr.export/1"
    assert bundle["customer"]["phone_e164"] == "+21620000000"  # export DOES include their data
    assert bundle["orders"][0]["total_minor"] == 34_000


# ---------- rate limiting ----------


def test_token_bucket_burst_then_throttle() -> None:
    bucket = TokenBucket(capacity=3, refill_per_second=1, updated_at=0.0)
    assert all(bucket.allow(0.0) for _ in range(3))
    assert not bucket.allow(0.0)  # burst exhausted
    assert bucket.allow(1.0)  # one token refilled
    assert bucket.retry_after() > 0


def test_rate_limiter_is_keyed() -> None:
    limiter = RateLimiter(capacity=1, refill_per_second=0.1)
    assert limiter.allow("customer:a", 0.0)
    assert not limiter.allow("customer:a", 0.0)
    assert limiter.allow("customer:b", 0.0)  # separate budget


# ---------- cost circuit breaker ----------


def test_breaker_trips_over_budget_and_blocks() -> None:
    breaker = CostBreaker(budget_minor=1_000, window_seconds=60, cooldown_seconds=30)
    breaker.record(0.0, 400)
    assert breaker.state is BreakerState.CLOSED and breaker.allow(0.0)
    breaker.record(1.0, 700)  # 1100 > 1000
    assert breaker.state is BreakerState.OPEN
    assert not breaker.allow(2.0)  # degrade to safe responses


def test_breaker_half_opens_after_cooldown() -> None:
    breaker = CostBreaker(budget_minor=100, window_seconds=60, cooldown_seconds=30)
    breaker.record(0.0, 500)
    assert not breaker.allow(10.0)
    assert breaker.allow(31.0)  # cooldown elapsed → probe
    assert breaker.state is BreakerState.HALF_OPEN


def test_breaker_window_rolls_off_old_spend() -> None:
    breaker = CostBreaker(budget_minor=1_000, window_seconds=60)
    breaker.record(0.0, 900)
    assert breaker.spend(120.0) == 0  # old events pruned
    breaker.record(120.0, 900)
    assert breaker.state is BreakerState.CLOSED


# ---------- vault ----------


class _FakeKeyManager:
    """Test double for KMS — wrapping is a reversible marker, NOT security."""

    def generate_dek(self) -> bytes:
        return os.urandom(32)

    def wrap(self, dek: bytes) -> bytes:
        return b"wrapped:" + dek

    def unwrap(self, wrapped: bytes) -> bytes:
        return wrapped.removeprefix(b"wrapped:")


class _InsecureTestCipher:
    """XOR — explicitly NOT a cipher. Exists only to exercise the envelope flow."""

    def encrypt(self, key: bytes, plaintext: bytes, *, aad: bytes = b"") -> tuple[bytes, bytes]:
        return b"nonce", bytes(b ^ key[i % len(key)] for i, b in enumerate(plaintext))

    def decrypt(self, key: bytes, nonce: bytes, ciphertext: bytes, *, aad: bytes = b"") -> bytes:
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(ciphertext))


def test_envelope_roundtrip_and_blob_encoding() -> None:
    km, cipher = _FakeKeyManager(), _InsecureTestCipher()
    secret = encrypt_secret("postgres://u:p@host/db", km=km, cipher=cipher)
    assert b"postgres" not in secret.ciphertext  # plaintext never stored
    assert decrypt_secret(secret, km=km, cipher=cipher) == "postgres://u:p@host/db"

    restored = EnvelopeSecret.from_blob(secret.to_blob())
    assert decrypt_secret(restored, km=km, cipher=cipher) == "postgres://u:p@host/db"


def test_configs_must_carry_vault_references_not_secrets() -> None:
    assert is_vault_ref("vault:sec_01J9")
    assert not is_vault_ref("postgres://u:p@host/db")

    assert_no_plaintext_secrets({"url": "https://x.tn", "token": "vault:sec_1"}, ("token", "password"))
    with pytest.raises(ValueError, match="vault reference"):
        assert_no_plaintext_secrets({"token": "literal-secret"}, ("token", "password"))


# ---------- retention ----------


def test_retention_cutoffs_and_due_check() -> None:
    policy = RetentionPolicy()
    marks = cutoffs(NOW, policy)
    assert marks.audio_before == NOW - timedelta(days=30)
    assert is_due(NOW - timedelta(days=31), marks.audio_before)
    assert not is_due(NOW - timedelta(days=29), marks.audio_before)


def test_tenant_overrides_may_only_shorten_retention() -> None:
    policy = RetentionPolicy().tightened_by({"audio_days": 7})
    assert policy.audio_days == 7
    # A tenant asking to keep audio for 5 years is clamped to the platform ceiling.
    assert RetentionPolicy().tightened_by({"audio_days": 5_000}).audio_days == 90
