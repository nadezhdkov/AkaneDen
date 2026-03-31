"""
Conversation Pipeline — AkaneDen v3.5

Extrai a lógica de eventos do main.py para uma classe testável.
Conecta os eventos do EventBus (texto, barge-in, Twitch, timeout) 
ao cérebro (LangGraph) e motor de voz (TTS).
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from akane_den.core.config import AkaneConfig
from akane_den.core.service_context import ServiceContext
from akane_den.brain.graph_state import AkaneBrain
from akane_den.skills.voice.tts_skill import TTSSkill
from akane_den.skills.vision.screen_vision_skill import ScreenVisionSkill


class ConversationPipeline:
    """Pipelines encapsulados para os fluxos conversacionais."""

    def __init__(
        self,
        service: ServiceContext,
        brain: AkaneBrain,
        tts_skill: TTSSkill,
        vision_skill: ScreenVisionSkill | None,
        config: AkaneConfig,
    ) -> None:
        self._service = service
        self._brain = brain
        self._tts = tts_skill
        self._vision = vision_skill
        self._config = config

    def register_handlers(self) -> None:
        """Registra todos os listener no EventBus."""
        self._service.event_bus.on("user_text_ready", self.on_user_text)
        self._service.event_bus.on("barge_in", self.on_barge_in)
        self._service.event_bus.on("trigger_proactive", self.on_trigger_proactive)
        self._service.event_bus.on("twitch_message_received", self.on_twitch_message)
        logger.debug("Conversation pipeline handlers registrados.")

    async def on_user_text(self, data: dict[str, Any]) -> None:
        """Pipeline completo: texto → brain → TTS streaming.

        Protegido por timeout de 15s e error handling robusto.
        Roda como task independente via fire_and_forget.
        """
        user_text = data.get("text", "")
        if not user_text:
            return

        logger.info(f"Usuário: '{user_text}'")

        try:
            # Aumentamos o timeout geral de 30s para 180s, pois o tempo de playback do 
            # áudio da Akane (que faz parte deste loop) pode durar dezenas de segundos.
            async with asyncio.timeout(180):
                # Contexto visual
                vision_ctx = None
                if self._vision and self._config.vision.enabled:
                    vision_ctx = self._vision.last_description
                    
                    # Só força capture síncrono se NÃO temos cache algum
                    # (ex: primeiro uso após boot). Evita bloquear o usuário
                    # por 44s+ enquanto espera CPU inference.
                    if not vision_ctx:
                        try:
                            logger.info("👀 Visão: Processando contexto visual on-demand...")
                            res = await asyncio.wait_for(
                                self._vision.execute(source="screen"), 
                                timeout=90.0
                            )
                            vision_ctx = res.get("description", "")
                        except Exception as e:
                            logger.debug(f"Visão pontual timeout/erro: {e}")

                # ⚡ STREAMING: Brain gera → TTS sintetiza sentença por sentença
                sentence_stream = self._brain.think_stream(
                    user_text=user_text,
                    vision_context=vision_ctx,
                )

                # Intercepta o stream para analisar emoção e disparar expressão
                async def emotion_aware_stream():
                    first_sentence = True
                    async for sentence in sentence_stream:
                        # Analisa emoção na primeira sentença
                        if first_sentence:
                            emotion, score = self._brain.analyze_emotion(sentence)
                            await self._service.event_bus.emit("emotion_detected", {
                                "emotion": emotion,
                                "score": score,
                            })
                            logger.info(
                                f"Akane ({emotion}): '{sentence[:60]}...'"
                            )
                            first_sentence = False
                        yield sentence

                # Fala em streaming (Faster First Response)
                await self._tts.speak_streaming(emotion_aware_stream())

        except TimeoutError:
            logger.error(
                "⏰ Pipeline timeout (180s)! Processamento excessivamente longo."
            )
            try:
                await self._tts.execute(
                    text="Sua conexão de batata me fez perder o fio "
                         "da meada, baka! Tenta de novo!",
                    emotion="irritacao",
                )
            except Exception:
                pass

        except asyncio.CancelledError:
            logger.debug("Pipeline cancelado (barge-in ou shutdown).")

        except Exception as e:
            logger.error(f"Erro no pipeline de conversação: {e}")
            try:
                await self._tts.execute(
                    text="Tsc! Meus circuitos deram um curto! "
                         "Culpa desse hardware de faixa branca!",
                    emotion="irritacao",
                )
            except Exception:
                pass

    async def on_barge_in(self, data: dict[str, Any]) -> None:
        """Interrompe o TTS quando o usuário pressiona PTT."""
        await self._tts.stop_speaking()
        logger.debug("Barge-in: TTS interrompido.")

    async def on_trigger_proactive(self, data: dict[str, Any]) -> None:
        """Chamado quando a Akane decide falar por conta própria (timeout de silêncio)."""
        logger.info("⚡ Gatilho Proativo acionado!")
        elapsed = data.get("elapsed_seconds", 300)
        
        # Constrói a provocação interna
        internal_prompt = (
            f"*O usuário está em silêncio faz {elapsed // 60} minutos. "
            "Puxe assunto de forma ríspida ou provocativa se quiser. "
            "Se você achar que não tem o que dizer, seja breve e reclame.*"
        )
        
        try:
            async with asyncio.timeout(180):
                sentence_stream = self._brain.think_stream(
                    user_text=internal_prompt,
                    barge_in=False,
                )

                async def proactive_stream():
                    async for sentence in sentence_stream:
                        yield sentence
                        
                # Fala em streaming
                await self._tts.speak_streaming(proactive_stream())
                
        except asyncio.CancelledError:
            pass
        except TimeoutError:
            logger.warning("Pipeline proativo expirou (timeout 180s).")
        except Exception as e:
            logger.error(f"Erro no pipeline proativo: {e}")

    async def on_twitch_message(self, data: dict[str, Any]) -> None:
        """Chamado quando uma mensagem do chat passa pelo cooldown e cai aqui."""
        author = data.get("author", "Viewer")
        content = data.get("content", "")
        
        logger.info(f"🎤 Respondendo chat da Twitch: {author}: {content}")
        
        # Constrói o prompt avisando que veio do chat
        prompt = f"*Mensagem do chat da Twitch, recebida de {author}:* {content}\n*Responda a essa pessoa.*"
        
        try:
            async with asyncio.timeout(180):
                sentence_stream = self._brain.think_stream(
                    user_text=prompt,
                    barge_in=False,
                )

                async def twitch_stream():
                    async for sentence in sentence_stream:
                        yield sentence
                        
                # Fala em streaming
                await self._tts.speak_streaming(twitch_stream())
                
        except asyncio.CancelledError:
            pass
        except TimeoutError:
            logger.warning("Pipeline da Twitch expirou (timeout 180s).")
        except Exception as e:
            logger.error(f"Erro no pipeline do Twitch Chat: {e}")
