"""Optional Google OIDC login and a same-origin, signed application session."""

from __future__ import annotations

from hashlib import sha256

import httpx
from authlib.integrations.base_client import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from joserfc.errors import JoseError
from starlette.requests import HTTPConnection
from starlette.responses import RedirectResponse

from app.core.config import get_settings

router = APIRouter(prefix="/account")
SESSION_AGE = 7 * 24 * 60 * 60
CALLBACK = "/api/account/google/callback"
_NO_STORE = {"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"}


def check_origin(connection: HTTPConnection) -> None:
    settings = get_settings()
    origin = connection.headers.get("origin")
    trusted = {settings.public_origin.rstrip("/"), *settings.origins}
    if origin is not None and (origin not in trusted or origin == "*"):
        raise HTTPException(403, "Untrusted origin.")


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret.get_secret_value(), "nba-account")


def _session_cookie() -> str:
    return (
        "__Host-nba_account"
        if get_settings().public_origin.startswith("https://")
        else "nba_account"
    )


def current_owner(connection: HTTPConnection) -> str | None:
    if not get_settings().google_sign_in:
        return None
    value = connection.cookies.get(_session_cookie())
    if not value:
        return None
    try:
        owner = _serializer().loads(value, max_age=SESSION_AGE)
    except BadSignature:
        return None
    return owner if isinstance(owner, str) else None


def require_owner(request: Request, response: Response) -> str:
    response.headers.update(_NO_STORE)
    owner = current_owner(request)
    if owner is None:
        raise HTTPException(401, "Sign in to view your history.", headers=_NO_STORE)
    return owner


def _google() -> OAuth:
    settings = get_settings()
    if not settings.google_sign_in:
        raise HTTPException(404, "Google sign-in is unavailable.")
    oauth = OAuth()
    oauth.register(
        "google",
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid", "code_challenge_method": "S256", "timeout": 10},
    )
    return oauth


@router.get("/session")
async def session(request: Request, response: Response) -> dict[str, bool]:
    response.headers.update(_NO_STORE)
    return {
        "google_sign_in": get_settings().google_sign_in,
        "signed_in": current_owner(request) is not None,
    }


@router.get("/google")
async def sign_in(request: Request) -> Response:
    google = _google().create_client("google")
    request.session.clear()
    redirect_uri = get_settings().public_origin.rstrip("/") + CALLBACK
    try:
        response: Response = await google.authorize_redirect(request, redirect_uri)
    except (OAuthError, httpx.HTTPError):
        response = RedirectResponse("/?account=error", status_code=303)
    response.headers.update(_NO_STORE)
    return response


@router.get("/google/callback")
async def sign_in_callback(request: Request) -> Response:
    google = _google().create_client("google")
    subject = None
    try:
        token = await google.authorize_access_token(request)
        subject = token.get("userinfo", {}).get("sub")
    except (OAuthError, JoseError, httpx.HTTPError, ValueError):
        pass
    finally:
        request.session.clear()
    if not isinstance(subject, str) or not subject:
        return RedirectResponse("/?account=error", status_code=303, headers=_NO_STORE)
    owner = sha256(f"google:{subject}".encode()).hexdigest()
    response = RedirectResponse("/?view=history", status_code=303, headers=_NO_STORE)
    response.set_cookie(
        _session_cookie(),
        _serializer().dumps(owner),
        max_age=SESSION_AGE,
        httponly=True,
        secure=_session_cookie().startswith("__Host-"),
        samesite="lax",
    )
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    check_origin(request)
    response = Response(status_code=204, headers=_NO_STORE)
    response.delete_cookie(
        _session_cookie(),
        httponly=True,
        secure=_session_cookie().startswith("__Host-"),
        samesite="lax",
    )
    return response
