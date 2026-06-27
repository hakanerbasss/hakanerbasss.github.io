from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    tts_voice: str = "M1"    # M1 erkek, F1 kadın
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
    def db_path(self) -> Path:
        return self.base_dir / "jobs.db"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
