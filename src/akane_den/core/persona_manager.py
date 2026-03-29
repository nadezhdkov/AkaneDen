"""
Gerenciador de Personas (Character Profiles).

Carrega e compila perfis YAML em modelos Pydantic validados,
permitindo trocar completamente a mente, voz e visuais da assistente.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from loguru import logger

from akane_den.core.models.persona import PersonaProfile


class PersonaManager:
    """Carrega dados das Personas a partir do diretório agents/persona/."""

    def __init__(self, personas_dir: str | Path | None = None) -> None:
        if personas_dir is None:
            # Caminho dinâmico caso a execução venha de src/akane_den/main.py
            base_path = Path(__file__).parent.parent
            self.personas_dir = base_path / "agents" / "persona"
        else:
            self.personas_dir = Path(personas_dir)

    def load_persona(self, persona_name: str) -> PersonaProfile:
        """Lê e realiza o parsing do yaml de persona."""
        if not persona_name.endswith(".yaml"):
            persona_name += ".yaml"

        target_file = self.personas_dir / persona_name

        if not target_file.exists():
            logger.error(f"Arquivo de persona '{target_file}' não encontrado.")
            raise FileNotFoundError(f"Persona {persona_name} não encontrada em {self.personas_dir}")

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            profile = PersonaProfile(**data)
            logger.info(f"Persona carregada com sucesso: {profile.name} v{profile.version}")
            return profile

        except yaml.YAMLError as exc:
            logger.error(f"Erro de sintaxe no yaml da persona: {exc}")
            raise
        except Exception as exc:
            logger.error(f"Falha de validação da Persona '{persona_name}': {exc}")
            raise
