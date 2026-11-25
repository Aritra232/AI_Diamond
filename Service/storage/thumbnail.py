from io import BytesIO


def make_thumbnail(
    image_bytes: bytes,
    *,
    max_px: int = 720,
    quality: int = 80,
) -> tuple[bytes, str, str]:
    """Return (bytes, content_type, extension) of a WebP thumbnail.

    The longest side is scaled down to ``max_px``; smaller images are not upscaled.
    """
    from PIL import Image, ImageOps

    with Image.open(BytesIO(image_bytes)) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        buffer = BytesIO()
        img.save(buffer, format="WEBP", quality=quality, method=4)
    return buffer.getvalue(), "image/webp", ".webp"
