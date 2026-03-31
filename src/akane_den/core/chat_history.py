"""
ChatHistoryManager — Persistência de conversas em SQLite.

Gerencia sessões de conversa com histórico persistente. Cada sessão
possui um UUID e pode ser retomada após restart do sistema.

Features:
    - CRUD de mensagens por sessão
    - Listagem de sessões com preview
    - Troca de sessão (switch)
    - Busca por texto no histórico
    - Exportação/importação de sessões

"Eu lembro de TUDO que você me disse, baka! Cada palavra!
 Então pense duas vezes antes de falar besteira!" — Akane
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class ChatHistoryManager:
    """Gerenciador de histórico de chat com persistência SQLite.

    Cada sessão é identificada por um UUID e contém uma sequência
    ordenada de mensagens (user/assistant) com timestamps.

    Uso:
        history = ChatHistoryManager("chat_history/akane.db")
        await history.setup()
        session_id = await history.create_session("Sessão do dia")
        await history.add_message(session_id, "user", "Olá Akane!")
        await history.add_message(session_id, "assistant", "Hmph, oi baka.")
        msgs = await history.get_messages(session_id)
    """

    def __init__(self, db_path: str = "chat_history/akane_chat.db") -> None:
        from akane_den.core.paths import BASE_DIR
        self._db_path = BASE_DIR / db_path
        self._conn: sqlite3.Connection | None = None

    async def setup(self) -> None:
        """Inicializa o banco de dados SQLite com tabelas necessárias."""
        import asyncio

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._init_db)
        logger.info(f"ChatHistory SQLite inicializado: {self._db_path}")

    def _init_db(self) -> None:
        """Cria tabelas se não existem (sync, roda em executor)."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                persona TEXT DEFAULT 'akane_default',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                emotion TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_messages_content
                ON messages(content);
        """)
        self._conn.commit()

    def _execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Executa query com error handling."""
        if self._conn is None:
            raise RuntimeError("ChatHistory não inicializado. Chame setup().")
        return self._conn.execute(query, params)

    # ── Session Management ──

    async def create_session(
        self,
        title: str = "",
        persona: str = "akane_default",
    ) -> str:
        """Cria uma nova sessão de conversa.

        Args:
            title: Título descritivo da sessão.
            persona: Nome do perfil de personagem.

        Returns:
            UUID da sessão criada.
        """
        import asyncio

        session_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        if not title:
            title = f"Sessão {now[:10]}"

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: (
                self._execute(
                    "INSERT INTO sessions (id, title, persona, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (session_id, title, persona, now, now),
                ),
                self._conn.commit(),
            ),
        )

        logger.info(f"Nova sessão criada: {session_id} ({title})")
        return session_id

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        """Lista sessões recentes com preview da última mensagem.

        Returns:
            Lista de dicts com id, title, persona, last_message, etc.
        """
        import asyncio

        def _query():
            cursor = self._execute(
                """
                SELECT s.id, s.title, s.persona, s.created_at, s.updated_at,
                    (SELECT content FROM messages m
                     WHERE m.session_id = s.id
                     ORDER BY m.created_at DESC LIMIT 1) as last_message,
                    (SELECT COUNT(*) FROM messages m
                     WHERE m.session_id = s.id) as message_count
                FROM sessions s
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _query)

    async def get_or_create_session(
        self, persona: str = "akane_default"
    ) -> str:
        """Retorna a sessão mais recente ou cria uma nova.

        Usado no boot para continuar a última conversa automaticamente.
        """
        sessions = await self.list_sessions(limit=1)
        if sessions:
            session_id = sessions[0]["id"]
            logger.info(
                f"Retomando sessão: {session_id} ({sessions[0]['title']})"
            )
            return session_id

        return await self.create_session(persona=persona)

    async def delete_session(self, session_id: str) -> bool:
        """Deleta uma sessão e todas as suas mensagens."""
        import asyncio

        def _delete():
            self._execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._conn.commit()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _delete)
        logger.info(f"Sessão deletada: {session_id}")
        return True

    # ── Message Management ──

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        emotion: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        """Adiciona uma mensagem à sessão.

        Args:
            session_id: UUID da sessão.
            role: 'user', 'assistant', ou 'system'.
            content: Texto da mensagem.
            emotion: Emoção detectada (opcional).
            metadata: Dados extras em JSON (opcional).

        Returns:
            ID da mensagem inserida.
        """
        import asyncio

        now = datetime.now().isoformat()
        meta_json = json.dumps(metadata or {})

        def _insert():
            cursor = self._execute(
                "INSERT INTO messages (session_id, role, content, emotion, created_at, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, role, content, emotion, now, meta_json),
            )
            self._execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            self._conn.commit()
            return cursor.lastrowid

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _insert)

    async def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Recupera mensagens de uma sessão (mais recentes primeiro).

        Args:
            session_id: UUID da sessão.
            limit: Número máximo de mensagens.
            offset: Pular N mensagens mais recentes.

        Returns:
            Lista de dicts com role, content, emotion, created_at.
        """
        import asyncio

        def _query():
            cursor = self._execute(
                """
                SELECT id, role, content, emotion, created_at, metadata
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ? OFFSET ?
                """,
                (session_id, limit, offset),
            )
            return [dict(row) for row in cursor.fetchall()]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _query)

    async def get_langchain_messages(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list:
        """Recupera mensagens formatadas como LangChain messages.

        Usado para reconstruir o histórico do AkaneBrain após restart.

        Returns:
            Lista de HumanMessage/AIMessage para o LangGraph.
        """
        from langchain_core.messages import AIMessage, HumanMessage

        raw_messages = await self.get_messages(session_id, limit=limit)
        lc_messages = []

        for msg in raw_messages:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))

        return lc_messages

    # ── Search ──

    async def search_messages(
        self, query: str, limit: int = 20
    ) -> list[dict]:
        """Busca mensagens por texto (LIKE search) em todas as sessões."""
        import asyncio

        def _search():
            cursor = self._execute(
                """
                SELECT m.id, m.session_id, m.role, m.content, m.emotion,
                       m.created_at, s.title as session_title
                FROM messages m
                JOIN sessions s ON m.session_id = s.id
                WHERE m.content LIKE ?
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                (f"%{query}%", limit),
            )
            return [dict(row) for row in cursor.fetchall()]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _search)

    # ── Stats ──

    async def get_stats(self) -> dict:
        """Retorna estatísticas gerais do histórico."""
        import asyncio

        def _stats():
            sessions = self._execute(
                "SELECT COUNT(*) as count FROM sessions"
            ).fetchone()
            messages = self._execute(
                "SELECT COUNT(*) as count FROM messages"
            ).fetchone()
            return {
                "total_sessions": sessions["count"],
                "total_messages": messages["count"],
                "db_path": str(self._db_path),
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _stats)

    # ── Cleanup ──

    def close(self) -> None:
        """Fecha a conexão SQLite."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("ChatHistory SQLite fechado.")

    def __repr__(self) -> str:
        return f"<ChatHistoryManager db={self._db_path}>"
