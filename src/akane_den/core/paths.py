import os
import sys
from pathlib import Path

def get_base_dir() -> Path:
    """Retorna o diretório base do projeto dependendo do SO.
    No Windows, usa a raiz do projeto atual.
    No Linux, usa ~/akane_den (expande o ~) ou o env AKANE_BASE_DIR.
    """
    env_dir = os.environ.get("AKANE_BASE_DIR")
    if env_dir:
        return Path(env_dir).resolve()

    if sys.platform == "linux":
        linux_dir = Path.home() / "akane_den"
        linux_dir.mkdir(parents=True, exist_ok=True)
        return linux_dir

    # Windows ou default: root do projeto (4 níveis acima deste arquivo)
    # src/akane_den/core/paths.py -> root/
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
