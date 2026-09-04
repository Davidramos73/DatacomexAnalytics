"""Auth endpoints: Google login, session introspection, logout, public config."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import backend.config as config
from backend import auth, auth_db

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleLogin(BaseModel):
    credential: str


@router.get("/config")
def auth_config() -> dict:
    return {"client_id": config.GOOGLE_CLIENT_ID, "auth_enabled": config.AUTH_ENABLED}


@router.post("/google")
def google_login(body: GoogleLogin, request: Request) -> dict:
    try:
        ident = auth.verify_google_token(body.credential)
    except auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if not auth.is_allowed(ident["email"]):
        raise HTTPException(status_code=403, detail="email no autorizado")

    auth_db.record_login(
        ident["email"], ident["name"], request.headers.get("user-agent")
    )
    request.session["user"] = {"email": ident["email"], "name": ident["name"]}
    return {"email": ident["email"], "name": ident["name"]}


@router.get("/me")
def me(request: Request) -> dict:
    user = getattr(request.state, "user", None) or request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="no autenticado")
    return {"email": user["email"], "name": user["name"]}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}
