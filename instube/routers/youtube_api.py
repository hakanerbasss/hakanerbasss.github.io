"""YouTube yapılandırma ve OAuth yetkilendirme uçları."""
import secrets
import hashlib
import base64

from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import RedirectResponse

from config import YT_VERIFIER, YT_VERIFIER_EN, YT_TOKEN_FILE, YT_TOKEN_FILE_EN
import youtube

router = APIRouter()


@router.get("/api/yt/config")
async def get_yt_config():
    return youtube.yt_status()


@router.post("/api/yt/config")
async def post_yt_config(client_id: str = Form(...), client_secret: str = Form(...)):
    youtube.save_yt_config(client_id.strip(), client_secret.strip())
    return {"ok": True}


def _start_auth(request: Request, callback_path: str, verifier_file):
    cfg = youtube.load_yt_config()
    if not cfg:
        raise HTTPException(400, "Önce YouTube client_id ve client_secret girin")
    redirect_uri = str(request.base_url) + callback_path
    flow = youtube.build_flow(cfg, redirect_uri)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    verifier_file.write_text(code_verifier)
    auth_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent",
        code_challenge=code_challenge, code_challenge_method="S256",
    )
    return RedirectResponse(auth_url)


def _finish_auth(request: Request, code: str, callback_path: str, verifier_file, token_file):
    cfg = youtube.load_yt_config()
    redirect_uri = str(request.base_url) + callback_path
    flow = youtube.build_flow(cfg, redirect_uri)
    code_verifier = verifier_file.read_text() if verifier_file.exists() else None
    flow.fetch_token(code=code, code_verifier=code_verifier)
    token_file.write_text(flow.credentials.to_json())


@router.get("/auth/youtube")
async def youtube_auth(request: Request):
    return _start_auth(request, "auth/youtube/callback", YT_VERIFIER)


@router.get("/auth/youtube/callback")
async def youtube_callback(request: Request, code: str):
    _finish_auth(request, code, "auth/youtube/callback", YT_VERIFIER, YT_TOKEN_FILE)
    return RedirectResponse("/settings.html?yt=ok")


@router.get("/auth/youtube/en")
async def youtube_auth_en(request: Request):
    return _start_auth(request, "auth/youtube/en/callback", YT_VERIFIER_EN)


@router.get("/auth/youtube/en/callback")
async def youtube_callback_en(request: Request, code: str):
    _finish_auth(request, code, "auth/youtube/en/callback", YT_VERIFIER_EN, YT_TOKEN_FILE_EN)
    return RedirectResponse("/settings.html?yt_en=ok")
