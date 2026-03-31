# Configuração — AkaneDen v3.5

O sistema é governado pelo `config.yaml` raiz, agora validado estritamente por classes **Pydantic v2**. Você pode trocar motores inteiros de IA apenas alterando o configuration file, e com a v3.5, essas mudanças podem ser recarregadas __em tempo real__ pelo Web Dashboard sem reiniciar o processo.

---

## Referência Completa do `.yaml`

```yaml
akane:
  # ============================================================
  # INPUT — Como o usuário fala com a Akane
  # ============================================================
  ptt_key: "f2"            # Segurar F2 para falar (Push-to-Talk)
                           # PTT aborta instantaneamente qualquer TTS tocando.

  # ============================================================
  # ASR (Speech-to-Text) — Reconhecimento de Voz
  # ============================================================
  asr:
    provider: "whisper"      # Motor de prioridade.
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
    max_history: 50           # Quantidade de mensagens retidas na Memória Tier 1 (SQLite)

  # ============================================================
  # MEMORY — Memória de Longo Prazo
  # ============================================================
  memory:
    enabled: true
    backend: "chromadb"       # Persiste contexto semântico (Tier 2)

  # ============================================================
  # MCP TOOLS — Automação e Busca
  # ============================================================
  mcp:
    enabled: true             # Se false, o LangGraph da Akane rodará sem tool calling

  # ============================================================
  # UI & LIVE — Interação Multicanal (v3.5)
  # ============================================================
  dashboard:
    enabled: true
    host: "127.0.0.1"
    port: 8080                # Acessar via navegador para ver Logs SSE e Configurações

  twitch:
    enabled: true
    channel_name: "seu_canal" # Lê o chat ao vivo e adiciona cooldowns entre mensagens.

  proactive_speak:
    enabled: true
    timeout_seconds: 300      # Se o usuário e a Twitch não falarem por 5 mins, Akane 
                              # puxa um assunto aleatoriamente.
```

---

## Variáveis de Ambiente (`.env`)

Akane v3.5 usa `uv` e lê automaticamente o `.env` raiz para autenticar as dependências ativas nas Configs:

```ini
# --- OBRIGATÓRIOS SE PROVIDER = GEMINI ---
GOOGLE_API_KEY=AIzaSy...

# --- INTEGRAÇÕES PREMIUM E LIVE ---
ELEVENLABS_API_KEY=sk_...
GROQ_API_KEY=gsk_...
OPENAI_API_KEY=sk-proj...
TWITCH_OAUTH_TOKEN=oauth:seutokenaqui

# --- SERVIDORES LOCAIS (Opcionais) ---
OLLAMA_BASE_URL=http://localhost:11434    # Caso provider seja "ollama"
```

## Dicas Rápidas
- **Como mudo pra Ollama?** Coloque `brain.provider: "ollama"` e `brain.model: "llama3"`.
- **Como a Twitch funciona?** A Akane lerá o chat. Se ela achar que o que foi dito vale a pena, ela responde em voz alta. O seu Push-To-Talk (F2) SEMPRE tem prioridade máxima e interrompe a conversa dela com o chat.
- **Hot-Swapping**: Você pode abrir `http://localhost:8080/`, mudar qualquer configuração de Personality ou de Sistema e salvar. O backend reinjetará sem fechar o bot.
