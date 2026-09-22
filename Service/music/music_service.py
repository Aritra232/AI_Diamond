import mimetypes
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from Service.music.music_generation_service import (
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
    style: str | None = Field(None, examples=["cinematic pop"])
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

    return await run_in_threadpool(
        generate_music_from_text,
        mode=data.mode,
        prompt=data.prompt,
        lyrics=data.lyrics,
        song_name=data.song_name,
        style=data.style,
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
    if uploaded_content_type and uploaded_content_type != "application/octet-stream":
        return uploaded_content_type

    guessed_content_type, _ = mimetypes.guess_type(filename)
    return guessed_content_type or "application/octet-stream"
