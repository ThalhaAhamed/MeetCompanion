"""
Unit tests for MeetStream webhook signature verification, replay protection, and handling.
"""
import pytest
import hmac
import hashlib
import json
from datetime import datetime, timezone, timedelta
from app.api.webhooks import verify_meetstream_signature


def test_verify_signature_valid():
    secret = "test_webhook_secret_123"
    payload = {"bot_id": "bot_999", "event": "bot.inmeeting"}
    raw_body = json.dumps(payload).encode("utf-8")
    now_iso = datetime.now(timezone.utc).isoformat()

    expected_sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    is_valid = verify_meetstream_signature(
        secret=secret,
        raw_body=raw_body,
        signature_header=expected_sig,
        timestamp_header=now_iso,
    )
    assert is_valid is True


def test_verify_signature_tampered_body():
    secret = "test_webhook_secret_123"
    payload = {"bot_id": "bot_999", "event": "bot.inmeeting"}
    raw_body = json.dumps(payload).encode("utf-8")
    tampered_body = json.dumps({"bot_id": "bot_999", "event": "bot.stopped"}).encode("utf-8")
    now_iso = datetime.now(timezone.utc).isoformat()

    sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    is_valid = verify_meetstream_signature(
        secret=secret,
        raw_body=tampered_body,
        signature_header=sig,
        timestamp_header=now_iso,
    )
    assert is_valid is False


def test_verify_signature_expired_timestamp():
    secret = "test_webhook_secret_123"
    payload = {"bot_id": "bot_999", "event": "bot.inmeeting"}
    raw_body = json.dumps(payload).encode("utf-8")
    # 10 minutes ago
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

    sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    is_valid = verify_meetstream_signature(
        secret=secret,
        raw_body=raw_body,
        signature_header=sig,
        timestamp_header=old_time,
        tolerance_seconds=300,  # 5 minutes
    )
    assert is_valid is False


def test_verify_signature_missing_prefix():
    secret = "test_webhook_secret_123"
    raw_body = b'{"bot_id": "bot_123"}'
    raw_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    # Missing "sha256=" prefix
    is_valid = verify_meetstream_signature(
        secret=secret,
        raw_body=raw_body,
        signature_header=raw_sig,
        timestamp_header=datetime.now(timezone.utc).isoformat(),
    )
    assert is_valid is False
