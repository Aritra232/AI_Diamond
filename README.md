# AI Diamond Video Generator

FastAPI backend for diamond-themed AI image generation, text-to-video, and image-to-video generation using Gemini/Veo, with generated assets uploaded to AWS S3.

## Endpoints

- `GET /` - API root
- `GET /health` - AI and storage configuration health
- `POST /api/v1/images/generate` - generate a diamond-themed image from a prompt
- `POST /api/v1/videos/text-to-video` - generate a diamond motion video from a prompt
- `POST /api/v1/videos/image-to-video` - generate a diamond motion video from an uploaded image and prompt
- `POST /api/v1/music/text-to-music` - generate music from a prompt or lyrics
- `POST /api/v1/music/enhance-audio` - enhance uploaded audio based on a user prompt

Swagger docs are available at `/docs`.

For image generation, the user prompt is used directly. Diamond styling and
motion details are only added by the video endpoints.

For music generation, `mode="lyrics"` uses the lyrics directly. `mode="prompt"`
uses OpenAI to refine the idea into a production-ready music prompt before
calling ElevenLabs. Duration is estimated automatically from the prompt or lyrics.
In prompt mode, the client can optionally provide `style` as a single selected
style string or an array of selected styles. If no style is selected, the backend
asks for generated lyrics/vocals without background instruments when
`instrumental=false`. If `instrumental=true`, the generated song uses vocals plus
instrumental background music. Selected styles guide that background arrangement.

Prompt mode without selected styles:

```json
{
  "mode": "prompt",
  "song_name": "Childhood Memories",
  "prompt": "Create a nostalgic childhood song with warm emotional vocals.",
  "style": [],
  "instrumental": false
}
```

Prompt mode with selected styles:

```json
{
  "mode": "prompt",
  "song_name": "Childhood Memories",
  "prompt": "Create a nostalgic childhood song with warm emotional vocals.",
  "style": ["Piano", "Violin", "Drums"],
  "instrumental": true
}
```

Audio enhancement accepts an uploaded audio file plus a required `prompt` form
field. This endpoint preserves the uploaded voice and is meant for cleanup,
noise removal, and clarity/professional-quality enhancement. If the prompt asks
to add background music, the backend generates soft instrumental music with
ElevenLabs and mixes it under the cleaned voice, preserving the uploaded voice.
This mixing step requires FFmpeg on the server. It will not convert spoken voice
into a full song with a different AI singing voice. Use `/api/v1/music/text-to-music`
when an AI-generated music track is acceptable.
Common formats such as `.mp3`, `.mpeg`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg`,
`.opus`, `.webm`, `.aiff`, and unknown binary uploads are accepted by the app
and sent with the best detected content type.

## Environment

Copy `.env.example` to `.env` and set:

```env
GEMINI_API_KEY=
OPENAI_API_KEY=
ELEVEN_LABS_API_KEY=
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

Run on port `4444`:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 4444
```

## Docker

Build and run with Docker Compose:

```bash
docker compose up --build
```

The API will be available at:

```text
http://127.0.0.1:4444/docs
```

Run in the background:

```bash
docker compose up --build -d
```

Stop:

```bash
docker compose down
```

The Docker image is multi-stage. The runtime image includes FFmpeg, which is
required for mixing uploaded voice audio with generated background music.

## Server Dependencies

Audio mixing for `/api/v1/music/enhance-audio` requires FFmpeg on the server or
VPS. Python packages alone are not enough because `pydub` uses the `ffmpeg`
binary to decode and export audio.

Ubuntu/Debian VPS:

```bash
sudo apt update
sudo apt install -y ffmpeg
ffmpeg -version
```

Dockerfile example:

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
```
