from fastapi import APIRouter, UploadFile, File, Form
from starlette.concurrency import run_in_threadpool

from Service.gemini.generation_service import generate_image_to_diamond_video

router = APIRouter()


@router.post(
    "/image-to-video",
    summary="Generate diamond motion video from image",
    operation_id="generateDiamondVideoFromImage",
)
async def image_to_video(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    duration_seconds: int = Form(5, ge=4, le=8),
    aspect_ratio: str = Form("16:9"),
):
    image_bytes = await image.read()
    return await run_in_threadpool(
        generate_image_to_diamond_video,
        image_bytes=image_bytes,
        filename=image.filename or "source-image.png",
        mime_type=image.content_type or "image/png",
        prompt=prompt,
        duration_seconds=duration_seconds,
        aspect_ratio=aspect_ratio,
    )
