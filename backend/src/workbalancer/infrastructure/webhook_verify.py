import hashlib
import hmac


def verify_cursor_webhook_signature(secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
