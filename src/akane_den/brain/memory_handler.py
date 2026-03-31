"""
MemoryHandler — Interface de memória de longo prazo.

Implementações:
    - ChromaMemoryHandler (default, local)
    - LettaMemoryHandler (preparado para Letta/MemGPT)

Permite que a Akane lembre de conversas passadas entre sessões.

"Eu lembro de TUDO que você faz, velho. Não pense que pode
me enganar só porque reiniciou o sistema!" — Akane
"""

from __future__ import annotations


from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from loguru import logger

from akane_den.core.config import MemoryConfig


class MemoryHandler(ABC):
    """Interface abstrata para memória persistente."""

    def __init__(self, config: MemoryConfig) -> None:
        self.config = config

    @abstractmethod
    async def store(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Armazena um trecho de texto com metadados opcionais."""
        ...

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Recupera os `top_k` trechos mais relevantes para a query."""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """Limpa toda a memória armazenada."""
        ...

    @abstractmethod
    async def setup(self) -> None:
        """Inicializa o backend de memória."""
        ...

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Nome do backend ativo."""
        ...


# ──────────────────────────────────────────────
# Implementação: ChromaDB (Default, Local)
# ──────────────────────────────────────────────


class ChromaMemoryHandler(MemoryHandler):
    """Memória de longo prazo usando ChromaDB local.

    Armazena embeddings de conversas em disco para
    recuperação semântica entre sessões.
    """

    def __init__(self, config: MemoryConfig) -> None:
        super().__init__(config)
        self._client = None
        self._collection = None

    async def setup(self) -> None:
        """Inicializa ChromaDB client e collection."""
        import asyncio

        loop = asyncio.get_running_loop()

        def _init_sync():
            import chromadb
            from chromadb.config import Settings

            client = chromadb.PersistentClient(
                path=self.config.db_path,
                settings=Settings(anonymized_telemetry=False),
            )
            collection = client.get_or_create_collection(
                name="akane_memory",
                metadata={"hnsw:space": "cosine"},
            )
            # WARM-UP: O ChromaDB usa sentence-transformers/onnx. A primeira query
            # puxa a DLL e aloca modelo pesadíssimo, travando o GIL por até 15s.
            # Essa busca "vazia" força o cacheamento durante o boot!
            try:
                collection.query(
                    query_texts=["warmup"],
                    n_results=1,
                )
            except Exception as e:
                pass
                
            return client, collection

        from akane_den.core.runtime import run_in_db
        self._client, self._collection = await run_in_db(_init_sync)
        count = self._collection.count()
        logger.info(
            f"ChromaDB inicializado e warmed-up: {self.config.db_path} "
            f"({count} memórias armazenadas)"
        )

    async def store(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Armazena texto com embedding automático do ChromaDB."""
        if not self._collection:
            logger.warning("ChromaDB não inicializado. Ignorando store().")
            return

        import asyncio
        import hashlib

        meta = metadata or {}
        meta["timestamp"] = datetime.now().isoformat()
        doc_id = hashlib.sha256(
            f"{text}{meta['timestamp']}".encode()
        ).hexdigest()[:16]

        loop = asyncio.get_running_loop()

        def _store_sync():
            self._collection.add(
                documents=[text],
                metadatas=[meta],
                ids=[doc_id],
            )

        from akane_den.core.runtime import run_in_db
        await run_in_db(_store_sync)
        logger.debug(f"Memória armazenada: id={doc_id}, len={len(text)}")

    async def retrieve(
        self,
        query: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Busca semântica por memórias relevantes."""
        if not self._collection or self._collection.count() == 0:
            return []

        import asyncio

        loop = asyncio.get_running_loop()

        def _query_sync():
            results = self._collection.query(
                query_texts=[query],
                n_results=min(top_k, self._collection.count()),
            )
            memories = []
            if results["documents"]:
                for doc, meta in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                ):
                    memories.append({
                        "text": doc,
                        "metadata": meta,
                    })
            return memories

        from akane_den.core.runtime import run_in_db
        memories = await run_in_db(_query_sync)
        logger.debug(f"Memórias recuperadas: {len(memories)} para query='{query[:40]}'")
        return memories

    async def clear(self) -> None:
        """Limpa toda a memória."""
        if self._client:
            import asyncio

            loop = asyncio.get_running_loop()

            def _clear_sync():
                self._client.delete_collection("akane_memory")

            from akane_den.core.runtime import run_in_db
            await run_in_db(_clear_sync)
            logger.warning("Memória limpa completamente!")

    @property
    def backend_name(self) -> str:
        return "chromadb"


# ──────────────────────────────────────────────
# Implementação: Letta (Preparada para futuro)
# ──────────────────────────────────────────────


class LettaMemoryHandler(MemoryHandler):
    """Memória de longo prazo via Letta (MemGPT).

    Preparada para integração futura. Requer servidor Letta rodando.
    Instale com: uv pip install 'akane-den[letta]'
    """

    def __init__(self, config: MemoryConfig) -> None:
        super().__init__(config)
        self._client = None
        self._agent_state = None

    async def setup(self) -> None:
        """Conecta ao servidor Letta."""
        try:
            from letta_client import Letta

            self._client = Letta(base_url=self.config.letta_base_url)
            # Tenta recuperar ou criar agente Akane
            agents = self._client.agents.list()
            agent = next(
                (a for a in agents if a.name == self.config.letta_agent_name),
                None,
            )
            if agent:
                self._agent_state = agent
                logger.info(f"Letta agent recuperado: {agent.name}")
            else:
                logger.info(
                    "Letta agent não encontrado. "
                    "Será criado na primeira interação."
                )

        except ImportError:
            raise ImportError(
                "letta-client não instalado! Instale com: "
                "uv pip install 'akane-den[letta]'"
            )
        except Exception as e:
            logger.warning(f"Letta não disponível: {e}")
            logger.info("Fallback: memória desabilitada para Letta.")

    async def store(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        """Armazena via Letta agent memory."""
        if not self._client or not self._agent_state:
            return
        try:
            self._client.agents.messages.send(
                agent_id=self._agent_state.id,
                role="user",
                text=f"[MEMÓRIA] {text}",
            )
            logger.debug(f"Memória Letta armazenada: {len(text)} chars")
        except Exception as e:
            logger.error(f"Erro ao armazenar em Letta: {e}")

    async def retrieve(
        self, query: str, top_k: int = 3
    ) -> list[dict[str, Any]]:
        """Recupera via Letta archival memory search."""
        if not self._client or not self._agent_state:
            return []
        try:
            results = self._client.agents.archival_memory.list(
                agent_id=self._agent_state.id,
                query=query,
                limit=top_k,
            )
            return [{"text": r.text, "metadata": {}} for r in results]
        except Exception as e:
            logger.error(f"Erro ao recuperar de Letta: {e}")
            return []

    async def clear(self) -> None:
        """Letta não suporta clear direto — log de aviso."""
        logger.warning(
            "Letta não suporta limpeza total de memória. "
            "Use o painel web do Letta para gerenciar."
        )

    @property
    def backend_name(self) -> str:
        return "letta"


# ──────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────


def create_memory_handler(config: MemoryConfig) -> MemoryHandler | None:
    """Factory para criar o handler de memória baseado no config."""
    if not config.enabled or config.backend == "none":
        logger.info("Memória de longo prazo desabilitada.")
        return None

    handlers = {
        "chromadb": ChromaMemoryHandler,
        "letta": LettaMemoryHandler,
    }

    handler_cls = handlers.get(config.backend)
    if not handler_cls:
        logger.error(f"Backend de memória desconhecido: {config.backend}")
        return None

    logger.info(f"Criando handler de memória: {config.backend}")
    return handler_cls(config)
