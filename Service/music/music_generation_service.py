import math
import re
import shutil
from io import BytesIO

from Service.config import get_settings
from Service.music.elevenlabs_client import get_eleven_labs_api_key
from Service.music.openai_music_service import (
    estimate_lyrics_duration,
    refine_music_prompt,
)
from Service.storage.s3_service import upload_bytes


ELEVEN_LABS_BASE_URL = "https://api.elevenlabs.io/v1"

ALLOWED_PROMPT_STYLES = {
    "Acoustic Guitar",
    "Electric Guitar",
    "Bass Guitar",
    "Piano",
    "Guitar",
    "Keyboard",
    "Synthesizer",
    "Drums",
    "Percussion",
    "Tabla",
    "Violin",
    "Flute",
    "Viola",
    "Cello",
    "Harp",
    "Bansuri",
    "Clarinet",
    "Oboe",
    "Trumpet",
    "Saxophone",
    "Bass",
    "Trombone",
    "Sitar",
    "Harmonium",
    "Ukulele",
    "Accordion",
}


def generate_music_from_text(
    *,
    mode: str,
    prompt: str | None = None,
    lyrics: str | None = None,
    song_name: str | None = None,
    style: str | None = None,
    selected_styles: list[str] | None = None,
    instrumental: bool = False,
) -> dict:
    normalized_mode = mode.lower().strip()
    if normalized_mode not in {"prompt", "lyrics"}:
        raise ValueError("mode must be either 'prompt' or 'lyrics'.")

    if normalized_mode == "lyrics":
        if not lyrics or not lyrics.strip():
            raise ValueError("lyrics is required when mode is 'lyrics'.")
        final_prompt = _build_lyrics_music_prompt(
            lyrics=lyrics,
            song_name=song_name,
            style=style,
            instrumental=instrumental,
        )
        estimated_duration_seconds = estimate_lyrics_duration(lyrics)
        composition_plan = _build_lyrics_composition_plan(
            lyrics=lyrics,
            duration_seconds=estimated_duration_seconds,
            song_name=song_name,
            style=style,
            instrumental=instrumental,
        )
        refined_by_openai = False
    else:
        if not prompt or not prompt.strip():
            raise ValueError("prompt is required when mode is 'prompt'.")
        refined = refine_music_prompt(
            prompt=prompt,
            song_name=song_name,
            style=style,
        )
        final_prompt = _add_music_context(
            refined["refined_prompt"],
            song_name=song_name,
            style=style,
            selected_styles=selected_styles or [],
            instrumental=instrumental,
        )
        estimated_duration_seconds = refined["estimated_duration_seconds"]
        composition_plan = None
        refined_by_openai = True

    audio_bytes, content_type = _compose_music(
        prompt=None if composition_plan else final_prompt,
        composition_plan=composition_plan,
        duration_seconds=estimated_duration_seconds,
        instrumental=False,
    )
    uploaded = upload_bytes(
        audio_bytes,
        folder="music/generated",
        filename=f"{_slugify(song_name or normalized_mode + '-music')}.mp3",
        content_type=content_type,
    )

    return {
        "status": "completed",
        "source_type": "text",
        "mode": normalized_mode,
        "song_name": song_name,
        "style": selected_styles or style,
        "instrumental": instrumental,
        "refined_by_openai": refined_by_openai,
        "estimated_duration_seconds": estimated_duration_seconds,
        "final_prompt": final_prompt,
        "composition_plan": composition_plan,
        "audio": uploaded,
    }


def enhance_uploaded_audio(
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    prompt: str,
) -> dict:
    if _should_convert_voice_to_song(prompt):
        raise ValueError(
            "This endpoint preserves the uploaded voice. Turning spoken voice "
            "into a full song with the same exact voice is not supported by the "
            "current ElevenLabs Music flow. Use a cleanup/enhancement prompt, "
            "or use /api/v1/music/text-to-music when an AI-generated singing "
            "voice is acceptable."
        )

    enhanced_bytes, enhanced_content_type = _isolate_audio(
        audio_bytes=audio_bytes,
        filename=filename,
        content_type=content_type,
    )

    if _should_add_background_music(prompt):
        mixed_bytes = _add_background_music_to_voice(
            voice_bytes=enhanced_bytes,
            user_prompt=prompt,
        )
        uploaded = upload_bytes(
            mixed_bytes,
            folder="music/enhanced-with-background",
            filename=f"{_slugify(filename or 'enhanced-audio')}.mp3",
            content_type="audio/mpeg",
        )

        return {
            "status": "completed",
            "source_type": "audio",
            "action": "enhance_audio_with_background_music",
            "prompt": prompt,
            "original_filename": filename,
            "voice_preserved": True,
            "audio": uploaded,
        }

    uploaded = upload_bytes(
        enhanced_bytes,
        folder="music/enhanced",
        filename=f"{_slugify(filename or 'enhanced-audio')}.mp3",
        content_type=enhanced_content_type,
    )

    return {
        "status": "completed",
        "source_type": "audio",
        "action": "enhance_audio",
        "prompt": prompt,
        "original_filename": filename,
        "audio": uploaded,
    }


def _add_background_music_to_voice(
    *,
    voice_bytes: bytes,
    user_prompt: str,
) -> bytes:
    if not shutil.which("ffmpeg"):
        raise ValueError(
            "Adding background music while preserving the uploaded voice requires "
            "FFmpeg on the server. Install FFmpeg and make sure the ffmpeg command "
            "is available in PATH."
        )

    try:
        from pydub import AudioSegment
    except ImportError as exc:
        raise ValueError(
            "Adding background music requires the pydub package. Run "
            "`pip install -r requirements.txt`."
        ) from exc

    voice = AudioSegment.from_file(BytesIO(voice_bytes))
    duration_seconds = _background_music_duration_seconds(len(voice))
    music_prompt = _background_music_prompt(user_prompt)
    music_bytes, _ = _compose_music(
        prompt=music_prompt,
        composition_plan=None,
        duration_seconds=duration_seconds,
        instrumental=True,
    )
    background = AudioSegment.from_file(BytesIO(music_bytes))
    background = _fit_audio_to_duration(background, len(voice)) - 18
    voice = voice + 2

    mixed = background.overlay(voice)
    output = BytesIO()
    mixed.export(output, format="mp3", bitrate="128k")
    return output.getvalue()


def _background_music_duration_seconds(voice_duration_ms: int) -> int:
    seconds = math.ceil(voice_duration_ms / 1000)
    return max(30, min(seconds, 300))


def _background_music_prompt(user_prompt: str) -> str:
    return (
        "Create soft instrumental background music only, no vocals, no lyrics. "
        "The music should sit quietly under a spoken or sung voice without "
        "overpowering it. User direction: "
        f"{user_prompt.strip()}"
    )


def _fit_audio_to_duration(audio, duration_ms: int):
    if len(audio) >= duration_ms:
        return audio[:duration_ms]

    loops = math.ceil(duration_ms / len(audio))
    return (audio * loops)[:duration_ms]


def _compose_music(
    *,
    prompt: str | None,
    composition_plan: dict | None,
    duration_seconds: int,
    instrumental: bool,
) -> tuple[bytes, str]:
    import requests

    settings = get_settings()
    payload = {
        "model_id": settings.eleven_labs_music_model,
    }
    if composition_plan:
        payload["composition_plan"] = composition_plan
    else:
        payload.update(
            {
                "prompt": prompt,
                "music_length_ms": duration_seconds * 1000,
                "force_instrumental": instrumental,
            }
        )

    response = requests.post(
        f"{ELEVEN_LABS_BASE_URL}/music",
        params={"output_format": "mp3_44100_128"},
        headers={
            "xi-api-key": get_eleven_labs_api_key(),
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=300,
    )
    response.raise_for_status()
    return response.content, response.headers.get("content-type", "audio/mpeg")


def _isolate_audio(
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
) -> tuple[bytes, str]:
    import requests

    provider_audio_bytes, provider_filename, provider_content_type = (
        _prepare_audio_for_provider(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
        )
    )

    response = requests.post(
        f"{ELEVEN_LABS_BASE_URL}/audio-isolation",
        headers={"xi-api-key": get_eleven_labs_api_key()},
        files={
            "audio": (
                provider_filename,
                provider_audio_bytes,
                provider_content_type,
            )
        },
        data={"file_format": "other"},
        timeout=300,
    )
    response.raise_for_status()
    return response.content, response.headers.get("content-type", "audio/mpeg")


def _prepare_audio_for_provider(
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
) -> tuple[bytes, str, str]:
    normalized_filename = filename or "audio"
    normalized_content_type = _normalize_audio_content_type(content_type)

    if normalized_content_type == "audio/mpeg":
        return audio_bytes, _ensure_extension(normalized_filename, ".mp3"), "audio/mpeg"

    if not shutil.which("ffmpeg"):
        return audio_bytes, normalized_filename, normalized_content_type

    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(BytesIO(audio_bytes))
        output = BytesIO()
        audio.export(output, format="mp3", bitrate="128k")
        return output.getvalue(), f"{_slugify(normalized_filename)}.mp3", "audio/mpeg"
    except Exception:
        return audio_bytes, normalized_filename, normalized_content_type


def _normalize_audio_content_type(content_type: str | None) -> str:
    if not content_type:
        return "application/octet-stream"
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


def _ensure_extension(filename: str, extension: str) -> str:
    if filename.lower().endswith(extension):
        return filename
    return f"{_slugify(filename)}{extension}"


def _should_add_background_music(prompt: str) -> bool:
    lowered = prompt.lower()
    add_music_phrases = [
        "add background music",
        "add soft music",
        "add soft background music",
        "background music",
        "music in the background",
        "add instrumental",
        "add instruments",
    ]
    remove_music_phrases = [
        "remove background music",
        "remove music",
    ]
    return any(phrase in lowered for phrase in add_music_phrases) and not any(
        phrase in lowered for phrase in remove_music_phrases
    )


def _should_convert_voice_to_song(prompt: str) -> bool:
    lowered = prompt.lower()
    cleanup_phrases = [
        "remove background music",
        "remove background",
        "remove noise",
        "noise removal",
        "clean audio",
        "clear audio",
        "enhance audio",
        "make it clear",
        "professional quality",
        "isolate voice",
        "voice isolation",
    ]
    creation_phrases = [
        "turn into a song",
        "convert into a song",
        "make a song",
        "create a song",
        "generate a song",
        "compose a song",
        "make music",
        "create music",
        "generate music",
        "compose music",
        "lyrics to song",
        "lyric to song",
        "voice to song",
        "song",
        "melody",
        "beat",
    ]

    if any(phrase in lowered for phrase in cleanup_phrases) and not any(
        phrase in lowered for phrase in creation_phrases
    ):
        return False

    return any(phrase in lowered for phrase in creation_phrases)


def _build_lyrics_music_prompt(
    *,
    lyrics: str,
    song_name: str | None,
    style: str | None,
    instrumental: bool,
) -> str:
    parts = []
    if song_name:
        parts.append(f"Song title: {song_name}.")
    if style:
        parts.append(f"Style: {style}.")
    if instrumental:
        parts.append(
            "Create a full song using these exact lyrics with lead vocals and "
            "instrumental background music."
        )
    else:
        parts.append(
            "Create a vocal-only song using these exact lyrics. Do not add "
            "instrumental background music or backing track."
        )
    parts.append(f"Lyrics:\n{lyrics.strip()}")
    return "\n".join(parts)


def _build_lyrics_composition_plan(
    *,
    lyrics: str,
    duration_seconds: int,
    song_name: str | None,
    style: str | None,
    instrumental: bool,
) -> dict:
    stanzas = _split_lyrics_into_stanzas(lyrics)
    section_duration_ms = _split_duration(duration_seconds * 1000, len(stanzas))
    positive_styles = _positive_music_styles(style, instrumental)
    negative_styles = ["instrumental only", "spoken word only"]
    if instrumental:
        negative_styles = ["instrumental only", "spoken word only", "a cappella only"]

    chunks = []
    for index, stanza in enumerate(stanzas):
        section_name = _section_name(index, len(stanzas))
        chunks.append(
            {
                "text": f"[{section_name}]\n{stanza}",
                "duration_ms": section_duration_ms[index],
                "positive_styles": positive_styles,
                "negative_styles": negative_styles,
                "context_adherence": "high",
            }
        )

    return {"chunks": chunks}


def _split_lyrics_into_stanzas(lyrics: str) -> list[str]:
    stanzas = [
        stanza.strip()
        for stanza in re.split(r"\n\s*\n", lyrics.strip())
        if stanza.strip()
    ]
    if stanzas:
        return stanzas
    return [lyrics.strip()]


def _split_duration(total_ms: int, count: int) -> list[int]:
    count = max(count, 1)
    base = max(3000, int(total_ms / count))
    durations = [base for _ in range(count)]
    durations[-1] += total_ms - sum(durations)
    return [max(3000, duration) for duration in durations]


def _positive_music_styles(style: str | None, instrumental: bool) -> list[str]:
    styles = [
        item.strip()
        for item in re.split(r"[,;]", style or "")
        if item.strip()
    ]
    if instrumental:
        styles.extend(
            [
                "clear emotional lead vocals singing the provided lyrics",
                "rich background instruments",
                "polished studio production",
                "balanced vocal mix with full instrumental backing",
            ]
        )
    else:
        styles.extend(
            [
                "clear emotional lead vocals singing the provided lyrics",
                "vocal-only performance",
                "a cappella style",
                "no instrumental backing track",
            ]
        )
    return styles[:50]


def _section_name(index: int, total: int) -> str:
    if total == 1:
        return "Verse"
    if index == total - 1:
        return "Chorus"
    return f"Verse {index + 1}"


def _add_music_context(
    prompt: str,
    *,
    song_name: str | None,
    style: str | None,
    selected_styles: list[str],
    instrumental: bool,
) -> str:
    parts = []
    if song_name:
        parts.append(f"Song title: {song_name}.")
    if style:
        parts.append(f"Style: {style}.")
    if instrumental:
        if selected_styles:
            parts.append(
                "Use lead vocals singing generated lyrics with instrumental "
                "background music built only around these selected styles: "
                f"{', '.join(selected_styles)}."
            )
        else:
            parts.append(
                "Use lead vocals singing generated lyrics with suitable "
                "instrumental background music."
            )
    elif selected_styles:
        parts.append(
            "Use lead vocals singing generated lyrics only. Do not add the "
            f"selected styles as instruments: {', '.join(selected_styles)}. "
            "Do not add background music, instruments, drums, percussion, or "
            "backing track."
        )
    else:
        parts.append(
            "Use lead vocals singing generated lyrics only. Do not add background "
            "music, instruments, drums, percussion, or backing track."
        )
    parts.append(prompt.strip())
    return "\n".join(parts)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "audio"
