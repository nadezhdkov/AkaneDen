import asyncio
import os
import time
from loguru import logger

try:
    from twitchio import Client, Message
    TWITCHIO_AVAILABLE = True
except ImportError:
    TWITCHIO_AVAILABLE = False
    Client = object   # type: ignore
    Message = object  # type: ignore

from akane_den.core.base_skill import BaseSkill, SkillContext


class TwitchChatSkill(BaseSkill):
    """
    Skill de Integração com a Twitch.
    Conecta-se ao chat do canal configurado, lê mensagens e aplica filtros
    (ignora comandos com ! e respeita um cooldown configurável).
    A execução é paralisada se o PTT (microfone do usuário) estiver ativo.
    """

    name = "twitch_chat"
    description = "Leitor de Chat da Twitch em tempo real."

    def __init__(self, service):
        ctx = SkillContext(skill_name=self.name)
        super().__init__(ctx, service)
        self.bot: Client | None = None
        self._task: asyncio.Task | None = None
        
        self.cooldown = self.config.twitch.cooldown
        self.last_read_time: float = 0.0
        
        # Estado de interrupção (usuário falando tem prioridade absoluta)
        self.ptt_active = False

    async def setup(self) -> None:
        await super().setup()
        
        if not self.config.twitch.enabled:
            logger.info("TwitchChatSkill desativada via config.")
            return
            
        if not TWITCHIO_AVAILABLE:
            logger.error("twitchio não instalado! Rode `uv add twitchio`.")
            return

        token = self.config.twitch.oauth_token or os.environ.get("TWITCH_OAUTH_TOKEN", "")
        channel = self.config.twitch.channel_name
        
        if not token or not channel:
            logger.warning("Twitch: Token ou Channel não configurados. Skill inativa.")
            return
            
        if not token.startswith("oauth:"):
            token = f"oauth:{token}"

        # Escuta os eventos do microfone para silenciar a Twitch temporariamente
        self.context.event_bus.on("ptt_pressed", self._on_ptt_pressed)
        self.context.event_bus.on("ptt_released", self._on_ptt_released)

        self.bot = Client(token=token, initial_channels=[channel])
        
        # Registrar events do twitchio
        self.bot.event_message = self._on_message
        self.bot.event_ready = self._on_ready
        
        # Inicializa conexão em background
        self._task = asyncio.create_task(self.bot.start())
        logger.info(f"Conectando ao canal da Twitch: {channel} (cooldown: {self.cooldown}s)")

    async def _on_ptt_pressed(self, data: dict) -> None:
        self.ptt_active = True

    async def _on_ptt_released(self, data: dict) -> None:
        self.ptt_active = False

    async def _on_ready(self) -> None:
        logger.success(f"📺 TwitchChat conectado como {self.bot.nick}")

    async def _on_message(self, message: Message) -> None:
        if not message.author:
            return
            
        username = message.author.name
        content = message.content.strip()
        
        # Filtro básico: ignora bots comuns (Nightbot) e comandos (!)
        if username.lower() in ("nightbot", "streamelements", "moobot"):
            return
        if content.startswith("!"):
            return
            
        # PTT ativado = cala o chat, o usuário real está falando!
        if self.ptt_active:
            return

        # Checa cooldown
        now = time.time()
        if now - self.last_read_time < self.cooldown:
            return
            
        # Tudo passou no filtro: emitir evento para a Akane reagir
        self.last_read_time = now
        logger.info(f"[Twitch] {username}: {content}")
        
        await self.context.event_bus.emit("twitch_message_received", {
            "author": username,
            "content": content
        })

    async def execute(self, **kwargs):
        pass

    async def teardown(self) -> None:
        if self.bot:
            await self.bot.close()
        if self._task:
            self._task.cancel()
        await super().teardown()
        logger.info("TwitchChat encerrou a conexão.")
