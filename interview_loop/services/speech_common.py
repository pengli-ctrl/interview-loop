from interview_loop.config import VOLC_API_KEY, VOLC_APPID, VOLC_TOKEN
from interview_loop.services.common import require_config


def volc_auth_headers(service: str) -> dict[str, str]:
    """Support both the API-key and AppID + AccessToken auth modes."""
    if VOLC_API_KEY:
        return {"X-Api-Key": VOLC_API_KEY}

    require_config(VOLC_APPID, VOLC_TOKEN)
    common = {"X-Api-Access-Key": VOLC_TOKEN}
    if service == "tts":
        return {**common, "X-Api-App-Id": VOLC_APPID}
    return {**common, "X-Api-App-Key": VOLC_APPID}
