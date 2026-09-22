import json
from io import BytesIO

from Service.config import get_settings


def _get_openai_client():
    from openai import OpenAI

    api_key = get_settings().openai_api_key
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    return OpenAI(api_key=api_key)


def refine_music_prompt(
    *,
    prompt: str,
    song_name: str | None = None,
    style: str | None = None,
) -> dict:
    settings = get_settings()
    user_context = {
        "song_name": song_name,
        "style": style,
        "prompt": prompt,
    }

    response = _get_openai_client().responses.create(
        model=settings.openai_music_prompt_model,
        input=[
            {
                "role": "system",
                "content": (
                    "You prepare concise production prompts for ElevenLabs Music. "
                    "Rewrite the user idea into a clear music generation prompt. "
                    "Do not mention copyrighted artists or songs. Return JSON only "
                    "with keys: refined_prompt, estimated_duration_seconds."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(user_context, ensure_ascii=False),
            },
        ],
    )

    raw_text = response.output_text.strip()
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        data = {
            "refined_prompt": raw_text,
            "estimated_duration_seconds": estimate_prompt_duration(prompt),
        }

    refined_prompt = str(data.get("refined_prompt") or prompt).strip()
    duration = _clamp_duration(data.get("estimated_duration_seconds"))
    return {
        "refined_prompt": refined_prompt,
        "estimated_duration_seconds": duration,
    }


def transcribe_audio(
    *,
    audio_bytes: bytes,
    filename: str,
    prompt: str | None = None,
) -> str:
    settings = get_settings()
    audio_file = BytesIO(audio_bytes)
    audio_file.name = filename

    kwargs = {
        "model": settings.openai_audio_transcription_model,
        "file": audio_file,
    }
    if prompt:
        kwargs["prompt"] = prompt

    transcript = _get_openai_client().audio.transcriptions.create(**kwargs)
    return getattr(transcript, "text", "").strip()


def estimate_prompt_duration(prompt: str) -> int:
    word_count = len(prompt.split())
    if word_count <= 12:
        return 30
    if word_count <= 40:
        return 45
    if word_count <= 90:
        return 60
    return 90


def estimate_lyrics_duration(lyrics: str) -> int:
    word_count = len(lyrics.split())
    if word_count == 0:
        return 30

    seconds = int((word_count / 1.8) + 20)
    return _round_to_nearest_five(_clamp_duration(seconds))


def _clamp_duration(value) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = 45

    return max(30, min(seconds, 300))


def _round_to_nearest_five(value: int) -> int:
    return int(round(value / 5) * 5)
