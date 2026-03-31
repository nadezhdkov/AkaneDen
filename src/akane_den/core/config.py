"""
Config — Modelos Pydantic para configuração tipada e validada.

Substitui o carregamento frágil de dicts YAML por modelos com
validação de tipos, valores padrão e constraints.

"Se você errar um campo nessa config, eu vou saber EXATAMENTE
o que está errado. Sem mais 'KeyError: not found', baka!" — Akane
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Sub-configs por domínio
# ──────────────────────────────────────────────


class TTSConfig(BaseModel):
    """Configuração do motor de Text-to-Speech."""

    default_engine: Literal["edge", "elevenlabs", "sherpa"] = "edge"

    # Edge-TTS (grátis, sem limites)
    edge_voice: str = "pt-BR-ThalitaNeural"
    edge_pitch: str = "+12Hz"
    edge_rate: str = "+10%"

    # ElevenLabs (premium, ativado em picos emocionais)
    elevenlabs_voice_id: str = "MEJe6hPrI48Kt2lFuVe3"
    elevenlabs_model: str = "eleven_flash_v2_5"

    # Threshold de emoção para ativar motor premium
    emotion_threshold: float = Field(0.7, ge=0.0, le=1.0)

    # Sherpa-onnx TTS (local, opcional)
    sherpa_model_path: str = ""


class ASRConfig(BaseModel):
    """Configuração do motor de Speech-to-Text."""

    provider: Literal["whisper", "sherpa", "groq_whisper"] = "whisper"
    model_size: str = "small"
    device: Literal["cpu", "cuda"] = "cpu"
    language: str = "pt"

    # Sherpa-onnx ASR settings (SenseVoiceSmall int8)
    sherpa_model_path: str = ""
    sherpa_tokens_path: str = ""

    # Groq Whisper (API) settings
    groq_whisper_model: str = "whisper-large-v3-turbo"


class BrainConfig(BaseModel):
    """Configuração do cérebro LLM."""

    provider: Literal["gemini", "groq", "ollama", "openai"] = "gemini"
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_history: int = Field(50, ge=5, le=500)

    # Gemini settings (default)
    gemini_model: str = "gemini-2.5-flash"

    # Groq settings
    groq_model: str = "llama-3.3-70b-versatile"
    groq_api_base: str = ""

    # Ollama settings
    ollama_model: str = "llama3.2"
    ollama_base_url: str = "http://localhost:11434"

    # OpenAI settings
    openai_model: str = "gpt-4o-mini"
    openai_api_base: str = ""

    @property
    def active_model(self) -> str:
        """Retorna o modelo ativo baseado no provider selecionado."""
        model_map = {
            "gemini": self.gemini_model,
            "groq": self.groq_model,
            "ollama": self.ollama_model,
            "openai": self.openai_model,
        }
        return model_map.get(self.provider, self.gemini_model)


class VisionConfig(BaseModel):
    """Configuração da skill de visão computacional."""

    enabled: bool = True
    provider: Literal["gemini", "ollama"] = "gemini"
    auto_capture_interval: int = Field(0, ge=0)
    
    # Gemini settings
    gemini_model: str = "gemini-2.5-flash"

    # Ollama settings
    vision_model: str = "llama3.2-vision"
    ollama_base_url: str = "http://localhost:11434"


class VTubeConfig(BaseModel):
    """Configuração do VTube Studio e avatar."""

    port: int = Field(8001, ge=1, le=65535)
    mouse_tracking: bool = True
    mouse_sensitivity: float = Field(1.0, ge=0.1, le=5.0)
    lip_sync: bool = True
    lip_sensitivity: float = Field(1.5, ge=0.1, le=5.0)
    lip_smoothing: float = Field(0.4, ge=0.0, le=1.0)


class MemoryConfig(BaseModel):
    """Configuração de memória de longo prazo.

    Preparada para integração futura com Letta (MemGPT).
    """

    enabled: bool = True
    backend: Literal["chromadb", "letta", "none"] = "chromadb"
    db_path: str = "local_chroma_db"
    embedding_model: str = "all-MiniLM-L6-v2"

    # Letta (MemGPT) settings — para integração futura
    letta_base_url: str = "http://localhost:8283"
    letta_agent_name: str = "akane"


class MCPConfig(BaseModel):
    """Configuração do Model Context Protocol (MCP)."""

    enabled: bool = False
    tools: list[str] = Field(default_factory=lambda: ["duckduckgo_search"])


class VADConfig(BaseModel):
    """Configuração de Voice Activity Detection.

    DESATIVADO por padrão. O modo primário é PTT (Push-to-Talk).
    VAD é um fallback opcional para uso hands-free.
    """

    enabled: bool = False
    provider: Literal["silero"] = "silero"
    threshold: float = Field(0.5, ge=0.1, le=0.9)
    min_speech_ms: int = Field(250, ge=50, le=2000)
    min_silence_ms: int = Field(1000, ge=200, le=5000)
    window_size_ms: int = Field(30, ge=10, le=100)


class DashboardConfig(BaseModel):
    """Configuração do Web Dashboard."""

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(8080, ge=1, le=65535)


class TwitchConfig(BaseModel):
    """Configuração de integração com a Twitch."""

    enabled: bool = False
    oauth_token: str = ""
    channel_name: str = ""
    cooldown: int = Field(10, ge=0)


# ──────────────────────────────────────────────
# Config raiz
# ──────────────────────────────────────────────


class AkaneConfig(BaseModel):
    """Configuração raiz do AkaneDen — validada e tipada por Pydantic.

    Todos os campos têm valores padrão sensatos. O config.yaml do
    usuário sobrescreve apenas o que ele customizar.
    """

    ptt_key: str = "f2"
    input_mode: Literal["ptt", "vad"] = "ptt"
    persona: str = "akane_default"

    tts: TTSConfig = Field(default_factory=TTSConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    brain: BrainConfig = Field(default_factory=BrainConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    vtube: VTubeConfig = Field(default_factory=VTubeConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    vad: VADConfig = Field(default_factory=VADConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    twitch: TwitchConfig = Field(default_factory=TwitchConfig)

    model_config = {"extra": "ignore"}
