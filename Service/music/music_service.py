import mimetypes
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from Service.music.music_generation_service import (
    ALLOWED_PROMPT_STYLES,
    enhance_uploaded_audio,
    generate_music_from_text,
)

router = APIRouter()


class TextToMusicRequest(BaseModel):
    mode: Literal["prompt", "lyrics"] = Field(..., examples=["prompt", "lyrics"])
    song_name: str | None = Field(None, examples=["Diamond Dreams"])
    prompt: str | None = Field(
        None,
        examples=["A romantic cinematic pop song about diamonds and city lights"],
    )
    lyrics: str | None = Field(
        None,
        examples=["Shine like a diamond in the night..."],
    )
    style: list[str] | str | None = Field(
        None,
        examples=[["Piano", "Violin"]],
    )
    instrumental: bool = False


@router.post(
    "/text-to-music",
    summary="Generate music from prompt or lyrics",
    operation_id="generateMusicFromText",
)
async def text_to_music(data: TextToMusicRequest):
    if data.mode == "prompt" and not (data.prompt and data.prompt.strip()):
        raise HTTPException(
            status_code=422,
            detail="prompt is required when mode is 'prompt'.",
        )
    if data.mode == "lyrics" and not (data.lyrics and data.lyrics.strip()):
        raise HTTPException(
            status_code=422,
            detail="lyrics is required when mode is 'lyrics'.",
        )

    selected_styles = _normalize_styles(data.style) if data.mode == "prompt" else []
    style_text = ", ".join(selected_styles) if data.mode == "prompt" else _style_to_text(data.style)
    if data.mode == "prompt":
        invalid_styles = [
            style
            for style in selected_styles
            if style not in ALLOWED_PROMPT_STYLES
        ]
        if invalid_styles:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Invalid style selected.",
                    "invalid_styles": invalid_styles,
                    "allowed_styles": sorted(ALLOWED_PROMPT_STYLES),
                },
            )

    return await run_in_threadpool(
        generate_music_from_text,
        mode=data.mode,
        prompt=data.prompt,
        lyrics=data.lyrics,
        song_name=data.song_name,
        style=style_text,
        selected_styles=selected_styles,
        instrumental=data.instrumental,
    )


@router.post(
    "/enhance-audio",
    summary="Clean and enhance uploaded audio",
    operation_id="enhanceUploadedAudio",
)
async def enhance_audio(
    audio: UploadFile = File(...),
    prompt: str = Form(...),
):
    audio_bytes = await audio.read()
    filename = audio.filename or "audio"
    try:
        return await run_in_threadpool(
            enhance_uploaded_audio,
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=_detect_content_type(filename, audio.content_type),
            prompt=prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _detect_content_type(filename: str, uploaded_content_type: str | None) -> str:
    normalized_content_type = _content_type_from_extension(filename)
    if normalized_content_type:
        return normalized_content_type

    if uploaded_content_type and uploaded_content_type != "application/octet-stream":
        return _normalize_audio_content_type(uploaded_content_type)

    guessed_content_type, _ = mimetypes.guess_type(filename)
    return _normalize_audio_content_type(guessed_content_type) or "application/octet-stream"


def _content_type_from_extension(filename: str) -> str | None:
    extension = Path(filename).suffix.lower()
    return {
        ".mp3": "audio/mpeg",
        ".mpeg": "audio/mpeg",
        ".mpga": "audio/mpeg",
        ".wav": "audio/wav",
        ".wave": "audio/wav",
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".oga": "audio/ogg",
        ".opus": "audio/ogg",
        ".webm": "audio/webm",
        ".aiff": "audio/aiff",
        ".aif": "audio/aiff",
        ".amr": "audio/amr",
        ".wma": "audio/x-ms-wma",
    }.get(extension)


def _normalize_audio_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    lowered = content_type.lower()
    return {
        "audio/mp3": "audio/mpeg",
        "audio/mpeg3": "audio/mpeg",
        "audio/x-mpeg-3": "audio/mpeg",
        "audio/x-wav": "audio/wav",
        "audio/wave": "audio/wav",
        "audio/x-m4a": "audio/mp4",
        "audio/mp4a-latm": "audio/mp4",
        "audio/x-aiff": "audio/aiff",
    }.get(lowered, content_type)


def _normalize_styles(styles: list[str] | str | None) -> list[str]:
    if styles is None:
        return []
    if isinstance(styles, str):
        return [styles.strip()] if styles.strip() else []

    normalized = []
    for style in styles:
        cleaned = style.strip()
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def _style_to_text(style: list[str] | str | None) -> str | None:
    if style is None:
        return None
    if isinstance(style, str):
        return style
    return ", ".join(_normalize_styles(style))
