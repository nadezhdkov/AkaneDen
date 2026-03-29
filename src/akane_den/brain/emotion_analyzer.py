"""
EmotionAnalyzer — Análise de emoções baseada em padrões textuais.

Detecta emoções no texto da Akane para:
1. Selecionar expressões faciais no VTube Studio
2. Escolher motor TTS adequado (Edge vs ElevenLabs)
3. Ajustar parâmetros de lip sync

Migrado para loguru na v3.0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger


@dataclass
class EmotionResult:
    """Resultado da análise emocional."""
    emotion: str
    score: float
    triggers: list[str]


# ──────────────────────────────────────────────
# Padrões emocionais
# ──────────────────────────────────────────────

_EMOTION_PATTERNS: dict[str, list[re.Pattern]] = {
    "raiva": [
        re.compile(r"(?i)(baka|idiota|velho|incompetente|lixo)"),
        re.compile(r"(?i)(COMO É QUE É|QUE É ISSO|pisar no monitor)"),
        re.compile(r"(?i)(graduar|cuspindo cheitos|me irrita)"),
        re.compile(r"(?i)(golpe de martelo|punho digital)"),
        re.compile(r"[A-ZÀ-Ú]{4,}"),  # CAPS LOCK = gritando
        re.compile(r"!{2,}"),  # Múltiplas exclamações
    ],
    "vergonha": [
        re.compile(r"(?i)(b-baka|q-quem|n-não|h-humph)"),
        re.compile(r"(?i)(gaguej|desviar? o olhar|constrangiment)"),
        re.compile(r"(?i)(não pense que|não se acostume|não é como se)"),
        re.compile(r"(?i)(buffering|pane)"),
    ],
    "surpresa": [
        re.compile(r"(?i)(o qu[eê]|hein|sério|impossível)"),
        re.compile(r"(?i)(não acredito|como assim)"),
        re.compile(r"\?{2,}"),  # Múltiplas interrogações
    ],
    "alegria": [
        re.compile(r"(?i)(hehe|nyah|perfeito|excelente|bravo)"),
        re.compile(r"(?i)(faixa preta|mestre|elite)"),
        re.compile(r"(?i)(yosh|sugoi|kawaii)"),
    ],
    "tedio": [
        re.compile(r"(?i)(beta|molequice|básico|entediante)"),
        re.compile(r"(?i)(faixa branca|treino básico|óbvio)"),
        re.compile(r"(?i)(hmph|tsc|whatever)"),
    ],
}


class EmotionAnalyzer:
    """Analisador de emoções baseado em padrões textuais.

    Analisa texto e retorna a emoção dominante com score de intensidade.
    """

    def __init__(self) -> None:
        self._patterns = _EMOTION_PATTERNS

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
