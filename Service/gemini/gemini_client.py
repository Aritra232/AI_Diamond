from functools import lru_cache

from google import genai

from Service.config import get_settings


@lru_cache
def get_client():
    api_key = get_settings().gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    return genai.Client(api_key=api_key)
