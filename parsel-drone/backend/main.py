from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import httpx
import jwt
import bcrypt
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

SECRET_KEY = os.getenv("SECRET_KEY", "changeme-in-production")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./parsel_drone.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

app = FastAPI(title="Parsel Drone API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()
_cache = {}  # in-memory cache for TKGM lists

TKGM_BASE = "https://cbsapi.tkgm.gov.tr/megsiswebapi.v3/api"


# --- Models ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    credits = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.utcnow)


class VideoHistory(Base):
    __tablename__ = "video_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    il = Column(String)
    ilce = Column(String)
    mahalle = Column(String)
    ada = Column(String)
    parsel = Column(String)
    lat = Column(Float)
    lon = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


# --- Schemas ---

class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ParselRequest(BaseModel):
    il_id: int
    il_adi: str
    ilce_id: int
    ilce_adi: str
    mahalle_id: int
    mahalle_adi: str
    ada: str
    parsel: str


# --- Helpers ---

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(days=30)}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        user = db.query(User).filter(User.id == int(payload["sub"])).first()
        if not user:
            raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token süresi doldu")
    except Exception:
        raise HTTPException(status_code=401, detail="Geçersiz token")


async def tkgm_get(url: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


# --- TKGM List Endpoints (cached) ---

@app.get("/api/iller")
async def iller():
    if "iller" not in _cache:
        data = await tkgm_get(f"{TKGM_BASE}/idariYapi/ilListe")
        _cache["iller"] = sorted(
            [{"text": f["properties"]["text"], "id": f["properties"]["id"]} for f in data["features"]],
            key=lambda x: x["text"]
        )
    return _cache["iller"]


@app.get("/api/ilceler/{il_id}")
async def ilceler(il_id: int):
    key = f"ilce_{il_id}"
    if key not in _cache:
        data = await tkgm_get(f"{TKGM_BASE}/idariYapi/ilceListe/{il_id}")
        _cache[key] = sorted(
            [{"text": f["properties"]["text"], "id": f["properties"]["id"]} for f in data["features"]],
            key=lambda x: x["text"]
        )
    return _cache[key]


@app.get("/api/mahalleler/{ilce_id}")
async def mahalleler(ilce_id: int):
    key = f"mahalle_{ilce_id}"
    if key not in _cache:
        data = await tkgm_get(f"{TKGM_BASE}/idariYapi/mahalleListe/{ilce_id}")
        _cache[key] = sorted(
            [{"text": f["properties"]["text"], "id": f["properties"]["id"]} for f in data["features"]],
            key=lambda x: x["text"]
        )
    return _cache[key]


# --- Auth Routes ---

@app.post("/api/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Bu email zaten kayıtlı")
    user = User(email=req.email, password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id), "credits": user.credits}


@app.post("/api/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email veya şifre hatalı")
    return {"token": create_token(user.id), "credits": user.credits}


@app.get("/api/me")
def me(user: User = Depends(get_current_user)):
    return {"email": user.email, "credits": user.credits}


# --- Parsel Route ---

@app.post("/api/parsel")
async def get_parsel(
    req: ParselRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.credits <= 0:
        raise HTTPException(status_code=402, detail="Krediniz yetersiz")

    url = f"{TKGM_BASE}/parsel/{req.mahalle_id}/{req.ada}/{req.parsel}"

    try:
        data = await tkgm_get(url)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Bu ada/parsel bulunamadı")
        raise HTTPException(status_code=502, detail="TKGM servisine ulaşılamadı")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="TKGM servisine ulaşılamadı")

    try:
        coords = data["geometry"]["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        center_lon = sum(lons) / len(lons)
        center_lat = sum(lats) / len(lats)
    except (KeyError, IndexError, TypeError):
        raise HTTPException(status_code=404, detail="Parsel bulunamadı")

    user.credits -= 1
    db.commit()

    history = VideoHistory(
        user_id=user.id,
        il=req.il_adi,
        ilce=req.ilce_adi,
        mahalle=req.mahalle_adi,
        ada=req.ada,
        parsel=req.parsel,
        lat=center_lat,
        lon=center_lon,
    )
    db.add(history)
    db.commit()

    return {
        "lat": center_lat,
        "lon": center_lon,
        "coordinates": coords,
        "remaining_credits": user.credits,
    }


@app.get("/api/history")
def history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    records = (
        db.query(VideoHistory)
        .filter(VideoHistory.user_id == user.id)
        .order_by(VideoHistory.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": r.id,
            "il": r.il,
            "ilce": r.ilce,
            "mahalle": r.mahalle,
            "ada": r.ada,
            "parsel": r.parsel,
            "lat": r.lat,
            "lon": r.lon,
            "date": r.created_at.strftime("%d.%m.%Y %H:%M"),
        }
        for r in records
    ]


@app.get("/health")
def health():
    return {"status": "ok"}
