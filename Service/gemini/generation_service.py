import base64
import mimetypes
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any

from google.genai import types

from Service.config import get_settings
from Service.gemini.gemini_client import get_client
from Service.storage.s3_service import upload_bytes, upload_file
from Service.storage.thumbnail import make_thumbnail


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


class ImageGenerationError(Exception):
    """Raised when *every* requested image failed."""

    def __init__(self, status_code: int, code: str, message: str, failures: list[dict]):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.failures = failures


def _error_status(exc: Exception) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value < 600:
            return value
    return None


def _classify_error(exc: Exception) -> tuple[int, str, str]:
    """Map a provider/storage exception to (http_status, error_code, message)."""
    status = _error_status(exc)

    if status == 429:
        return 429, "QUOTA_EXCEEDED", "Image generation quota exceeded. Please wait a moment and retry."
    if status in (400, 403):
        return 400, "PROVIDER_REJECTED", f"The image provider rejected this request: {exc}"
    if status is not None and status >= 500:
        return 502, "PROVIDER_ERROR", "The image provider had a temporary problem. Please retry."
    if isinstance(exc, RuntimeError) and "did not return an image" in str(exc):
        return 502, "NO_IMAGE_RETURNED", "The image provider returned no image for this prompt. Try rewording it."
    if exc.__class__.__module__.startswith(("botocore", "boto3")):
        return 502, "STORAGE_ERROR", "Generated image could not be saved to storage."
    return 500, "GENERATION_FAILED", f"Image generation failed: {exc}"


def _is_transient(exc: Exception) -> bool:
    status = _error_status(exc)
    if status is not None and status >= 500:
        return True
    return isinstance(exc, RuntimeError) and "did not return an image" in str(exc)


def _generate_one_image(client, settings, config, prompt: str, index: int) -> dict:
    """Generate, upload and thumbnail a single image. Raises on failure."""
    last_exc: Exception | None = None
    image_bytes = b""
    mime_type = "image/png"

    for attempt in range(settings.image_retries + 1):
        try:
            response = client.models.generate_content(
                model=settings.gemini_image_model,
                contents=prompt,
                config=config,
            )
            image_bytes, mime_type = _extract_generated_image(response)
            last_exc = None
            break
        except Exception as exc:  # noqa: BLE001 - classified by caller
            last_exc = exc
            if attempt < settings.image_retries and _is_transient(exc):
                time.sleep(1.5 * (attempt + 1))
                continue
            raise

    if last_exc is not None:
        raise last_exc

    extension = mimetypes.guess_extension(mime_type) or ".png"
    uploaded = upload_bytes(
        image_bytes,
        folder="diamond/images",
        filename=f"diamond-image-{index}{extension}",
        content_type=mime_type,
    )
    uploaded["index"] = index

    # A thumbnail problem must never fail the image itself.
    uploaded["thumbnail_url"] = None
    uploaded["thumbnail_key"] = None
    try:
        thumb_bytes, thumb_type, thumb_ext = make_thumbnail(
            image_bytes,
            max_px=settings.thumbnail_max_px,
            quality=settings.thumbnail_quality,
        )
        thumb = upload_bytes(
            thumb_bytes,
            folder="diamond/images/thumbs",
            filename=f"diamond-image-{index}-thumb{thumb_ext}",
            content_type=thumb_type,
        )
        uploaded["thumbnail_url"] = thumb["url"]
        uploaded["thumbnail_key"] = thumb["key"]
    except Exception as exc:  # noqa: BLE001
        print(f"[image] thumbnail failed for image {index}: {exc}")

    return uploaded


def generate_diamond_image(
    *,
    prompt: str,
    aspect_ratio: str = "1:1",
    number_of_images: int = 1,
) -> dict:
    """Generate ``number_of_images`` images in parallel with partial success.

    Returns ``status="completed"`` when all succeed, ``"partial"`` when some fail.
    Raises ImageGenerationError only if every image failed.
    """
    client = get_client()
    settings = get_settings()
    final_prompt = build_image_prompt(prompt)

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
        ),
    )

    images: list[dict] = []
    failed: list[dict] = []
    workers = max(1, min(number_of_images, settings.image_max_concurrency))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_generate_one_image, client, settings, config, final_prompt, index): index
            for index in range(1, number_of_images + 1)
        }
        for future, index in futures.items():
            try:
                images.append(future.result())
            except Exception as exc:  # noqa: BLE001
                status, code, message = _classify_error(exc)
                print(f"[image] image {index}/{number_of_images} failed ({code}): {exc}")
                failed.append(
                    {"index": index, "status_code": status, "code": code, "message": message}
                )

    images.sort(key=lambda item: item["index"])
    failed.sort(key=lambda item: item["index"])

    if not images:
        first = failed[0]
        raise ImageGenerationError(first["status_code"], first["code"], first["message"], failed)

    return {
        "status": "completed" if not failed else "partial",
        "prompt": prompt,
        "final_prompt": final_prompt,
        "model": settings.gemini_image_model,
        "requested": number_of_images,
        "images": images,
        "failed": failed,
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
