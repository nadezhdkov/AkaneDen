"""
Persona — System prompt dinâmico.

Constrói o prompt baseado no PersonaProfile carregado pelo Manager,
injetando contexto dinâmico (visão, barge-in, emoções) de forma flexível.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from akane_den.core.models.persona import PersonaProfile


def get_system_prompt(
    profile: "PersonaProfile",
    vision_context: str | None = None,
    webcam_context: str | None = None,
    barge_in: bool = False,
    extra_context: str | None = None,
) -> str:
    """Gera o system prompt dinâmico baseado no perfil atual.

    Args:
        profile: Objeto PersonaProfile validado na inicialização.
        vision_context: Descrição da tela do usuário.
        webcam_context: Descrição da webcam.
        barge_in: Se True, adiciona contexto de interrupção.
        extra_context: Qualquer contexto extra a ser adicionado.

    Returns:
        System prompt completo formatado.
    """
    parts = [profile.base_prompt]

    if vision_context and "vision_context" in profile.templates:
        try:
            parts.append(profile.templates["vision_context"].format(vision_context=vision_context))
            logger.debug(f"Vision context injetado: {vision_context[:80]}...")
        except KeyError:
            parts.append(f"{profile.templates['vision_context']}\n{vision_context}")

    if webcam_context and "webcam_context" in profile.templates:
        try:
            parts.append(profile.templates["webcam_context"].format(webcam_context=webcam_context))
            logger.debug(f"Webcam context injetado: {webcam_context[:80]}...")
        except KeyError:
            parts.append(f"{profile.templates['webcam_context']}\n{webcam_context}")

    if barge_in and "barge_in" in profile.templates:
        parts.append(profile.templates["barge_in"])
        logger.debug("Barge-in flag ativada no prompt.")

    if extra_context:
        # Se a persona definir template customizado de extra
        if "extra_context" in profile.templates:
            try:
                parts.append(profile.templates["extra_context"].format(extra_context=extra_context))
            except KeyError:
                parts.append(f"{profile.templates['extra_context']}\n{extra_context}")
        else:
            parts.append(f"\n## Contexto Adicional\n{extra_context}")

    return "\n".join(parts)
