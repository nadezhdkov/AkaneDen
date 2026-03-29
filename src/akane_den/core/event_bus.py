"""
EventBus — Pub/Sub interno para comunicação desacoplada entre skills.

Permite que skills emitam e escutem eventos sem referências diretas,
mantendo a arquitetura modular e extensível.

Migrado de logging para loguru na v3.0.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from loguru import logger


class EventBus:
    """Barramento de eventos pub/sub leve para o sistema Akane.

    Eventos planejados:
        - user_speech_ready: PTTSkill -> STTSkill (audio_bytes)
        - user_text_ready: STTSkill -> Brain (text)
        - akane_response: Brain -> TTSSkill, ExpressionSkill (text, emotion)
        - emotion_detected: EmotionAnalyzer -> ExpressionSkill, TTSSkill (emotion, score)
        - screen_captured: ScreenVisionSkill -> Brain (description)
        - barge_in: PTTSkill -> TTSSkill (stop playback)
        - tts_speaking_start: TTSSkill -> LipSyncSkill (audio_path)
        - tts_speaking_stop: TTSSkill -> LipSyncSkill ()
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable]] = {}
        self._event_log: list[dict[str, Any]] = []

    def on(self, event: str, callback: Callable) -> None:
        """Registra um callback para um evento.

        O callback pode ser sync ou async — o emit() trata ambos.
        """
        self._listeners.setdefault(event, []).append(callback)
        logger.debug(f"Listener registrado: {event} -> {callback.__qualname__}")

    def off(self, event: str, callback: Callable) -> None:
        """Remove um callback de um evento."""
        if event in self._listeners:
            self._listeners[event] = [
                cb for cb in self._listeners[event] if cb != callback
            ]

    async def emit(
        self,
        event: str,
        data: dict | None = None,
        *,
        fire_and_forget: bool = False,
    ) -> None:
        """Emite um evento para todos os listeners registrados.

        Suporta callbacks sync e async. Erros em um listener não
        bloqueiam os demais.

        Args:
            event: Nome do evento.
            data: Dados do evento.
            fire_and_forget: Se True, listeners assíncronos são lançados
                via asyncio.create_task() sem bloquear o emit().
                Use para pipelines pesados (Brain/TTS) que não devem
                congelar o event loop.
        """
        listeners = self._listeners.get(event, [])
        if not listeners:
            return

        self._event_log.append({
            "event": event,
            "data": data,
            "listeners": len(listeners),
        })
        logger.debug(
            f"Evento emitido: '{event}' -> {len(listeners)} listener(s)"
            f"{' [fire_and_forget]' if fire_and_forget else ''}"
        )

        for cb in listeners:
            try:
                if asyncio.iscoroutinefunction(cb):
                    if fire_and_forget:
                        asyncio.create_task(
                            self._safe_invoke(cb, data, event)
                        )
                    else:
                        await cb(data)
                else:
                    cb(data)
            except Exception as e:
                logger.error(
                    f"Erro no listener de '{event}' ({cb.__qualname__}): {e}"
                )

    @staticmethod
    async def _safe_invoke(
        cb: Callable, data: dict | None, event: str
    ) -> None:
        """Wrapper seguro para tasks fire-and-forget — captura exceções."""
        try:
            await cb(data)
        except Exception as e:
            logger.error(
                f"Erro em task fire_and_forget de '{event}' "
                f"({cb.__qualname__}): {e}"
            )

    def has_listeners(self, event: str) -> bool:
        """Verifica se há listeners para um evento."""
        return bool(self._listeners.get(event))

    def get_stats(self) -> dict:
        """Retorna estatísticas do barramento."""
        return {
            "registered_events": list(self._listeners.keys()),
            "total_listeners": sum(len(cbs) for cbs in self._listeners.values()),
            "events_emitted": len(self._event_log),
        }

    def __repr__(self) -> str:
        return (
            f"<EventBus events={len(self._listeners)} "
            f"emitted={len(self._event_log)}>"
        )
