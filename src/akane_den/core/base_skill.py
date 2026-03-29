"""
BaseSkill ABC + SkillContext — Fundação da arquitetura Shogun v3.0.

Refatorada para receber ServiceContext em vez de config+bus separados.
Toda skill do sistema herda de BaseSkill e recebe o ServiceContext
que fornece acesso a LLM, TTS, ASR, EventBus e config tipado.
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from akane_den.core.service_context import ServiceContext


@dataclass
class SkillContext:
    """Contexto de execução de cada skill com cooldown dinâmico randomizado.

    O cooldown é randomizado entre min_cooldown e max_cooldown para
    garantir que as reações da Akane sejam dinâmicas e não repetitivas.
    """

    skill_name: str
    min_cooldown: float = 0.0
    max_cooldown: float = 0.0
    last_triggered: float = 0.0
    trigger_count: int = 0
    enabled: bool = True

    def can_trigger(self) -> bool:
        """Verifica se a skill pode ser ativada (cooldown expirado + habilitada)."""
        if not self.enabled:
            return False
        if self.min_cooldown <= 0 and self.max_cooldown <= 0:
            return True
        elapsed = time.time() - self.last_triggered
        cooldown = random.uniform(self.min_cooldown, self.max_cooldown)
        return elapsed >= cooldown

    def mark_triggered(self) -> None:
        """Registra que a skill foi ativada agora."""
        self.last_triggered = time.time()
        self.trigger_count += 1

    def reset(self) -> None:
        """Reseta contadores da sessão."""
        self.last_triggered = 0.0
        self.trigger_count = 0


class BaseSkill(ABC):
    """Classe base abstrata que toda skill do sistema Akane deve herdar.

    Implementa o padrão Shogun v3.0: cada skill é um módulo independente
    com setup/teardown assíncrono, execução com cooldown, e exposição
    opcional de ferramentas para o LangGraph.

    Mudança v3.0: Recebe ServiceContext em vez de config+bus separados.
    O ServiceContext fornece acesso tipado a config, event_bus, LLM, TTS e ASR.
    """

    def __init__(self, context: SkillContext, service: ServiceContext) -> None:
        self.context = context
        self.service = service
        self._active = False

    @property
    def config(self):
        """Atalho para o config tipado (AkaneConfig)."""
        return self.service.config

    @property
    def event_bus(self):
        """Atalho para o EventBus."""
        return self.service.event_bus

    @abstractmethod
    async def execute(self, **kwargs) -> dict:
        """Executa a skill. Retorna dict com resultados.

        Cada skill define sua própria interface de kwargs.
        O retorno sempre é um dict para uniformidade.
        """
        ...

    @abstractmethod
    async def setup(self) -> None:
        """Inicialização assíncrona (conexões, carregamento de modelos, etc).

        Chamado uma vez pelo SkillManager durante o boot do sistema.
        """
        ...

    async def teardown(self) -> None:
        """Cleanup opcional. Chamado durante o shutdown do sistema."""
        self._active = False

    def get_tools(self) -> list:
        """Retorna lista de LangChain tools expostas por esta skill.

        Override nas skills que precisam expor ferramentas para o LangGraph.
        Por padrão retorna lista vazia.
        """
        return []

    @property
    def name(self) -> str:
        """Nome identificador da skill."""
        return self.context.skill_name

    @property
    def is_active(self) -> bool:
        return self._active

    def __repr__(self) -> str:
        status = "ON" if self.context.enabled else "OFF"
        return (
            f"<{self.__class__.__name__} '{self.name}' "
            f"[{status}] triggers={self.context.trigger_count}>"
        )
