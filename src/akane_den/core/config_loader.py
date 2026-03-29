"""
ConfigLoader — Carrega config.yaml e valida com Pydantic.

Substitui o loader frágil que retornava dicts sem validação.
Agora retorna um AkaneConfig tipado e validado.

"Pelo menos agora se você errar a config, vai saber ANTES
de rodar, não no meio do processamento, velho!" — Akane
"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from akane_den.core.config import AkaneConfig


def load_config(config_path: str | Path | None = None) -> AkaneConfig:
    """Carrega config.yaml e valida com Pydantic.

    Args:
        config_path: Caminho para config.yaml. Se None, procura na raiz do projeto.

    Returns:
        AkaneConfig validado.

    Raises:
        pydantic.ValidationError: Se a config contém valores inválidos.
    """
    if config_path is None:
        # Procura na raiz do projeto (3 níveis acima de src/akane_den/core/)
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        config_path = base_dir / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        logger.warning(
            f"config.yaml não encontrado em '{config_path}'. Usando defaults completos."
        )
        return AkaneConfig()

    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        # Extrai a seção 'akane' (compatível com v2.0)
        akane_data = raw.get("akane", raw)

        # Compatibilidade: mapeia campos antigos para novos
        akane_data = _migrate_v2_config(akane_data)

        config = AkaneConfig(**akane_data)
        logger.info(f"Config carregado de: {config_path}")
        logger.debug(f"Provider LLM: {config.brain.provider} ({config.brain.active_model})")
        logger.debug(f"Provider TTS: {config.tts.default_engine}")
        logger.debug(f"Provider ASR: {config.asr.provider}")
        return config

    except Exception as e:
        logger.error(f"Erro ao carregar config.yaml: {e}")
        logger.warning("Usando configuração padrão como fallback.")
        return AkaneConfig()


def _migrate_v2_config(data: dict) -> dict:
    """Migra campos do config v2.0 para o formato v3.0.

    Garante compatibilidade retroativa para quem atualizar
    sem reescrever o config.yaml inteiro.
    """
    # v2: stt_model → v3: asr.model_size
    if "stt_model" in data and "asr" not in data:
        data["asr"] = {
            "model_size": data.pop("stt_model"),
            "device": data.pop("stt_device", "cpu"),
        }
    elif "stt_model" in data:
        data.setdefault("asr", {})
        data["asr"].setdefault("model_size", data.pop("stt_model"))
        if "stt_device" in data:
            data["asr"].setdefault("device", data.pop("stt_device"))

    # v2: brain.model → v3: brain.gemini_model (se provider=gemini)
    if "brain" in data and isinstance(data["brain"], dict):
        brain = data["brain"]
        if "model" in brain and "provider" not in brain:
            model_name = brain.pop("model")
            brain["provider"] = "gemini"
            brain["gemini_model"] = model_name

    return data
