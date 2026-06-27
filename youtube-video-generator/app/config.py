from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DeepSeek LLM
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # TTS
    tts_url: str = "http://localhost:5500"
    tts_speaker: str = "tr_speaker_0"
    tts_backend: str = "edge-tts"  # "supertonic" veya "edge-tts"

    # Pexels
    pexels_api_key: str = ""

    # YouTube
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = "http://localhost:8000/api/youtube/callback"

    # Paths
    base_dir: Path = Path(__file__).parent.parent
    font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    @property
    def outputs_dir(self) -> Path:
        p = self.base_dir / "outputs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def temp_dir(self) -> Path:
        p = self.base_dir / "temp"
        p.mkdir(parents=True, exist_ok=True)
        return p

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
