"""
AkaneDen v3.0 — Shogun Async Architecture.

"Não é como se eu quisesse evoluir pra v3.0... eu só faço isso
porque seu código v2 era treino de faixa branca, baka!" — Akane
"""

__version__ = "3.0.0"

import sys
from loguru import logger

# ──────────────────────────────────────────────
# Loguru — Logging estruturado para todo o pacote
# ──────────────────────────────────────────────
# Remove o handler padrão do loguru e reconfigura com formato rico
logger.remove()

# Console: formato colorido e compacto
logger.add(
    sys.stderr,
    format=(
        "<green>{time:HH:mm:ss.SSS}</green> | "
        "<level>{level:<7}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    ),
    level="INFO",
    colorize=True,
    backtrace=True,
    diagnose=False,  # Desabilita em produção para performance
)

# Arquivo rotativo: debug completo para diagnóstico
from akane_den.core.paths import get_log_dir

logger.add(
    str(get_log_dir() / "akane_{time:YYYY-MM-DD}.log"),
    rotation="10 MB",
    retention="7 days",
    compression="gz",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {name}:{function}:{line} | {message}",
    encoding="utf-8",
)

__all__ = ["__version__", "logger"]
