from pathlib import Path
from pydantic_settings import BaseSettings

VOICES = {
    "M1": "Erkek 1", "M2": "Erkek 2", "M3": "Erkek 3",
    "F1": "Kadın 1",  "F2": "Kadın 2",  "F3": "Kadın 3",
}

PREVIEW_TEXT = (
    "Merhaba! Bu ses ile kitabınızı seslendirebilirim. "
    "Sesin kalitesini ve akıcılığını bu kısa örnekten değerlendirebilirsiniz."
)


class Settings(BaseSettings):
    tts_voice: str = "M1"
    tts_lang: str = "tr"
    tts_speed: float = 1.0
    tts_steps: int = 8

    base_dir: Path = Path(__file__).parent.parent

    @property
    def uploads_dir(self) -> Path:
        p = self.base_dir / "uploads"
        p.mkdir(exist_ok=True)
        return p

    @property
    def outputs_dir(self) -> Path:
        p = self.base_dir / "outputs"
        p.mkdir(exist_ok=True)
        return p

    @property
    def previews_dir(self) -> Path:
        p = self.base_dir / "outputs" / "previews"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        return self.base_dir / "jobs.db"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
