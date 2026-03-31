"""
ServiceContext — Contêiner de Injeção de Dependência.

O ServiceContext é o coração da arquitetura Shogun v3.0. Ele centraliza
todas as instâncias ativas de motores de IA (LLM, TTS, ASR, VAD),
o EventBus, ChatHistory, e o config tipado.

v3.5: Adicionado VAD, ChatHistoryManager, e reload_config() para
hot-swap de personagem/config em runtime.

Benefícios:
    - Troca de provedores sem alterar skills
    - Uma única fonte de verdade para dependências
    - Setup/teardown centralizado
    - Hot-swap de config sem restart
    - Facilita testes com mock de engines

"Eu sou o CONTEXTO. Tudo passa por mim. Se alguma skill tentar
funcionar sem mim, vai 'graduar' na hora. Entendeu, baka?" — Akane
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from akane_den.core.config import AkaneConfig
from akane_den.core.engine_factory import EngineFactory
from akane_den.core.engines.asr_engine import ASREngine
from akane_den.core.engines.llm_engine import LLMEngine
from akane_den.core.engines.tts_engine import TTSEngine, ElevenLabsTTSEngine
from akane_den.core.event_bus import EventBus
from akane_den.core.persona_manager import PersonaManager
from akane_den.core.models.persona import PersonaProfile


@dataclass
class ServiceContext:
    """Contêiner de dependências para cada sessão da Akane.

    Centraliza as instâncias ativas de LLM, ASR, TTS, VAD, EventBus,
    ChatHistory e config. Skills recebem o ServiceContext no construtor.

    Uso:
        config = load_config()
        service = await ServiceContext.create(config)

        # Skills recebem o ServiceContext
        ptt = PTTSkill(SkillContext("ptt"), service)
        # Dentro da skill: self.service.llm, self.service.tts, etc.
    """

    config: AkaneConfig
    event_bus: EventBus
    llm: LLMEngine
    tts: TTSEngine
    asr: ASREngine
    persona: PersonaProfile
    # Motor TTS emocional (ElevenLabs) — pode ser None
    tts_emotional: ElevenLabsTTSEngine | None = None
    # VAD (Voice Activity Detection) — None se desativado
    vad: object | None = None
    # Chat History Manager — None se não configurado
    chat_history: object | None = None

    @classmethod
    async def create(cls, config: AkaneConfig) -> ServiceContext:
        """Factory method assíncrono — cria e inicializa todos os motores.

        Este é o ponto de entrada principal. Instancia os motores
        baseados no config e prepara o contexto completo.

        Args:
            config: Configuração validada por Pydantic.

        Returns:
            ServiceContext pronto para uso.
        """
        logger.info("=" * 50)
        logger.info("Criando ServiceContext...")
        logger.info("=" * 50)

        event_bus = EventBus()
        
        # ── Persona Load & Override ──
        pm = PersonaManager()
        profile = pm.load_persona(config.persona)
        
        # Sobrescreve as configs de voz dinamicamente pelo que estiver no profile
        if profile.voice_config.elevenlabs_voice_id:
            config.tts.elevenlabs_voice_id = profile.voice_config.elevenlabs_voice_id
        if profile.voice_config.edge_voice:
            config.tts.edge_voice = profile.voice_config.edge_voice

        # ── LLM Engine ──
        llm = EngineFactory.create_llm(config)

        # ── TTS Engine (default) ──
        tts = EngineFactory.create_tts(config)

        # ── TTS Emocional (ElevenLabs, separado) ──
        tts_emotional = None
        if config.tts.default_engine != "elevenlabs":
            try:
                tts_emotional = EngineFactory.create_elevenlabs_tts(config)
                if tts_emotional.is_available:
                    logger.info("TTS emocional (ElevenLabs) disponível.")
                else:
                    tts_emotional = None
                    logger.info("TTS emocional (ElevenLabs) não disponível.")
            except Exception as e:
                logger.warning(f"ElevenLabs não pôde ser inicializado: {e}")
                tts_emotional = None

        # ── ASR Engine ──
        asr = EngineFactory.create_asr(config)
        await asr.setup()

        # ── VAD Engine (opcional, desativado por padrão) ──
        vad = EngineFactory.create_vad(config)
        if vad is not None:
            await vad.setup()
            logger.info(f"  VAD: {vad.engine_name}")

        # ── Chat History (SQLite) ──
        chat_history = None
        try:
            from akane_den.core.chat_history import ChatHistoryManager

            chat_history = ChatHistoryManager()
            await chat_history.setup()
        except Exception as e:
            logger.warning(f"ChatHistory não inicializado: {e}")
            chat_history = None

        context = cls(
            config=config,
            event_bus=event_bus,
            llm=llm,
            tts=tts,
            asr=asr,
            persona=profile,
            tts_emotional=tts_emotional,
            vad=vad,
            chat_history=chat_history,
        )

        logger.success("ServiceContext criado com sucesso!")
        logger.info(f"  LLM: {llm.model_name}")
        logger.info(f"  TTS: {tts.engine_name}")
        logger.info(
            f"  TTS Emocional: "
            f"{'ElevenLabs' if tts_emotional else 'Nenhum'}"
        )
        logger.info(f"  ASR: {asr.engine_name}")
        logger.info(f"  VAD: {vad.engine_name if vad else 'Desativado (PTT primário)'}")
        logger.info(f"  ChatHistory: {'SQLite' if chat_history else 'Desativado'}")

        return context

    async def reload_config(self, new_config: AkaneConfig) -> None:
        """Hot-swap de configuração sem restart completo.

        Só reinicializa engines cujo config mudou.
        Usado pelo Web Dashboard para troca de persona/provider.

        Args:
            new_config: Nova configuração validada.
        """
        logger.info("Hot-swap de configuração iniciado...")
        changes = []

        # ── LLM ──
        if new_config.brain != self.config.brain:
            self.llm = EngineFactory.create_llm(new_config)
            changes.append(f"LLM → {self.llm.model_name}")

        # ── TTS ──
        if new_config.tts != self.config.tts:
            self.tts = EngineFactory.create_tts(new_config)
            changes.append(f"TTS → {self.tts.engine_name}")

            # Atualiza emocional se necessário
            if new_config.tts.default_engine != "elevenlabs":
                try:
                    self.tts_emotional = EngineFactory.create_elevenlabs_tts(new_config)
                    if not self.tts_emotional.is_available:
                        self.tts_emotional = None
                except Exception:
                    self.tts_emotional = None

        # ── ASR ──
        if new_config.asr != self.config.asr:
            if hasattr(self.asr, 'shutdown'):
                self.asr.shutdown()
            self.asr = EngineFactory.create_asr(new_config)
            await self.asr.setup()
            changes.append(f"ASR → {self.asr.engine_name}")

        # ── VAD ──
        if new_config.vad != self.config.vad:
            if self.vad and hasattr(self.vad, 'shutdown'):
                self.vad.shutdown()
            self.vad = EngineFactory.create_vad(new_config)
            if self.vad is not None:
                await self.vad.setup()
            changes.append(f"VAD → {self.vad.engine_name if self.vad else 'off'}")

        # ── Persona ──
        if new_config.persona != self.config.persona:
            pm = PersonaManager()
            self.persona = pm.load_persona(new_config.persona)
            changes.append(f"Persona → {new_config.persona}")

        self.config = new_config

        if changes:
            logger.success(f"Hot-swap concluído: {', '.join(changes)}")
        else:
            logger.info("Hot-swap: nenhuma mudança detectada.")

    def get_active_tts(self, emotion: str = "neutro", score: float = 0.0) -> TTSEngine:
        """Retorna o motor TTS adequado baseado na emoção.

        Se a emoção é intensa E o ElevenLabs está disponível,
        usa o motor emocional. Caso contrário, usa o padrão.

        Args:
            emotion: Nome da emoção detectada.
            score: Score de intensidade (0.0 a 1.0).

        Returns:
            TTSEngine adequado para a emoção.
        """
        emotional_states = ("raiva", "vergonha")

        if (
            self.tts_emotional is not None
            and self.tts_emotional.is_available
            and emotion in emotional_states
            and score >= self.config.tts.emotion_threshold
        ):
            logger.debug(
                f"TTS emocional ativado: {emotion} (score={score})"
            )
            return self.tts_emotional

        return self.tts

    def __repr__(self) -> str:
        return (
            f"<ServiceContext "
            f"llm={self.llm.model_name} "
            f"tts={self.tts.engine_name} "
            f"asr={self.asr.engine_name} "
            f"vad={'on' if self.vad else 'off'}>"
        )
