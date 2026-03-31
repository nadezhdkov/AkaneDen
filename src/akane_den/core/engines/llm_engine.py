"""
LLMEngine — Interface abstrata e implementações para provedores de LLM.

Padrão Factory: cada provedor herda de LLMEngine e implementa
chat() e chat_stream() assíncronos. A troca de provedor é feita
apenas no config.yaml sem alterar nenhum código.

Provedores implementados baseados na LangChainLLMEngine:
    - GeminiLLMEngine (default)
    - GroqLLMEngine
    - OllamaLLMEngine
    - OpenAILLMEngine

"Trocar de cérebro? Quem você pensa que eu sou, uma boneca de troca
de peças?! ...Mas tá, se o Gemini cair, eu uso o Groq. Eficiência." — Akane
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import AsyncIterator

from loguru import logger

from akane_den.core.config import AkaneConfig
from akane_den.core.runtime import run_in_io


class LLMEngine(ABC):
    """Interface abstrata para provedores de LLM.

    Toda implementação deve suportar:
    - chat(): resposta completa (síncrono-compatível via await)
    - chat_stream(): streaming por chunks (para Faster First Response)
    - tool binding (bind_tools)
    """

    def __init__(self, config: AkaneConfig) -> None:
        self.config = config

    @abstractmethod
    async def chat(
        self,
        messages: list,
        tools: list | None = None,
    ) -> object:
        """Gera resposta completa (retorna LangChain message object)."""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list,
        tools: list | None = None,
    ) -> AsyncIterator[str | list]:
        """Gera resposta em streaming (yield de chunks de texto ou list de tool_calls)."""
        ...

    @abstractmethod
    def bind_tools(self, tools: list) -> None:
        """Vincula ferramentas LangChain ao modelo."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Nome do modelo ativo."""
        ...


class LangChainLLMEngine(LLMEngine):
    """Classe base Template Method para provedores baseados no LangChain."""

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        self._llm = None
        self._tools_bound = False

    async def chat(self, messages: list, tools: list | None = None) -> object:
        """Invoca o LLM (isolado em IO_POOL)."""
        llm = self._llm
        if not llm:
            raise RuntimeError("LLM não inicializado pela subclasse.")

        if tools and not self._tools_bound:
            llm = llm.bind_tools(tools)

        try:
            return await run_in_io(llm.invoke, messages)
        except Exception as e:
            logger.error(f"[LLM] Falha na chamada síncrona ({self.model_name}): {e}")
            raise

    async def chat_stream(
        self,
        messages: list,
        tools: list | None = None,
    ) -> AsyncIterator[str | list]:
        """Stream híbrido unificado para todos os modelos."""
        llm = self._llm
        if not llm:
            raise RuntimeError("LLM não inicializado pela subclasse.")

        if tools and not self._tools_bound:
            llm = llm.bind_tools(tools)

        try:
            full_chunk = None
            async for chunk in llm.astream(messages):
                if full_chunk is None:
                    full_chunk = chunk
                else:
                    full_chunk += chunk

                if hasattr(chunk, "content") and chunk.content:
                    content = chunk.content
                    if isinstance(content, str):
                        yield content
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                yield block.get("text", "")
                            elif isinstance(block, str):
                                yield block
            
            if full_chunk and hasattr(full_chunk, "tool_calls") and full_chunk.tool_calls:
                yield full_chunk.tool_calls

        except Exception as e:
            logger.error(f"[{self.model_name}] RateLimit/Conexão abortada: {e}")
            yield "\n[H-humph! Meu cérebro deu um nó agora, baka! Não me pressione tanto, tente de novo em um minuto!]"

    def bind_tools(self, tools: list) -> None:
        if self._llm is not None:
            self._llm = self._llm.bind_tools(tools)
            self._tools_bound = True


# ──────────────────────────────────────────────
# Implementação: Gemini (Default)
# ──────────────────────────────────────────────


class GeminiLLMEngine(LangChainLLMEngine):
    """LLM Engine usando Google Gemini via langchain-google-genai."""

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        from langchain_google_genai import ChatGoogleGenerativeAI

        self._llm = ChatGoogleGenerativeAI(
            model=config.brain.gemini_model,
            temperature=config.brain.temperature,
        )
        logger.info(f"GeminiLLMEngine inicializado: {self.model_name}")

    @property
    def model_name(self) -> str:
        return self.config.brain.gemini_model


# ──────────────────────────────────────────────
# Implementação: Groq
# ──────────────────────────────────────────────


class GroqLLMEngine(LangChainLLMEngine):
    """LLM Engine usando Groq via langchain-groq."""

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        try:
            from langchain_groq import ChatGroq

            kwargs = {
                "model": config.brain.groq_model,
                "temperature": config.brain.temperature,
            }
            if config.brain.groq_api_base:
                kwargs["groq_api_base"] = config.brain.groq_api_base

            self._llm = ChatGroq(**kwargs)
            logger.info(f"GroqLLMEngine inicializado: {self.model_name}")
        except ImportError:
            raise ImportError(
                "langchain-groq não instalado! Instale com: "
                "uv pip install 'akane-den[groq]'"
            )

    @property
    def model_name(self) -> str:
        return self.config.brain.groq_model


# ──────────────────────────────────────────────
# Implementação: Ollama
# ──────────────────────────────────────────────


class OllamaLLMEngine(LangChainLLMEngine):
    """LLM Engine usando Ollama local via langchain-ollama."""

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        try:
            from langchain_ollama import ChatOllama

            self._llm = ChatOllama(
                model=config.brain.ollama_model,
                temperature=config.brain.temperature,
                base_url=config.brain.ollama_base_url,
            )
            logger.info(f"OllamaLLMEngine inicializado: {self.model_name} @ {config.brain.ollama_base_url}")
        except ImportError:
            raise ImportError(
                "langchain-ollama não instalado! Instale com: "
                "uv pip install 'akane-den[ollama]'"
            )

    @property
    def model_name(self) -> str:
        return self.config.brain.ollama_model


# ──────────────────────────────────────────────
# Implementação: OpenAI
# ──────────────────────────────────────────────


class OpenAILLMEngine(LangChainLLMEngine):
    """LLM Engine usando OpenAI ou compatíveis via langchain-openai."""

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        try:
            from langchain_openai import ChatOpenAI

            kwargs = {
                "model": config.brain.openai_model,
                "temperature": config.brain.temperature,
            }
            if config.brain.openai_api_base:
                kwargs["openai_api_base"] = config.brain.openai_api_base

            self._llm = ChatOpenAI(**kwargs)
            logger.info(f"OpenAILLMEngine inicializado: {self.model_name}")
        except ImportError:
            raise ImportError(
                "langchain-openai não instalado! Instale com: "
                "uv pip install 'akane-den[openai]'"
            )

    @property
    def model_name(self) -> str:
        return self.config.brain.openai_model
