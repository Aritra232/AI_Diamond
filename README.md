# AI Diamond Video Generator

FastAPI backend for diamond-themed AI image generation, text-to-video, and image-to-video generation using Gemini/Veo, with generated assets uploaded to AWS S3.

## Endpoints

- `GET /` - API root
- `GET /health` - AI and storage configuration health
- `POST /api/v1/images/generate` - generate a diamond-themed image from a prompt
- `POST /api/v1/videos/text-to-video` - generate a diamond motion video from a prompt
- `POST /api/v1/videos/image-to-video` - generate a diamond motion video from an uploaded image and prompt

Swagger docs are available at `/docs`.

For image generation, the user prompt is used directly. Diamond styling and
motion details are only added by the video endpoints.

## Environment

Copy `.env.example` to `.env` and set:

```env
GEMINI_API_KEY=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=
AWS_S3_BUCKET=
```

`AWS_S3_PUBLIC_BASE_URL` is optional. Use it if your bucket is served through CloudFront or a custom public URL.

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```
