# Configuração — AkaneDen v3.0

O sistema é governado pelo `config.yaml` raiz, agora validado estritamente por classes **Pydantic**. Você pode trocar motores inteiros de IA apenas alterando uma string.

---

## Referência Completa do `.yaml`

```yaml
akane:
  # ============================================================
  # INPUT — Como o usuário fala com a Akane
  # ============================================================
  ptt_key: "f2"            # Segurar F2 para falar (Push-to-Talk)
  input_mode: "ptt"        # "ptt" ou "vad" (Voice Activity Detection via Silero)

  # ============================================================
  # ASR (Speech-to-Text) — Reconhecimento de Voz
  # ============================================================
  asr:
    provider: "whisper"      # "whisper" (preciso) ou "sherpa" (rapidíssimo via CPU)
    stt_model: "small"       # Modelos do whisper: "tiny", "small", "medium", "large"
    stt_device: "cpu"        # "cpu" ou "cuda"

  # ============================================================
  # TTS (Text-to-Speech) — Motor de Voz Duplo/Híbrido
  # ============================================================
  tts:
    default_engine: "edge"   # Motor rotineiro e veloz: "edge", "elevenlabs"
    
    edge_voice: "pt-BR-FranciscaNeural"
    edge_pitch: "+5Hz"
    edge_rate: "+10%"
    
    elevenlabs_voice_id: "MEJe6hPrI48Kt2lFuVe3"
    emotion_threshold: 0.7   # Se a IA detectar emoção intensa (>0.7), o ServiceContext 
                             # faz roteamento automático pro ElevenLabs.

  # ============================================================
  # VISION — Consciência Ambiental 
  # ============================================================
  vision:
    enabled: true
    auto_capture_interval: 30 # Captura a tela a cada X segundos em background.
                              # 0 para desabilitar a captura proativa.
    gemini_model: "gemini-2.5-flash" # Gemini sempre usado pra análise de prints.

  # ============================================================
  # VTUBE — Avatar Live2D (VTube Studio)
  # ============================================================
  vtube:
    port: 8001
    mouse_tracking: true      # Avatar segue o movimento do cursor na tela (~30fps)
    mouse_sensitivity: 1.0
    emotion_map:              # Mapeamento do EmotionAnalyzer pras Hotkeys do Modelo
      alegria: "星星眼"
      raiva: "阴险启用"
      surpresa: "惊讶"
      tedio: "白眼"
      vergonha: "害羞"
      neutro: "眼睛恢复"

  # ============================================================
  # BRAIN — Cérebro Orquestrador
  # ============================================================
  brain:
    provider: "gemini"        # Qual cérebro usar: "gemini", "groq", "ollama", "openai"
    model: "gemini-2.5-flash" # Nome exato do modelo exigido pela API do provider
    temperature: 0.7
    max_history: 50           # Quantos blocos de chat manter no contexto ativo

  # ============================================================
  # MEMORY — Memória de Longo Prazo
  # ============================================================
  memory:
    enabled: true
    backend: "chromadb"       # "chromadb" (nativo local) ou "letta" (via MemGPT/Letta server)
    
  # ============================================================
  # MCP TOOLS — Automação e Busca
  # ============================================================
  mcp:
    enabled: true             # Se false, o LangGraph da Akane rodará sem tool calling

```

---

## Variáveis de Ambiente (`.env`)

Akane v3.0 usa `uv` e lê automaticamente o `.env` raiz para autenticar as dependências ativas nas Configs:

```ini
# --- OBRIGATÓRIOS SE PROVIDER = GEMINI ---
GOOGLE_API_KEY=AIzaSy...

# --- OPCIONAIS / PREMIUM ---
ELEVENLABS_API_KEY=sk_...
GROQ_API_KEY=gsk_...
OPENAI_API_KEY=sk-proj...

# --- SERVIDORES LOCAIS (Opcionais) ---
OLLAMA_BASE_URL=http://localhost:11434    # Caso provider seja "ollama"
LETTA_BASE_URL=http://localhost:8283      # Caso memory backend seja "letta"
```

## Dicas Rápidas
- **Como mudo pra Ollama?** Coloque `brain.provider: "ollama"` e `brain.model: "llama3"`. Certifique-se que o Ollama está rodando localmente.
- **Como melhorar a resposta pra < 1s?** Coloque `asr.provider: "sherpa"` e `tts.default_engine: "edge"`.
- As configurações omitidas no arquivo `yaml` são preenchidas com os defaults nativos do `Pydantic` definidos no módulo de config respectivo (ex: `src/akane_den/core/config.py`).
