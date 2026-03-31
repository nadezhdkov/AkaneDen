import asyncio
import time
from typing import Any
from loguru import logger

from akane_den.core.base_skill import BaseSkill, SkillContext


class ProactiveSpeakSkill(BaseSkill):
    """
    Sistema de Proatividade: Monitora o tempo desde a última interação e
    decide puxar assunto se o usuário ficar muito tempo em silêncio.
    """
    
    name = "proactive_speak"
    description = "Puxa assunto se o usuário ficar inativo por muito tempo."

    def __init__(self, service, timeout_seconds: int = 300):
        ctx = SkillContext(skill_name=self.name)
        super().__init__(ctx, service)
        self.timeout_seconds = timeout_seconds
        self.last_interaction: float = time.time()
        self._task: asyncio.Task | None = None
        self._enabled = True

    async def setup(self) -> None:
        """Inicializa listeners e o loop em background."""
        await super().setup()
        
        # Ouve eventos principais para resetar o timer
        self.service.event_bus.on("user_speech_ready", self._reset_timer)
        self.service.event_bus.on("user_text_ready", self._reset_timer)
        self.service.event_bus.on("tts_speaking_start", self._reset_timer)
        self.service.event_bus.on("barge_in", self._reset_timer)
        
        # Inicia o monitoramento
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Skill {self.name} iniciada (timeout: {self.timeout_seconds}s)")

    async def _reset_timer(self, data: dict | None = None) -> None:
        """Reseta o cronômetro de silêncio."""
        self.last_interaction = time.time()

    async def _monitor_loop(self) -> None:
        """Loop que verifica a inatividade."""
        while True:
            try:
                await asyncio.sleep(5)  # Checa a cada 5 segundos
                
                if not self._enabled:
                    continue
                    
                elapsed = time.time() - self.last_interaction
                if elapsed > self.timeout_seconds:
                    logger.debug(f"{self.name}: Timeout atingido! Disparando gatilho proativo.")
                    
                    # Dispara o evento proativo e desativa temporariamente para não floodar
                    self._enabled = False
                    await self.service.event_bus.emit("trigger_proactive", {
                        "elapsed_seconds": int(elapsed)
                    })
                    
                    # Fica 60 segundos desativado antes de tentar contar silêncio de novo
                    await asyncio.sleep(60)
                    self._enabled = True
                    # Do not manually reset last_interaction here, wait for actual event.
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no monitor loop da ProactiveSpeakSkill: {e}")
                await asyncio.sleep(5)

    async def execute(self, **kwargs) -> Any:
        pass  # A execução principal acontece via EventBus e main.py
        
    async def teardown(self) -> None:
        if self._task:
            self._task.cancel()
        await super().teardown()
