from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.security import decode_access_token


def rate_limit_key(request) -> str:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            payload = decode_access_token(token)
            subject = str(payload.get("sub") or "").strip()
            if subject:
                return f"user:{subject}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=rate_limit_key)
