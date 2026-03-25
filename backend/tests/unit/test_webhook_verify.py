import hashlib
import hmac

from workbalancer.infrastructure.webhook_verify import verify_cursor_webhook_signature


def test_verify_accepts_valid_signature() -> None:
    secret = "s" * 32
    body = b'{"event":"statusChange","id":"bc_1"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_cursor_webhook_signature(secret, body, sig) is True


def test_verify_rejects_wrong_signature() -> None:
    secret = "s" * 32
    body = b"{}"
    assert verify_cursor_webhook_signature(secret, body, "sha256=deadbeef") is False


def test_verify_rejects_missing_header_or_secret() -> None:
    assert verify_cursor_webhook_signature("secret", b"{}", None) is False
    assert verify_cursor_webhook_signature("", b"{}", "sha256=abc") is False
