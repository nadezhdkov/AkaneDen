import os
from pathlib import Path

def get_base_dir() -> Path:
    """Retorna o diretório base do projeto (agnóstico de SO).

    Ordem de resolução:
    1. AKANE_BASE_DIR env var (override manual)
    2. Raiz do projeto relativa a este arquivo (4 níveis acima)
       src/akane_den/core/paths.py → project_root/
    """
    env_dir = os.environ.get("AKANE_BASE_DIR")
    if env_dir:
        return Path(env_dir).resolve()

    # Resolve raiz do projeto a partir da posição deste arquivo.
    # Funciona em Windows, Linux, macOS, e dentro de containers.
    return Path(__file__).resolve().parent.parent.parent.parent

BASE_DIR = get_base_dir()

def get_log_dir() -> Path:
    d = BASE_DIR / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_db_dir() -> Path:
    d = BASE_DIR / "local_chroma_db"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_models_dir() -> Path:
    d = BASE_DIR / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d
