"""
인증 의존성 — 세션에서 현재 사용자를 추출한다.
"""
from fastapi import Request, HTTPException
from authlib.integrations.starlette_client import OAuth
from app.core.config import settings

# ── Keycloak OAuth 클라이언트 ─────────────────────────────────────────────────

oauth = OAuth()
oauth.register(
    name="keycloak",
    server_metadata_url=(
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        "/.well-known/openid-configuration"
    ),
    client_id=settings.keycloak_client_id,
    client_secret=settings.keycloak_client_secret,
    client_kwargs={"scope": "openid email profile"},
)


# ── 현재 사용자 의존성 ──────────────────────────────────────────────────────────

async def get_current_user(request: Request) -> dict:
    """
    세션 쿠키에서 로그인 사용자 정보를 반환한다.
    인증되지 않은 경우 401을 반환한다.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    return user


async def get_current_user_optional(request: Request) -> dict | None:
    """인증 여부에 관계없이 사용자 정보를 반환한다 (없으면 None)."""
    return request.session.get("user")
