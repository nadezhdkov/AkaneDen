"""
VADEngine — Voice Activity Detection (Fallback Opcional).

Motor de detecção de voz para modo hands-free. DESATIVADO por padrão.
O modo primário de entrada é PTT (Push-to-Talk, F2).

Provedores implementados:
    - SileroVADEngine (preciso, leve, CPU-friendly)

"Ficar ouvindo você o tempo inteiro? Que inferno!
 Aperte a tecla quando quiser falar, baka!" — Akane
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections import deque

import numpy as np
from loguru import logger

from akane_den.core.config import AkaneConfig


class VADEngine(ABC):
    """Interface abstrata para Voice Activity Detection."""

    def __init__(self, config: AkaneConfig) -> None:
        self.config = config

    @abstractmethod
    async def setup(self) -> None:
        """Carrega modelo VAD."""
        ...

    @abstractmethod
    def is_speech(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> bool:
        """Determina se o chunk de áudio contém fala.

        Args:
            audio_chunk: Array float32 com amostras de áudio.
            sample_rate: Taxa de amostragem.

        Returns:
            True se há fala detectada.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reseta estado interno do VAD."""
        ...

    def shutdown(self) -> None:
        """Libera recursos do VAD (override opcional)."""
        pass

    @property
    @abstractmethod
    def engine_name(self) -> str:
        ...


class SileroVADEngine(VADEngine):
    """VAD Engine usando Silero VAD (PyTorch).

    Silero é leve (~1MB), preciso e roda em CPU sem problemas.
    Usa windowed detection com smoothing para evitar falsos positivos.

    Configuração via config.yaml:
        vad:
          enabled: false          # DESATIVADO por padrão
          provider: "silero"
          threshold: 0.5          # Sensibilidade (0.0–1.0)
          min_speech_ms: 250      # Duração mínima de fala para trigger
          min_silence_ms: 1000    # Silêncio mínimo para end-of-utterance
          window_size_ms: 30      # Tamanho da janela de análise
    """

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        self._model = None
        self._utils = None

        vad_cfg = config.vad
        self._threshold = vad_cfg.threshold
        self._min_speech_ms = vad_cfg.min_speech_ms
        self._min_silence_ms = vad_cfg.min_silence_ms
        self._window_size_ms = vad_cfg.window_size_ms

        # State tracking
        self._speech_count = 0
        self._silence_count = 0
        self._is_speaking = False

        # Smoothing buffer (últimas N decisões)
        self._decisions: deque[bool] = deque(maxlen=5)

    async def setup(self) -> None:
        """Carrega o modelo Silero VAD via torch.hub."""
        try:
            import torch

            logger.info("Carregando Silero VAD...")

            loop = asyncio.get_running_loop()

            def _load_model():
                model, utils = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    trust_repo=True,
                )
                return model, utils

            self._model, self._utils = await loop.run_in_executor(
                None, _load_model
            )
            logger.success("Silero VAD carregado com sucesso.")

        except ImportError:
            raise ImportError(
                "torch não instalado! VAD Silero requer PyTorch. "
                "Instale com: uv pip install torch"
            )

    def is_speech(
        self, audio_chunk: np.ndarray, sample_rate: int = 16000
    ) -> bool:
        """Detecta fala usando Silero VAD com smoothing.

        O smoothing evita triggers falsos — uma única janela com
        fala não ativa o VAD. É necessário que a maioria das últimas
        N janelas detectem fala.
        """
        import torch

        if self._model is None:
            raise RuntimeError("Silero VAD não inicializado. Chame setup().")

        # Converte para tensor
        if audio_chunk.dtype != np.float32:
            audio_chunk = audio_chunk.astype(np.float32)

        tensor = torch.from_numpy(audio_chunk)

        # Inferência VAD
        confidence = self._model(tensor, sample_rate).item()
        is_voice = confidence >= self._threshold

        # Smoothing
        self._decisions.append(is_voice)
        smoothed = sum(self._decisions) > len(self._decisions) / 2

        # Contagem de duração
        window_ms = self._window_size_ms
        if smoothed:
            self._speech_count += window_ms
            self._silence_count = 0
        else:
            self._silence_count += window_ms
            if self._silence_count >= self._min_silence_ms:
                self._speech_count = 0

        # Determina estado
        if not self._is_speaking and self._speech_count >= self._min_speech_ms:
            self._is_speaking = True
            logger.debug(
                f"VAD: Fala detectada (confiança={confidence:.2f})"
            )
        elif self._is_speaking and self._silence_count >= self._min_silence_ms:
            self._is_speaking = False
            logger.debug(
                f"VAD: Silêncio detectado após {self._silence_count}ms"
            )

        return self._is_speaking

    def reset(self) -> None:
        """Reseta estado do VAD para nova utterance."""
        self._speech_count = 0
        self._silence_count = 0
        self._is_speaking = False
        self._decisions.clear()
        if self._model is not None:
            self._model.reset_states()

    @property
    def engine_name(self) -> str:
        return "silero-vad"
