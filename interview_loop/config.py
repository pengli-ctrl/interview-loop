import os
from pathlib import Path

import streamlit as st

from interview_loop.scenarios import get_default_registry


def _get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, default)).strip()


LLM_API_KEY = _get_secret("deepseek_api_key")
LLM_BASE_URL = _get_secret("deepseek_base_url", "https://api.deepseek.com/v1")
LLM_MODEL = _get_secret("deepseek_model", "deepseek-chat")
VOLC_API_KEY = _get_secret("volc_api_key")
VOLC_APPID = _get_secret("volc_appid")
VOLC_TOKEN = _get_secret("volc_token")
VOLC_TTS_RESOURCE_ID = _get_secret("volc_tts_resource_id", "seed-tts-2.0")
VOLC_ASR_RESOURCE_ID = _get_secret("volc_asr_resource_id", "volc.seedasr.auc")
VOICE_TYPE = _get_secret("volc_voice_type", "zh_female_vv_uranus_bigtts")

BASE_DIR = Path(__file__).resolve().parent.parent
SAVE_DIR = BASE_DIR / "interview_sessions"
SAVE_DIR.mkdir(parents=True, exist_ok=True)
GLOBAL_STATS_PATH = BASE_DIR / "weak_stats_mode.json"
RECORD_DIR = BASE_DIR / "面试记录"
RECORD_DIR.mkdir(parents=True, exist_ok=True)
MAX_RESUME_BYTES = 10 * 1024 * 1024
DEMO_MODE = _get_secret("demo_mode", "false").lower() in {"1", "true", "yes", "on"}
ADMIN_MODE = _get_secret("admin_mode", "false").lower() in {"1", "true", "yes", "on"}

SCENARIO_REGISTRY = get_default_registry()
MODE_CONFIG = SCENARIO_REGISTRY.legacy_mode_config()
MODE_LIST = SCENARIO_REGISTRY.interview_rounds()
STYLE_LIST = SCENARIO_REGISTRY.styles()

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_CACHE_NAME = "models--sentence-transformers--all-MiniLM-L6-v2"
