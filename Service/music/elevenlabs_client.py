from Service.config import get_settings


def get_eleven_labs_api_key() -> str:
    api_key = get_settings().eleven_labs_api_key
    if not api_key:
        raise RuntimeError("ELEVEN_LABS_API_KEY is not configured.")
    return api_key
