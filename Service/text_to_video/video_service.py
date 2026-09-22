from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from Service.gemini.generation_service import generate_text_to_diamond_video

router = APIRouter()


class VideoRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    duration_seconds: int = Field(5, ge=4, le=8)
    aspect_ratio: str = Field("16:9", examples=["16:9", "9:16"])


@router.post(
    "/text-to-video",
    summary="Generate diamond motion video from text",
    operation_id="generateDiamondVideoFromText",
)
async def text_to_video(data: VideoRequest):
    return await run_in_threadpool(
        generate_text_to_diamond_video,
        prompt=data.prompt,
        duration_seconds=data.duration_seconds,
        aspect_ratio=data.aspect_ratio,
    )
