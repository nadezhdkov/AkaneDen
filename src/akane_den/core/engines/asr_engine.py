"""
ASREngine — Interface abstrata e implementações para provedores de ASR.

Padrão Factory: cada provedor herda de ASREngine e implementa
transcribe() assíncrono.

Provedores implementados:
    - WhisperASREngine (default, faster-whisper via ProcessPoolExecutor)
    - SherpaOnnxASREngine (opcional, SenseVoiceSmall int8)
    - GroqWhisperASREngine (API, ultra-rápido via Groq)

v3.3: Whisper migrado para ProcessPoolExecutor para contornar o GIL.
      O modelo é pré-carregado no processo worker para evitar cold-start.

"Fala mais alto, baka! E não culpe meu ouvido digital se você
gagueja que nem um CD riscado!" — Akane
"""

from __future__ import annotations

import asyncio
import functools
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from loguru import logger

from akane_den.core.config import AkaneConfig


class ASREngine(ABC):
    """Interface abstrata para provedores de Speech-to-Text."""

    def __init__(self, config: AkaneConfig) -> None:
        self.config = config

    @abstractmethod
    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> str:
        """Transcreve áudio float32 para texto.

        Args:
            audio: Array NumPy float32 normalizado (-1.0 a 1.0).
            sample_rate: Taxa de amostragem do áudio.

        Returns:
            Texto transcrito.
        """
        ...

    @abstractmethod
    async def setup(self) -> None:
        """Carrega modelos pesados (chamado no boot)."""
        ...

    def shutdown(self) -> None:
        """Libera recursos pesados (override opcional)."""
        pass

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Nome do motor ASR ativo."""
        ...


# ──────────────────────────────────────────────
# Worker Functions (top-level para pickle/spawn)
# ──────────────────────────────────────────────
# Essas funções vivem no escopo do módulo porque o
# ProcessPoolExecutor precisa serializá-las via pickle.
# O modelo é carregado UMA VEZ no initializer do worker.

_whisper_worker_model = None


def _init_whisper_worker(
    model_size: str,
    device: str,
    compute_type: str,
    language: str,
) -> None:
    """Initializer do ProcessPoolExecutor — carrega o modelo no worker.

    Executado UMA VEZ quando o processo worker inicia. O modelo fica
    em memória persistente no worker, evitando cold-start a cada chamada.
    """
    global _whisper_worker_model
    from faster_whisper import WhisperModel

    _whisper_worker_model = {
        "model": WhisperModel(model_size, device=device, compute_type=compute_type),
        "language": language,
    }


def _transcribe_in_worker(audio: np.ndarray) -> str:
    """Função de transcrição executada no processo worker.

    Usa o modelo pré-carregado pelo initializer. Como roda em processo
    separado, o GIL do worker NÃO afeta o event loop principal.
    """
    global _whisper_worker_model
    if _whisper_worker_model is None:
        raise RuntimeError("Worker não inicializado! Modelo Whisper ausente.")

    model = _whisper_worker_model["model"]
    language = _whisper_worker_model["language"]

    segments, _info = model.transcribe(
        audio,
        language=language,
        beam_size=1,
        vad_filter=True,
        without_timestamps=True,
    )
    return " ".join(seg.text for seg in segments).strip()


# ──────────────────────────────────────────────
# Implementação: Faster-Whisper (Default)
# ──────────────────────────────────────────────


class WhisperASREngine(ASREngine):
    """ASR Engine usando faster-whisper (CTranslate2) em ProcessPoolExecutor.

    v3.3: A inferência roda em um processo separado para contornar o GIL.
    O modelo é pré-carregado no worker via initializer, eliminando
    latência de cold-start. Isso resolve os 12.5s de event loop starvation.
    """

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        self._model_size = config.asr.model_size
        self._device = config.asr.device
        self._language = config.asr.language
        self._compute_type = "int8" if self._device == "cpu" else "float16"
        self._executor: ProcessPoolExecutor | None = None

    async def setup(self) -> None:
        """Cria o ProcessPoolExecutor com o modelo Whisper pré-carregado.

        O initializer do executor carrega o modelo no worker ANTES da
        primeira chamada, garantindo zero latência de cold-start.

        v3.5: Se CUDA falhar (cublas64_12.dll ausente, etc.), faz fallback
        automático para CPU/int8 sem crashar o sistema.
        """
        await self._try_create_executor(self._device, self._compute_type)

    async def _try_create_executor(
        self, device: str, compute_type: str
    ) -> None:
        """Tenta criar o executor. Se CUDA falhar, faz fallback para CPU."""
        logger.info(
            f"Criando ProcessPoolExecutor para Whisper '{self._model_size}' "
            f"({device}, {compute_type})..."
        )

        loop = asyncio.get_running_loop()

        # Cria o executor com initializer que pré-carrega o modelo
        self._executor = ProcessPoolExecutor(
            max_workers=1,
            initializer=_init_whisper_worker,
            initargs=(
                self._model_size,
                device,
                compute_type,
                self._language,
            ),
        )

        # Força o worker a inicializar AGORA (warm-up)
        try:
            await loop.run_in_executor(
                self._executor,
                _transcribe_in_worker,
                np.zeros(1600, dtype=np.float32),  # 0.1s de silêncio
            )
            logger.success(
                f"Whisper '{self._model_size}' carregado em processo worker "
                f"({device}/{compute_type}, PID isolado, GIL independente)."
            )
            # Atualiza device/compute_type efetivos
            self._device = device
            self._compute_type = compute_type

        except Exception as e:
            error_msg = str(e).lower()
            is_cuda_error = any(
                kw in error_msg
                for kw in ("cublas", "cuda", "cudnn", "gpu", "nvrtc")
            )

            if is_cuda_error and device != "cpu":
                logger.warning(
                    f"⚠ CUDA indisponível ({e}). "
                    f"Fazendo fallback para CPU/int8..."
                )
                # Mata o executor quebrado
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None
                # Recria com CPU
                await self._try_create_executor("cpu", "int8")
            else:
                # Warm-up pode retornar vazio (esperado)
                logger.warning(
                    f"Warm-up do worker concluído com aviso "
                    f"(esperado para áudio vazio): {e}"
                )
                logger.success(
                    f"Whisper '{self._model_size}' carregado em "
                    f"processo worker ({device}/{compute_type})."
                )

    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> str:
        """Transcreve áudio em processo separado (GIL-free, non-blocking).

        O áudio é serializado e enviado ao worker via ProcessPoolExecutor.
        A CPU-bound inference roda em processo separado com GIL independente,
        sem afetar o event loop do asyncio.
        """
        if self._executor is None:
            raise RuntimeError(
                "ProcessPool não criado. Chame setup() primeiro."
            )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, _transcribe_in_worker, audio
        )

    def shutdown(self) -> None:
        """Encerra o ProcessPoolExecutor e libera o processo worker."""
        if self._executor:
            logger.info("Encerrando ProcessPool do Whisper...")
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
            logger.info("ProcessPool do Whisper encerrado.")

    @property
    def engine_name(self) -> str:
        return f"whisper-{self._model_size}"


# ──────────────────────────────────────────────
# Implementação: Sherpa-onnx (Opcional, SenseVoiceSmall)
# ──────────────────────────────────────────────


class SherpaOnnxASREngine(ASREngine):
    """ASR Engine usando sherpa-onnx com SenseVoiceSmall int8.

    Mais rápido que Whisper em CPU. Requer instalação opcional:
        uv pip install 'akane-den[sherpa]'
    """

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        self._recognizer = None
        self._model_path = config.asr.sherpa_model_path
        self._tokens_path = config.asr.sherpa_tokens_path

    async def setup(self) -> None:
        """Inicializa o reconhecedor Sherpa-onnx."""
        try:
            import sherpa_onnx

            logger.info("Inicializando Sherpa-onnx ASR (SenseVoiceSmall int8)...")

            # SenseVoiceSmall config
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=self._model_path,
                tokens=self._tokens_path,
                use_itn=True,
                num_threads=4,
                debug=False,
            )

            logger.success("Sherpa-onnx ASR inicializado.")

        except ImportError:
            raise ImportError(
                "sherpa-onnx não instalado! Instale com: "
                "uv pip install 'akane-den[sherpa]'"
            )
        except Exception as e:
            logger.error(f"Falha ao inicializar Sherpa-onnx: {e}")
            raise

    def _transcribe_sync(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcrição síncrona com sherpa-onnx."""
        import sherpa_onnx

        stream = self._recognizer.create_stream()

        # sherpa-onnx espera float32 samples
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        stream.accept_waveform(sample_rate, audio.tolist())
        self._recognizer.decode_stream(stream)

        return stream.result.text.strip()

    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> str:
        """Transcreve áudio em thread pool (non-blocking)."""
        if self._recognizer is None:
            raise RuntimeError(
                "Sherpa-onnx não inicializado. Chame setup() primeiro."
            )

        from akane_den.core.runtime import run_in_heavy_thread
        return await run_in_heavy_thread(
            self._transcribe_sync, audio, sample_rate
        )

    @property
    def engine_name(self) -> str:
        return "sherpa-onnx-sensevoice"


# ──────────────────────────────────────────────
# Implementação: Groq Whisper (API, ultra-rápido)
# ──────────────────────────────────────────────


class GroqWhisperASREngine(ASREngine):
    """ASR Engine usando Groq Whisper API.

    A Groq oferece inferência ultra-rápida de Whisper via API.
    Requer GROQ_API_KEY no ambiente.

    Ideal para quando velocidade é prioridade sobre privacidade,
    já que o áudio é enviado para a nuvem.
    """

    def __init__(self, config: AkaneConfig) -> None:
        super().__init__(config)
        self._client = None
        self._language = config.asr.language
        self._model = config.asr.groq_whisper_model

    async def setup(self) -> None:
        """Inicializa o cliente Groq."""
        import os

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY não encontrada no ambiente! "
                "Configure no .env ou via Dashboard."
            )

        try:
            from groq import Groq

            self._client = Groq(api_key=api_key)
            logger.success(
                f"Groq Whisper ASR inicializado (model={self._model})."
            )
        except ImportError:
            raise ImportError(
                "groq não instalado! Instale com: "
                "uv pip install groq"
            )

    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> str:
        """Transcreve áudio via Groq Whisper API.

        Converte o array NumPy para WAV temporário e envia via API.
        Roda em thread pool para não bloquear o event loop.
        """
        if self._client is None:
            raise RuntimeError(
                "Groq Whisper não inicializado. Chame setup()."
            )

        from akane_den.core.runtime import run_in_io
        return await run_in_io(
            self._transcribe_sync, audio, sample_rate
        )

    def _transcribe_sync(
        self, audio: np.ndarray, sample_rate: int
    ) -> str:
        """Transcrição síncrona via Groq API."""
        import io
        import wave

        # Converte float32 → int16 WAV em memória
        audio_int16 = (audio * 32767).astype(np.int16)
        buffer = io.BytesIO()

        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())

        buffer.seek(0)
        buffer.name = "audio.wav"  # groq client needs .name

        transcription = self._client.audio.transcriptions.create(
            file=buffer,
            model=self._model,
            language=self._language,
            response_format="text",
        )

        return transcription.strip() if isinstance(transcription, str) else str(transcription).strip()

    @property
    def engine_name(self) -> str:
        return f"groq-whisper-{self._model}"
