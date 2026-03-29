"""
LLMEngine — Interface abstrata e implementações para provedores de LLM.

Padrão Factory: cada provedor herda de LLMEngine e implementa
chat() e chat_stream() assíncronos. A troca de provedor é feita
apenas no config.yaml sem alterar nenhum código.

Provedores implementados:
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
    ) -> AsyncIterator[str]:
        """Gera resposta em streaming (yield de chunks de texto)."""
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


# ──────────────────────────────────────────────
# Implementação: Gemini (Default)
# ──────────────────────────────────────────────


class GeminiLLMEngine(LLMEngine):
    """LLM Engine usando Google Gemini via langchain-google-genai."""

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        from langchain_google_genai import ChatGoogleGenerativeAI

        self._llm = ChatGoogleGenerativeAI(
            model=config.brain.gemini_model,
            temperature=config.brain.temperature,
        )
        self._tools_bound = False
        logger.info(f"GeminiLLMEngine inicializado: {config.brain.gemini_model}")

    async def chat(self, messages: list, tools: list | None = None) -> object:
        """Invoca Gemini (roda em thread pool para não bloquear)."""
        llm = self._llm
        if tools and not self._tools_bound:
            llm = llm.bind_tools(tools)

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, llm.invoke, messages)
        return response

    async def chat_stream(
        self,
        messages: list,
        tools: list | None = None,
    ) -> AsyncIterator[str]:
        """Stream de resposta do Gemini."""
        llm = self._llm
        if tools and not self._tools_bound:
            llm = llm.bind_tools(tools)

        # LangChain stream() retorna um iterador síncrono
        loop = asyncio.get_running_loop()

        def _stream_sync():
            return list(llm.stream(messages))

        chunks = await loop.run_in_executor(None, _stream_sync)
        for chunk in chunks:
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

    def bind_tools(self, tools: list) -> None:
        self._llm = self._llm.bind_tools(tools)
        self._tools_bound = True

    @property
    def model_name(self) -> str:
        return self.config.brain.gemini_model


# ──────────────────────────────────────────────
# Implementação: Groq
# ──────────────────────────────────────────────


class GroqLLMEngine(LLMEngine):
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
            self._tools_bound = False
            logger.info(f"GroqLLMEngine inicializado: {config.brain.groq_model}")
        except ImportError:
            raise ImportError(
                "langchain-groq não instalado! Instale com: "
                "uv pip install 'akane-den[groq]'"
            )

    async def chat(self, messages: list, tools: list | None = None) -> object:
        llm = self._llm
        if tools and not self._tools_bound:
            llm = llm.bind_tools(tools)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, llm.invoke, messages)

    async def chat_stream(
        self,
        messages: list,
        tools: list | None = None,
    ) -> AsyncIterator[str]:
        llm = self._llm
        if tools and not self._tools_bound:
            llm = llm.bind_tools(tools)

        loop = asyncio.get_running_loop()

        def _stream_sync():
            return list(llm.stream(messages))

        chunks = await loop.run_in_executor(None, _stream_sync)
        for chunk in chunks:
            if hasattr(chunk, "content") and chunk.content:
                if isinstance(chunk.content, str):
                    yield chunk.content

    def bind_tools(self, tools: list) -> None:
        self._llm = self._llm.bind_tools(tools)
        self._tools_bound = True

    @property
    def model_name(self) -> str:
        return self.config.brain.groq_model


# ──────────────────────────────────────────────
# Implementação: Ollama
# ──────────────────────────────────────────────


class OllamaLLMEngine(LLMEngine):
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
            self._tools_bound = False
            logger.info(
                f"OllamaLLMEngine inicializado: {config.brain.ollama_model} "
                f"@ {config.brain.ollama_base_url}"
            )
        except ImportError:
            raise ImportError(
                "langchain-ollama não instalado! Instale com: "
                "uv pip install 'akane-den[ollama]'"
            )

    async def chat(self, messages: list, tools: list | None = None) -> object:
        llm = self._llm
        if tools and not self._tools_bound:
            llm = llm.bind_tools(tools)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, llm.invoke, messages)

    async def chat_stream(
        self,
        messages: list,
        tools: list | None = None,
    ) -> AsyncIterator[str]:
        llm = self._llm
        if tools and not self._tools_bound:
            llm = llm.bind_tools(tools)

        loop = asyncio.get_running_loop()

        def _stream_sync():
            return list(llm.stream(messages))

        chunks = await loop.run_in_executor(None, _stream_sync)
        for chunk in chunks:
            if hasattr(chunk, "content") and chunk.content:
                if isinstance(chunk.content, str):
                    yield chunk.content

    def bind_tools(self, tools: list) -> None:
        self._llm = self._llm.bind_tools(tools)
        self._tools_bound = True

    @property
    def model_name(self) -> str:
        return self.config.brain.ollama_model


# ──────────────────────────────────────────────
# Implementação: OpenAI
# ──────────────────────────────────────────────


class OpenAILLMEngine(LLMEngine):
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
            self._tools_bound = False
            logger.info(f"OpenAILLMEngine inicializado: {config.brain.openai_model}")
        except ImportError:
            raise ImportError(
                "langchain-openai não instalado! Instale com: "
                "uv pip install 'akane-den[openai]'"
            )

    async def chat(self, messages: list, tools: list | None = None) -> object:
        llm = self._llm
        if tools and not self._tools_bound:
            llm = llm.bind_tools(tools)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, llm.invoke, messages)

    async def chat_stream(
        self,
        messages: list,
        tools: list | None = None,
    ) -> AsyncIterator[str]:
        llm = self._llm
        if tools and not self._tools_bound:
            llm = llm.bind_tools(tools)

        loop = asyncio.get_running_loop()

        def _stream_sync():
            return list(llm.stream(messages))

        chunks = await loop.run_in_executor(None, _stream_sync)
        for chunk in chunks:
            if hasattr(chunk, "content") and chunk.content:
                if isinstance(chunk.content, str):
                    yield chunk.content

    def bind_tools(self, tools: list) -> None:
        self._llm = self._llm.bind_tools(tools)
        self._tools_bound = True

    @property
    def model_name(self) -> str:
        return self.config.brain.openai_model
