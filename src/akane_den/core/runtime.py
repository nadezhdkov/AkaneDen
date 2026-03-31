"""
Runtime — Gerenciamento de Concorrência e Event Loop da AkaneDen

Define os executores dedicados para diferentes tipos de carga de trabalho,
evitando que operações bloqueantes causem "Event Loop Starvation".

- IO_POOL: Para chamadas de rede lentas (APIs, web requests).
- DB_POOL: ThreadPool isolado para ChromaDB (evita problemas de pickle e GIL locks não-CPU).
- CPU_POOL: ProcessPool padrão para cálculo pesado puro em Python.
- HEAVY_THREAD_POOL: Para bibliotecas C++/Rust que liberam o GIL mas não são picklable (ex: Sherpa-Onnx).
"""

import asyncio
import concurrent.futures
from typing import Any, Callable

from loguru import logger

# Pool para I/O leve e de rede (APIs LLM, chamadas HTTP)
IO_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="AkaneIO"
)

# Pool dedicado para Banco de Dados local (ChromaDB)
# O ChromaDB usa SQLite e C++ bindings que não sobrevivem ao pickle
# de um ProcessPool, por isso usamos um ThreadPool isolado.
DB_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="AkaneDB"
)

# Pool para inferência local e extensões C++ que liberam o GIL
# Ideal para Sherpa-Onnx, OpenCV, Numpy heavy ops.
HEAVY_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="AkaneHeavy"
)

# Pool para CPU-bound em Python puro (quando serializável via pickle)
CPU_POOL = concurrent.futures.ProcessPoolExecutor(
    max_workers=2
)


async def run_in_io(func: Callable, *args: Any) -> Any:
    """Executa de forma segura no pool de roteamento I/O."""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(IO_POOL, func, *args)
    except Exception as e:
        logger.error(f"[IO_POOL] Erro na execução de {func.__name__}: {e}")
        raise


async def run_in_db(func: Callable, *args: Any) -> Any:
    """Executa de forma segura no pool de Banco de Dados."""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(DB_POOL, func, *args)
    except Exception as e:
        logger.error(f"[DB_POOL] Erro na execução de {func.__name__}: {e}")
        raise


async def run_in_heavy_thread(func: Callable, *args: Any) -> Any:
    """Executa num ThreadPool dedicado para tarefas pesadas não picklables."""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(HEAVY_THREAD_POOL, func, *args)
    except Exception as e:
        logger.error(f"[HEAVY_THREAD_POOL] Erro em {func.__name__}: {e}")
        raise


async def run_in_cpu(func: Callable, *args: Any) -> Any:
    """Executa no pool de Processos (requer serialização via pickle)."""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(CPU_POOL, func, *args)
    except Exception as e:
        logger.error(f"[CPU_POOL] Erro no worker de {func.__name__}: {e}")
        raise
