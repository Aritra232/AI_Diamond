import base64
import mimetypes
import os
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

from google.genai import types

from Service.config import get_settings
from Service.gemini.gemini_client import get_client
from Service.storage.s3_service import upload_bytes, upload_file


DIAMOND_STYLE = """
Visual style: a brilliant blue-white faceted diamond centered on a deep navy
cosmic background, golden orbital rings around it, tiny star particles, lens
glow, clean premium luxury look, high contrast, sharp crystal reflections.
"""

DIAMOND_MOTION_STYLE = """
Motion style: cinematic slow orbit around a glowing diamond, golden rings
rotating at different speeds, sparkling star particles drifting outward, subtle
camera push-in, premium jewelry ad lighting, smooth loop-friendly movement.
"""


def build_image_prompt(user_prompt: str) -> str:
    return user_prompt.strip()


def build_video_prompt(user_prompt: str) -> str:
    return f"{DIAMOND_STYLE}\n{DIAMOND_MOTION_STYLE}\nUser direction: {user_prompt}".strip()


def generate_diamond_image(
    *,
    prompt: str,
    aspect_ratio: str = "1:1",
    number_of_images: int = 1,
) -> dict:
    client = get_client()
    settings = get_settings()
    final_prompt = build_image_prompt(prompt)

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
        ),
    )

    images = []
    for index in range(1, number_of_images + 1):
        response = client.models.generate_content(
            model=settings.gemini_image_model,
            contents=final_prompt,
            config=config,
        )
        image_bytes, mime_type = _extract_generated_image(response)
        extension = mimetypes.guess_extension(mime_type) or ".png"
        uploaded = upload_bytes(
            image_bytes,
            folder="diamond/images",
            filename=f"diamond-image-{index}{extension}",
            content_type=mime_type,
        )
        images.append(uploaded)

    return {
        "status": "completed",
        "prompt": prompt,
        "final_prompt": final_prompt,
        "model": settings.gemini_image_model,
        "images": images,
    }


def _extract_generated_image(response) -> tuple[bytes, str]:
    for part in response.parts:
        inline_data = getattr(part, "inline_data", None)
        if inline_data is not None:
            mime_type = getattr(inline_data, "mime_type", None) or "image/png"
            data = inline_data.data
            if isinstance(data, str):
                data = base64.b64decode(data)
            return data, mime_type

        image = part.as_image()
        if image is not None:
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue(), "image/png"

    raise RuntimeError("Gemini did not return an image.")


def generate_text_to_diamond_video(
    *,
    prompt: str,
    duration_seconds: int = 5,
    aspect_ratio: str = "16:9",
) -> dict:
    settings = get_settings()
    final_prompt = build_video_prompt(prompt)
    operation = _start_video_generation(
        prompt=final_prompt,
        duration_seconds=duration_seconds,
        aspect_ratio=aspect_ratio,
    )
    return _finish_video_generation(
        operation,
        prompt=prompt,
        final_prompt=final_prompt,
        source_type="text",
        model=settings.gemini_video_model,
    )


def generate_image_to_diamond_video(
    *,
    image_bytes: bytes,
    filename: str,
    mime_type: str,
    prompt: str,
    duration_seconds: int = 5,
    aspect_ratio: str = "16:9",
) -> dict:
    settings = get_settings()
    final_prompt = build_video_prompt(prompt)

    source_image = _image_from_upload_bytes(
        image_bytes=image_bytes,
        filename=filename,
        mime_type=mime_type,
    )
    operation = _start_video_generation(
        prompt=final_prompt,
        duration_seconds=duration_seconds,
        aspect_ratio=aspect_ratio,
        image=source_image,
    )
    return _finish_video_generation(
        operation,
        prompt=prompt,
        final_prompt=final_prompt,
        source_type="image",
        model=settings.gemini_video_model,
    )


def _start_video_generation(
    *,
    prompt: str,
    duration_seconds: int,
    aspect_ratio: str,
    image: Any | None = None,
):
    client = get_client()
    settings = get_settings()
    config = types.GenerateVideosConfig(
        number_of_videos=1,
        duration_seconds=duration_seconds,
        aspect_ratio=aspect_ratio,
    )

    try:
        source_kwargs = {"prompt": prompt}
        if image is not None:
            source_kwargs["image"] = image
        source = types.GenerateVideosSource(**source_kwargs)
        return client.models.generate_videos(
            model=settings.gemini_video_model,
            source=source,
            config=config,
        )
    except TypeError:
        kwargs = {
            "model": settings.gemini_video_model,
            "prompt": prompt,
            "config": config,
        }
        if image is not None:
            kwargs["image"] = image
        return client.models.generate_videos(**kwargs)


def _finish_video_generation(
    operation,
    *,
    prompt: str,
    final_prompt: str,
    source_type: str,
    model: str,
) -> dict:
    client = get_client()
    operation = _wait_for_operation(operation)
    generated_video = operation.response.generated_videos[0]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        destination = tmp.name

    try:
        client.files.download(file=generated_video.video, destination=destination)
        uploaded = upload_file(
            destination,
            folder="diamond/videos",
            content_type="video/mp4",
        )
    finally:
        Path(destination).unlink(missing_ok=True)

    return {
        "status": "completed",
        "source_type": source_type,
        "prompt": prompt,
        "final_prompt": final_prompt,
        "model": model,
        "video": uploaded,
    }


def _wait_for_operation(operation):
    client = get_client()
    settings = get_settings()
    started_at = time.monotonic()

    while not operation.done:
        if time.monotonic() - started_at > settings.video_timeout_seconds:
            raise TimeoutError("Video generation timed out.")
        time.sleep(settings.video_poll_interval_seconds)
        operation = client.operations.get(operation)

    return operation


def _image_from_upload_bytes(*, image_bytes: bytes, filename: str, mime_type: str):
    suffix = Path(filename).suffix
    if not suffix:
        suffix = mimetypes.guess_extension(mime_type) or ".png"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(image_bytes)
        temp_path = tmp.name

    try:
        return types.Image.from_file(location=temp_path)
    finally:
        os.unlink(temp_path)
