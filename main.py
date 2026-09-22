from fastapi import FastAPI

from Service.config import get_settings
from Service.image_generation.image_service import router as image_router
from Service.image_to_video.image_video_service import router as image_video_router
from Service.text_to_video.video_service import router as text_video_router

settings = get_settings()

tags_metadata = [
    {
        "name": "Health",
        "description": "AI backend status and readiness endpoints.",
    },
    {
        "name": "Image Generation",
        "description": "Generate diamond-themed images from user prompts.",
    },
    {
        "name": "Text To Video",
        "description": "Generate diamond motion videos from user prompts.",
    },
    {
        "name": "Image To Video",
        "description": "Generate diamond motion videos from a user image and prompt.",
    },
]

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    openapi_tags=tags_metadata,
)


@app.get("/", tags=["Health"], summary="API root")
def root():
    return {
        "status": "running",
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"], summary="AI service health")
def health():
    return {
        "status": "healthy",
        "ai": {
            "provider": "gemini",
            "image_model": settings.gemini_image_model,
            "video_model": settings.gemini_video_model,
            "configured": bool(settings.gemini_api_key),
        },
        "storage": {
            "provider": "aws_s3",
            "bucket": settings.aws_s3_bucket,
            "configured": bool(settings.aws_s3_bucket),
        },
    }


app.include_router(
    image_router,
    prefix="/api/v1/images",
    tags=["Image Generation"],
)
app.include_router(
    text_video_router,
    prefix="/api/v1/videos",
    tags=["Text To Video"],
)
app.include_router(
    image_video_router,
    prefix="/api/v1/videos",
    tags=["Image To Video"],
)
