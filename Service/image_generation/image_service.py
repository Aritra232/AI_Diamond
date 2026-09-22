from fastapi import APIRouter, HTTPException
from google.genai.errors import ClientError
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from Service.gemini.generation_service import generate_diamond_image

router = APIRouter()


class ImageRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=3,
        examples=["Diamond necklace product shot"],
    )
    aspect_ratio: str = Field("1:1", examples=["1:1", "16:9", "9:16"])
    number_of_images: int = Field(1, ge=1, le=4)


@router.post(
    "/generate",
    summary="Generate diamond image",
    operation_id="generateDiamondImage",
)
async def generate_image(data: ImageRequest):
    try:
        return await run_in_threadpool(
            generate_diamond_image,
            prompt=data.prompt,
            aspect_ratio=data.aspect_ratio,
            number_of_images=data.number_of_images,
        )
    except ClientError as exc:
        if exc.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Gemini image generation quota exceeded. Please wait and retry, "
                    "enable billing/increase quota for the Gemini API project, or "
                    "use another image model/API key."
                ),
            ) from exc

        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc
