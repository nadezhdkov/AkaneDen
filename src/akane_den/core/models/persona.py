"""
Modelos Pydantic para validação de Character Profiles (Personas). 
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class PersonaVoiceConfig(BaseModel):
    """Configurações específicas de voz para a Persona, que podem sobrescrever o config global."""

    elevenlabs_voice_id: Optional[str] = None
    edge_voice: Optional[str] = None


class PersonaProfile(BaseModel):
    """
    O Perfil Mental e Estrutural de um personagem.
    Guarda instruções, padrões emocionais, mapeamentos do VTube, etc.
    """

    name: str
    version: str = "1.0"
    
    # Textos de injeção no System Prompt
    base_prompt: str
    templates: Dict[str, str] = Field(default_factory=dict)
    
    # Análise de emoções (Mapeamento de Emoção -> RegEx lists)
    emotion_patterns: Dict[str, List[str]] = Field(default_factory=dict)
    
    # Mapeamento dinâmico para hotkeys do VTube Studio
    vtube_mapping: Dict[str, str] = Field(default_factory=dict)

    # Configurações de Voz específicas (Opcional)
    voice_config: PersonaVoiceConfig = Field(default_factory=PersonaVoiceConfig)
