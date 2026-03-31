"""
GraphState — Grafo LangGraph com streaming para Faster First Response.

Refatorado na v3.0 para:
1. Usar ServiceContext em vez de parâmetros avulsos
2. Suportar streaming de resposta (sentença por sentença)
3. Integrar MCP tools e memória de longo prazo
4. Ser totalmente assíncrono (sem brain.invoke() bloqueante)
5. [v3.5] Persistência de chat via SQLite (ChatHistoryManager)

"Meu cérebro agora PENSA e FALA ao mesmo tempo. Enquanto eu
processo o próximo argumento pra te xingar, a primeira frase
já tá saindo. Eficiência de elite, baka!" — Akane
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger

from akane_den.brain.emotion_analyzer import EmotionAnalyzer
from akane_den.brain.persona import get_system_prompt

if TYPE_CHECKING:
    from akane_den.core.service_context import ServiceContext


class AkaneBrain:
    """Cérebro da Akane — gerencia conversação com streaming.

    O brain mantém o histórico de mensagens, gera respostas via
    LLM streaming, e coordena com emotion analyzer e memória.
    """

    def __init__(self, service: "ServiceContext") -> None:
        self.service = service
        self._history: list = []
        self._emotion_analyzer = EmotionAnalyzer(service.persona)
        self._tools: list = []
        self._memory = None
        self._session_id: str | None = None

    async def setup(self, tools: list | None = None, memory=None) -> None:
        """Inicializa o brain com ferramentas e memória.

        Args:
            tools: Lista de LangChain tools disponíveis.
            memory: MemoryHandler para memória de longo prazo.
        """
        self._tools = tools or []
        self._memory = memory

        if self._tools:
            self.service.llm.bind_tools(self._tools)
            logger.info(f"Brain equipado com {len(self._tools)} ferramentas.")

        # Restaura histórico persistente (SQLite)
        chat_history = self.service.chat_history
        if chat_history:
            try:
                self._session_id = await chat_history.get_or_create_session(
                    persona=self.service.config.persona
                )
                saved_msgs = await chat_history.get_langchain_messages(
                    self._session_id,
                    limit=self.service.config.brain.max_history,
                )
                if saved_msgs:
                    self._history = saved_msgs
                    logger.info(
                        f"Histórico restaurado: {len(saved_msgs) // 2} turnos "
                        f"(sessão {self._session_id})"
                    )
            except Exception as e:
                logger.warning(f"Erro ao restaurar histórico: {e}")

        logger.info("AkaneBrain inicializado e pronto.")

    def _build_messages(
        self,
        user_text: str,
        vision_context: str | None = None,
        webcam_context: str | None = None,
        barge_in: bool = False,
        memory_context: list[str] | None = None,
    ) -> list:
        """Constrói a lista de mensagens para o LLM.

        Args:
            user_text: Texto do usuário.
            vision_context: Descrição da tela (se disponível).
            webcam_context: Descrição da webcam (se disponível).
            barge_in: Se o usuário interrompeu a Akane.
            memory_context: Memórias relevantes recuperadas.

        Returns:
            Lista de mensagens LangChain.
        """
        # System prompt dinâmico
        extra_ctx = None
        if memory_context:
            extra_ctx = (
                "## Memórias Relevantes\n"
                + "\n".join(f"- {m}" for m in memory_context)
            )

        system_prompt = get_system_prompt(
            profile=self.service.persona,
            vision_context=vision_context,
            webcam_context=webcam_context,
            barge_in=barge_in,
            extra_context=extra_ctx,
        )

        messages = [SystemMessage(content=system_prompt)]
        messages.extend(self._history)
        messages.append(HumanMessage(content=user_text))

        return messages

    async def think(
        self,
        user_text: str,
        vision_context: str | None = None,
        webcam_context: str | None = None,
        barge_in: bool = False,
    ) -> str:
        """Gera resposta COMPLETA (não-streaming). Fallback para compatibilidade.

        Args:
            user_text: Texto do usuário.

        Returns:
            Texto completo da resposta da Akane.
        """
        # Recupera memórias relevantes
        memory_context = await self._retrieve_memories(user_text)

        messages = self._build_messages(
            user_text=user_text,
            vision_context=vision_context,
            webcam_context=webcam_context,
            barge_in=barge_in,
            memory_context=memory_context,
        )

        try:
            response = await self.service.llm.chat(messages, self._tools)

            # Extrai texto da resposta
            response_text = self._extract_text(response)

            # Processa tool calls se houver
            if hasattr(response, "tool_calls") and response.tool_calls:
                response_text = await self._handle_tool_calls(
                    response, messages
                )

            # Atualiza histórico
            self._update_history(user_text, response_text)

            # Armazena na memória de longo prazo
            await self._store_memory(user_text, response_text)

            return response_text

        except Exception as e:
            logger.error(f"Erro no brain.think(): {e}")
            return (
                "Tsc! Meus circuitos travaram por um segundo. "
                "Não é culpa minha, é esse hardware de faixa branca! "
                "Tenta de novo, baka."
            )

    async def think_stream(
        self,
        user_text: str,
        vision_context: str | None = None,
        webcam_context: str | None = None,
        barge_in: bool = False,
    ) -> AsyncIterator[str]:
        """Gera resposta em STREAMING — sentença por sentença.

        Este é o método principal para Faster First Response.
        Cada sentence completa (terminada em . ! ? ou ...) é
        yielded assim que detectada.

        Yields:
            Sentenças completas assim que ficam prontas.
        """
        # Recupera memórias relevantes
        memory_context = await self._retrieve_memories(user_text)

        messages = self._build_messages(
            user_text=user_text,
            vision_context=vision_context,
            webcam_context=webcam_context,
            barge_in=barge_in,
            memory_context=memory_context,
        )

        try:
            full_response = ""
            sentence_buffer = ""
            sentence_separators = (".", "!", "?", "…")

            async for chunk in self.service.llm.chat_stream(messages, self._tools):
                if isinstance(chunk, list):
                    logger.info(f"Tool calls detectados via streaming: {len(chunk)}")
                    from langchain_core.messages import AIMessage
                    tool_msg = AIMessage(content="", tool_calls=chunk)
                    final_text = await self._handle_tool_calls(tool_msg, messages)
                    if final_text:
                        sentence_buffer += final_text
                        full_response += final_text
                    continue

                sentence_buffer += chunk
                full_response += chunk

                # Detecta sentenças completas
                while True:
                    # Procura o primeiro separador na posição mais próxima
                    earliest_pos = -1
                    found_sep = ""

                    for sep in sentence_separators:
                        pos = sentence_buffer.find(sep)
                        if pos >= 0 and (earliest_pos < 0 or pos < earliest_pos):
                            # Checa por "..." (3 pontos)
                            if sep == "." and sentence_buffer[pos:pos+3] == "...":
                                earliest_pos = pos + 2  # Inclui os 3 pontos
                                found_sep = "..."
                            else:
                                earliest_pos = pos
                                found_sep = sep

                    if earliest_pos < 0:
                        break  # Nenhuma sentença completa ainda

                    # Extrai a sentença completa
                    sentence = sentence_buffer[:earliest_pos + 1].strip()
                    sentence_buffer = sentence_buffer[earliest_pos + 1:].lstrip()

                    if sentence and len(sentence) > 2:
                        logger.debug(f"Sentence ready: '{sentence[:50]}...'")
                        yield sentence

            # Flush do buffer restante
            if sentence_buffer.strip() and len(sentence_buffer.strip()) > 2:
                yield sentence_buffer.strip()

            # Atualiza histórico com resposta completa
            self._update_history(user_text, full_response)

            # Armazena na memória de longo prazo
            await self._store_memory(user_text, full_response)

        except Exception as e:
            logger.error(f"Erro no brain.think_stream(): {e}")
            yield (
                "Tsc! Erro no streaming! Culpa do hardware limitado, "
                "não minha! Tenta de novo, baka."
            )

    async def _handle_tool_calls(
        self, response: Any, messages: list
    ) -> str:
        """Executa tool calls e retorna a resposta final com resultados."""
        from langchain_core.messages import ToolMessage

        tool_map = {t.name: t for t in self._tools}
        messages.append(response)

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            logger.info(f"Tool call: {tool_name}({tool_args})")

            tool = tool_map.get(tool_name)
            if tool:
                try:
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None, tool.invoke, tool_args
                    )
                    result_str = str(result)
                except Exception as e:
                    result_str = f"Erro na ferramenta: {e}"
                    logger.error(f"Tool {tool_name} falhou: {e}")
            else:
                result_str = f"Ferramenta '{tool_name}' não encontrada!"

            messages.append(
                ToolMessage(content=result_str, tool_call_id=tool_call["id"])
            )

        # Segunda invocação com resultados das tools
        final_response = await self.service.llm.chat(messages)
        return self._extract_text(final_response)

    def _extract_text(self, response: Any) -> str:
        """Extrai texto limpo de um LangChain message object."""
        if hasattr(response, "content"):
            content = response.content
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                return " ".join(text_parts)
        return str(response)

    def _update_history(self, user_text: str, response_text: str) -> None:
        """Atualiza o histórico de conversação (com limite do config).

        v3.5: Também persiste no SQLite via ChatHistoryManager.
        """
        self._history.append(HumanMessage(content=user_text))
        self._history.append(AIMessage(content=response_text))

        max_history = self.service.config.brain.max_history
        if len(self._history) > max_history * 2:
            self._history = self._history[-(max_history * 2):]
            logger.debug(f"Histórico truncado para {max_history} turnos.")

        # Persiste no SQLite (fire-and-forget)
        chat_history = self.service.chat_history
        if chat_history and self._session_id:
            async def _persist():
                try:
                    await chat_history.add_message(
                        self._session_id, "user", user_text
                    )
                    await chat_history.add_message(
                        self._session_id, "assistant", response_text
                    )
                except Exception as e:
                    logger.warning(f"Erro ao persistir chat: {e}")

            asyncio.create_task(_persist())

    async def _retrieve_memories(self, query: str) -> list[str] | None:
        """Recupera memórias relevantes para contextualizar a resposta."""
        if not self._memory:
            return None

        try:
            memories = await self._memory.retrieve(query, top_k=3)
            if memories:
                return [m["text"] for m in memories]
        except Exception as e:
            logger.warning(f"Erro ao recuperar memórias: {e}")

        return None

    async def _store_memory(self, user_text: str, response_text: str) -> None:
        """Armazena a interação na memória de longo prazo."""
        if not self._memory:
            return

        try:
            combined = f"User: {user_text}\nAkane: {response_text}"
            await self._memory.store(
                combined,
                metadata={"type": "conversation"},
            )
        except Exception as e:
            logger.warning(f"Erro ao armazenar memória: {e}")

    def analyze_emotion(self, text: str) -> tuple[str, float]:
        """Analisa emoção no texto (atalho para EmotionAnalyzer)."""
        return self._emotion_analyzer.analyze(text)

    def clear_history(self) -> None:
        """Limpa o histórico de conversação da sessão."""
        self._history.clear()
        logger.info("Histórico de conversação limpo.")

    @property
    def history_length(self) -> int:
        return len(self._history) // 2

    @property
    def session_id(self) -> str | None:
        """ID da sessão de chat persistente ativa."""
        return self._session_id
