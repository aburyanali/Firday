import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class AppConfig:
    app_name: str = os.getenv("APP_NAME", "NOVA OS")
    environment: str = os.getenv("APP_ENV", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    admin_api_key: Optional[str] = os.getenv("NOVA_ADMIN_API_KEY")
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    perplexity_api_key: Optional[str] = os.getenv("PERPLEXITY_API_KEY")
    elevenlabs_api_key: Optional[str] = os.getenv("ELEVENLABS_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    perplexity_model: str = os.getenv("PERPLEXITY_MODEL", "sonar-small-chat")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    provider_first_token_timeout_seconds: float = float(
        os.getenv("PROVIDER_FIRST_TOKEN_TIMEOUT_SECONDS", "2.0")
    )
    provider_request_timeout_seconds: float = float(
        os.getenv("PROVIDER_REQUEST_TIMEOUT_SECONDS", "25.0")
    )
    memory_db_path: str = os.getenv(
        "FRIDAY_MEMORY_DB_PATH",
        str(Path.home() / ".friday_memory.db"),
    )
    conversation_db_path: str = os.getenv(
        "FRIDAY_CONVERSATION_DB_PATH",
        str(BASE_DIR / "friday_memory.db"),
    )


config = AppConfig()


def create_openai_client(api_key: Optional[str] = None):
    from openai import OpenAI

    resolved_key = api_key or config.openai_api_key
    if not resolved_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Add it to your environment or local .env file."
        )
    return OpenAI(api_key=resolved_key)
