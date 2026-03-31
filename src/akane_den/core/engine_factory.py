"""
EngineFactory — Fábrica de motores de IA.

Instancia o provedor correto (LLM, TTS, ASR) baseado na configuração.
Usa o padrão Registry para extensibilidade: novos provedores podem
ser registrados sem modificar a factory.

"Eu mesma escolho qual cérebro usar! Não é você que decide
qual motor me move, baka. Eu sou uma máquina de elite!" — Akane
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from akane_den.core.config import AkaneConfig
from akane_den.core.engines.asr_engine import (
    ASREngine,
    GroqWhisperASREngine,
    SherpaOnnxASREngine,
    WhisperASREngine,
)
from akane_den.core.engines.llm_engine import (
    GeminiLLMEngine,
    GroqLLMEngine,
    LLMEngine,
    OllamaLLMEngine,
    OpenAILLMEngine,
)
from akane_den.core.engines.tts_engine import (
    EdgeTTSEngine,
    ElevenLabsTTSEngine,
    TTSEngine,
)


class EngineFactory:
    """Fábrica de motores de IA — instancia provedores a partir do config.

    Suporta registro dinâmico de novos provedores em runtime.
    """

    # Registry estático: nome -> classe
    _LLM_REGISTRY: dict[str, type[LLMEngine]] = {
        "gemini": GeminiLLMEngine,
        "groq": GroqLLMEngine,
        "ollama": OllamaLLMEngine,
        "openai": OpenAILLMEngine,
    }

    _TTS_REGISTRY: dict[str, type[TTSEngine]] = {
        "edge": EdgeTTSEngine,
        "elevenlabs": ElevenLabsTTSEngine,
    }

    _ASR_REGISTRY: dict[str, type[ASREngine]] = {
        "whisper": WhisperASREngine,
        "sherpa": SherpaOnnxASREngine,
        "groq_whisper": GroqWhisperASREngine,
    }

    # ── Registro dinâmico ──

    @classmethod
    def register_llm(cls, name: str, engine_class: type[LLMEngine]) -> None:
        """Registra um novo provedor de LLM."""
        cls._LLM_REGISTRY[name] = engine_class
        logger.info(f"LLM provider registrado: {name} -> {engine_class.__name__}")

    @classmethod
    def register_tts(cls, name: str, engine_class: type[TTSEngine]) -> None:
        """Registra um novo provedor de TTS."""
        cls._TTS_REGISTRY[name] = engine_class
        logger.info(f"TTS provider registrado: {name} -> {engine_class.__name__}")

    @classmethod
    def register_asr(cls, name: str, engine_class: type[ASREngine]) -> None:
        """Registra um novo provedor de ASR."""
        cls._ASR_REGISTRY[name] = engine_class
        logger.info(f"ASR provider registrado: {name} -> {engine_class.__name__}")

    # ── Criação de instâncias ──

    @classmethod
    def create_llm(cls, config: AkaneConfig) -> LLMEngine:
        """Cria LLM engine baseado no config.brain.provider."""
        provider = config.brain.provider
        engine_cls = cls._LLM_REGISTRY.get(provider)
        if not engine_cls:
            available = ", ".join(cls._LLM_REGISTRY.keys())
            raise ValueError(
                f"LLM provider '{provider}' não registrado, baka! "
                f"Disponíveis: {available}"
            )
        logger.info(
            f"Criando LLM: {provider} -> {engine_cls.__name__} "
            f"(model={config.brain.active_model})"
        )
        return engine_cls(config)

    @classmethod
    def create_tts(cls, config: AkaneConfig) -> TTSEngine:
        """Cria TTS engine baseado no config.tts.default_engine."""
        engine_name = config.tts.default_engine
        engine_cls = cls._TTS_REGISTRY.get(engine_name)
        if not engine_cls:
            available = ", ".join(cls._TTS_REGISTRY.keys())
            raise ValueError(
                f"TTS engine '{engine_name}' não registrada! "
                f"Disponíveis: {available}"
            )
        logger.info(f"Criando TTS: {engine_name} -> {engine_cls.__name__}")
        return engine_cls(config)

    @classmethod
    def create_elevenlabs_tts(cls, config: AkaneConfig) -> ElevenLabsTTSEngine:
        """Cria uma instância adicional de ElevenLabs para motor emocional."""
        return ElevenLabsTTSEngine(config)

    @classmethod
    def create_asr(cls, config: AkaneConfig) -> ASREngine:
        """Cria ASR engine baseado no config.asr.provider."""
        provider = config.asr.provider
        engine_cls = cls._ASR_REGISTRY.get(provider)
        if not engine_cls:
            available = ", ".join(cls._ASR_REGISTRY.keys())
            raise ValueError(
                f"ASR provider '{provider}' não registrado! "
                f"Disponíveis: {available}"
            )
        logger.info(f"Criando ASR: {provider} -> {engine_cls.__name__}")
        return engine_cls(config)

    # ── Informações ──

    @classmethod
    def list_providers(cls) -> dict[str, list[str]]:
        """Lista todos os provedores registrados."""
        return {
            "llm": list(cls._LLM_REGISTRY.keys()),
            "tts": list(cls._TTS_REGISTRY.keys()),
            "asr": list(cls._ASR_REGISTRY.keys()),
        }

    # ── VAD Factory ──

    @classmethod
    def create_vad(cls, config: AkaneConfig):
        """Cria VAD engine se habilitado no config.

        Retorna None se VAD está desativado.
        """
        if not config.vad.enabled:
            logger.info("VAD desativado (modo PTT primário).")
            return None

        from akane_den.core.engines.vad_engine import SileroVADEngine

        provider = config.vad.provider
        if provider == "silero":
            logger.info("Criando VAD: silero")
            return SileroVADEngine(config)

        raise ValueError(f"VAD provider '{provider}' não suportado!")
