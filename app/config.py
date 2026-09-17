from dataclasses import dataclass
import os


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    api_key: str = os.getenv("API_KEY", "")
    model: str = os.getenv("MAIA_MODEL", "maia3-5m")
    device: str = os.getenv("MAIA_DEVICE", "cpu")
    use_amp: bool = _bool("MAIA_USE_AMP", False)
    preload_model: bool = _bool("PRELOAD_MODEL", True)
    startup_timeout_seconds: float = float(os.getenv("STARTUP_TIMEOUT_SECONDS", "240"))
    max_deadline_ms: int = int(os.getenv("MAX_DEADLINE_MS", "15000"))


settings = Settings()
