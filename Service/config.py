import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI Diamond Video Generator")
    app_version: str = os.getenv("APP_VERSION", "1.0.0")

    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_image_model: str = os.getenv(
        "GEMINI_IMAGE_MODEL",
        "gemini-3-pro-image",
    )
    gemini_video_model: str = os.getenv(
        "GEMINI_VIDEO_MODEL",
        "veo-3.1-generate-preview",
    )
    video_poll_interval_seconds: int = _get_int("VIDEO_POLL_INTERVAL_SECONDS", 10)
    video_timeout_seconds: int = _get_int("VIDEO_TIMEOUT_SECONDS", 600)

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_music_prompt_model: str = os.getenv(
        "OPENAI_MUSIC_PROMPT_MODEL",
        "gpt-5-mini",
    )
    openai_audio_transcription_model: str = os.getenv(
        "OPENAI_AUDIO_TRANSCRIPTION_MODEL",
        "gpt-4o-transcribe",
    )

    eleven_labs_api_key: str | None = os.getenv("ELEVEN_LABS_API_KEY") or os.getenv(
        "ELEVENLABS_API_KEY"
    )
    eleven_labs_music_model: str = os.getenv(
        "ELEVEN_LABS_MUSIC_MODEL",
        "music_v2_5",
    )

    aws_access_key_id: str | None = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region: str = os.getenv("AWS_REGION") or os.getenv("S3_REGION", "us-east-1")
    aws_s3_bucket: str | None = (
        os.getenv("AWS_S3_BUCKET")
        or os.getenv("AWS_S3_BUCKET_NAME")
        or os.getenv("AWS_BUCKET_NAME")
    )
    aws_s3_public_base_url: str | None = os.getenv("AWS_S3_PUBLIC_BASE_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
