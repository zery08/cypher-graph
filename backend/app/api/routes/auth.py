"""
Keycloak BFF 인증 라우터
브라우저 → 이 서버 → Keycloak 흐름으로 처리하며,
토큰은 HttpOnly 세션 쿠키에만 보관된다.
"""
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.auth import oauth, get_current_user
from app.core.database import get_db
from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/auth/login")
async def login(request: Request):
    """Keycloak 로그인 페이지로 리디렉트한다."""
    return await oauth.keycloak.authorize_redirect(request, settings.keycloak_redirect_uri)


@router.get("/auth/callback")
async def callback(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Keycloak에서 인가 코드를 받아 토큰으로 교환하고
    사용자 정보를 DB에 저장(upsert)한 후 프론트엔드로 리디렉트한다.
    """
    try:
        token = await oauth.keycloak.authorize_access_token(request)
    except Exception as e:
        logger.error(f"Keycloak 토큰 교환 실패: {e}")
        raise HTTPException(status_code=400, detail="인증 실패")

    userinfo = token.get("userinfo") or {}
    sub = userinfo.get("sub")
    if not sub:
        raise HTTPException(status_code=400, detail="사용자 정보를 가져올 수 없습니다")

    username = userinfo.get("preferred_username") or userinfo.get("name") or sub
    email = userinfo.get("email")

    # DB upsert
    result = await db.execute(select(User).where(User.id == sub))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(id=sub, username=username, email=email)
        db.add(user)
    else:
        user.username = username
        user.email = email
    await db.commit()

    # 세션에 사용자 정보 저장 (토큰은 서버 세션에만 보관)
    request.session["user"] = {"sub": sub, "username": username, "email": email}
    request.session["access_token"] = token.get("access_token", "")

    logger.info(f"로그인 성공: {username} ({sub})")
    return RedirectResponse(url=settings.frontend_url)


@router.get("/auth/logout")
async def logout(request: Request):
    """세션을 삭제하고 Keycloak 로그아웃 엔드포인트로 리디렉트한다."""
    request.session.clear()
    logout_url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        f"/protocol/openid-connect/logout"
        f"?post_logout_redirect_uri={settings.frontend_url}"
    )
    return RedirectResponse(url=logout_url)


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    """현재 로그인한 사용자 정보를 반환한다."""
    return user
