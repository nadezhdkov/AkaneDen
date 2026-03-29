"""
EmotionAnalyzer — Análise de emoções baseada em padrões textuais da Persona.

Detecta emoções no texto para:
1. Selecionar expressões faciais no VTube Studio
2. Escolher motor TTS adequado
3. Ajustar parâmetros de lip sync

Compila os padrões Regex carregados da `PersonaProfile` em runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from akane_den.core.models.persona import PersonaProfile


@dataclass
class EmotionResult:
    """Resultado da análise emocional."""
    emotion: str
    score: float
    triggers: list[str]


class EmotionAnalyzer:
    """Analisador de emoções baseado em padrões textuais da persona.

    Analisa texto e retorna a emoção dominante com score de intensidade.
    """

    def __init__(self, profile: "PersonaProfile") -> None:
        self._patterns: dict[str, list[re.Pattern]] = {}
        
        # Compila os patterns do Profile carregado dinamicamente
        for emotion, regex_list in profile.emotion_patterns.items():
            compiled_list = []
            for pattern_str in regex_list:
                try:
                    compiled_list.append(re.compile(pattern_str))
                except re.error as e:
                    logger.error(f"Padrão Regex inválido para '{emotion}': {pattern_str} - {e}")
            
            if compiled_list:
                self._patterns[emotion] = compiled_list
        
        logger.debug(f"EmotionAnalyzer compilou categorias: {list(self._patterns.keys())}")

    def analyze(self, text: str) -> tuple[str, float]:
        """Analisa texto e retorna (emoção, score).

        Args:
            text: Texto a ser analisado.

        Returns:
            Tupla (emoção_dominante, score_0_a_1).
        """
        result = self.analyze_detailed(text)
        return result.emotion, result.score

    def analyze_detailed(self, text: str) -> EmotionResult:
        """Análise detalhada com triggers encontrados.

        Args:
            text: Texto a ser analisado.

        Returns:
            EmotionResult com emoção, score, e lista de triggers.
        """
        if not text or not text.strip():
            return EmotionResult(emotion="neutro", score=0.0, triggers=[])

        scores: dict[str, float] = {}
        triggers: dict[str, list[str]] = {}

        for emotion, patterns in self._patterns.items():
            emotion_triggers = []
            for pattern in patterns:
                matches = pattern.findall(text)
                if matches:
                    emotion_triggers.extend(
                        m if isinstance(m, str) else m[0] for m in matches
                    )
            if emotion_triggers:
                # Score baseado na quantidade e variedade de triggers
                raw_score = len(emotion_triggers) / max(len(patterns), 1)
                scores[emotion] = min(raw_score, 1.0)
                triggers[emotion] = emotion_triggers

        if not scores:
            return EmotionResult(emotion="neutro", score=0.0, triggers=[])

        # Emoção dominante = maior score
        dominant = max(scores, key=scores.get)
        score = scores[dominant]

        logger.debug(
            f"Emoção detectada: {dominant} (score={score:.2f}) "
            f"triggers={triggers.get(dominant, [])[:3]}"
        )

        return EmotionResult(
            emotion=dominant,
            score=score,
            triggers=triggers.get(dominant, []),
        )
