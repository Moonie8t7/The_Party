from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_path,
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API Keys - required
    anthropic_api_key: str
    openai_api_key: str
    gemini_api_key: str
    grok_api_key: str
    deepseek_api_key: str

    # WebSocket server
    ws_host: str = "localhost"
    ws_port: int = 8765

    # Overlay WebSocket server (browser source connects to this)
    overlay_host: str = "localhost"
    overlay_port: int = 8766

    # Router
    router_model: str = "claude-haiku-4-5-20251001"

    # Queue
    queue_max_size: int = 10
    trigger_cooldown_seconds: float = 3.0
    dedup_window_seconds: float = 5.0

    # Provider timeouts
    provider_timeout_seconds: float = 15.0
    provider_max_retries: int = 2

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_model_id: str = "eleven_turbo_v2_5"
    elevenlabs_stability: float = 0.5
    elevenlabs_similarity_boost: float = 0.75

    # Voice IDs - set in .env after selecting from ElevenLabs voice library
    voice_clauven: str = "PLACEHOLDER_CLAUVEN"
    voice_geptima: str = "PLACEHOLDER_GEPTIMA"
    voice_gemaux: str = "PLACEHOLDER_GEMAUX"
    voice_grokthar: str = "PLACEHOLDER_GROKTHAR"
    voice_deepwilla: str = "PLACEHOLDER_DEEPWILLA"

    # Speech
    inter_character_gap_seconds: float = 0.5

    # Logging
    log_level: str = "INFO"

    # Persistence
    transcript_path: str = "logs/transcript.jsonl"

    # Session context
    session_context_path: str = "session/session_context.txt"

    # Twitch API
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    twitch_broadcaster_login: str = "watchmoonie"

    # IGDB (uses same Twitch credentials)
    igdb_enabled: bool = True

    # Vision
    vision_enabled: bool = False
    vision_interval_seconds: float = 60.0
    vision_obs_host: str = "localhost"
    vision_obs_port: int = 4455
    vision_obs_password: str = ""
    vision_model: str = "gpt-4o"
    vision_max_tokens: int = 150
    vision_prompt: str = (
        "You are watching a live game stream. "
        "Describe what is currently happening on screen in 2-3 sentences. "
        "Be specific: mention the game state, what the player is doing, "
        "any notable UI elements (health, ammo, objectives), and the general "
        "situation. Do not speculate about what might happen next. "
        "Write in present tense. Be concise."
    )

    # Vision flickbook
    vision_burst_frames: int = 5
    vision_burst_interval_seconds: float = 2.0

    # Vision log
    vision_log_enabled: bool = True
    vision_log_max_context_entries: int = 5
    vision_log_max_file_entries: int = 100
    vision_log_path: str = "session/vision_log_{date}.txt"

    # STT
    stt_enabled: bool = False
    stt_model: str = "base"
    stt_device_index: int = -1
    stt_language: str = "en"
    stt_cooldown_seconds: float = 90.0
    stt_min_words: int = 5
    stt_reaction_model: str = "claude-haiku-4-5-20251001"


settings = Settings()
