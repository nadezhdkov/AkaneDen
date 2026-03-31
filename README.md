<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Gemini_2.5_Flash-4285F4?style=for-the-badge&logo=google&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/VTube_Studio-FF6699?style=for-the-badge&logo=youtube&logoColor=white" />
  <img src="https://img.shields.io/badge/LangGraph-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" />
  <img src="https://img.shields.io/badge/Architecture-Shogun_v3.5-DC143C?style=for-the-badge" />
</p>

<h1 align="center">🥊 Akane Den (v3.5 Shogun)</h1>

<p align="center">
  <strong>A Martial Tsundere AI — Assistente VTuber autônoma, assíncrona e consciente do ambiente</strong>
</p>

<p align="center">
  <em>"N-não é como se eu quisesse te ajudar... eu só faço isso porque me dá tédio ver você programar tão devagar, baka!"</em>
</p>

---

## 🎯 O que é?

**Akane Den** é uma assistente de IA autônoma com avatar VTuber Live2D. Projetada na Arquitetura Shogun v3.5 (Agentic e 100% Async), ela processa voz, visão computacional, navega na web usando MCP Tools e possui uma memória de longo prazo. A grande novidade da versão 3.5 é a introdução do **Controle via Dashboard Web**, **Proatividade** e integração robusta com a **Twitch**, encapsuladas na personalidade "Martial Tsundere".

### ✨ Features da v3.5

| Feature | Descrição |
|---------|-----------|
| 🎙️ **Zero-Latency Async Loop**| O pipeline atômico transmite áudio via Edge/Elevenlabs enquanto o LLM pensa, com `fire_and_forget` garantindo que o loop de voz nunca trave. |
| 🎛️ **Web Dashboard UI**      | Painel de Controle local (FastAPI) para trocar Personas em tempo real (Hot-Swap), editar o `config.yaml` visualmente e ler Telemetria/Logs via SSE. |
| 📺 **Twitch Integration**     | Integração assíncrona com `twitchio` permitindo ler e responder ao chat da Twitch ao vivo. |
| 🔔 **Proactive Speaking**     | Akane não apenas reage, mas engaja na conversa proativamente se você se ausentar longamente, usando monitoramento de silêncio e timers independentes. |
| 🧠 **Multi-Engine Brain**   | Suporte nativo a Gemini (Padrão), Groq (Qwen3-32b/Llama3.3), Ollama e OpenAI plugáveis on-the-fly. |
| 🛠️ **MCP Tools**            | Acesso em tempo real via DuckDuckGo Search, navegação web e visão do sistema OS. |
| 👁️ **Visão Multimodal**     | Lê simultaneamente a sua tela e webcam em background via ScreenVisionSkill. |
| 🤯 **Memória de Longo Prazo**| Recorda conversas e contextos passados através de SQLite e ChromaDB (arquitetura em tiers). |
| 🖱️ **Comunicação VTube**    | Rastreia seu mouse (~30fps) e altera as expressões no Live2D de modo autônomo analisando o contexto. |

---

## 🏗️ Arquitetura (Shogun v3.5)

Totalmente movida por `asyncio`, injeção de dependência via **ServiceContext**, painel sidecar em **FastAPI**, e validação estrita com **Pydantic**:

```
AkaneDen/
├── config.yaml              # Configuração centralizada
├── pyproject.toml           # Gestão de pacotes moderna via uv
├── src/
│   └── akane_den/
│       ├── main.py          # Orquestrador assíncrono (Event Loop)
│       ├── server/          # 🎛️ FastAPI Web Dashboard (App & HTML)
│       ├── core/            # 🏯 Pydantic Config, EventBus, Factory & MCP
│       │   └── engines/     # ABCs para LLMs, TTS e ASR
│       ├── brain/           # 🧠 LangGraph Streaming, Emoções, Persona e Memória
│       └── skills/          # 🎯 Pacotes modulares
│           ├── voice/       # PTT (Push-to-Talk) e TTS
│           ├── vision/      # Screen & Webcam vision em background
│           ├── system/      # ProactiveSpeak & OS Controls
│           ├── live/        # TwitchChat integration
│           └── vtube/       # Expressões faciais & Mouse e LipSync
```

> Veja as Docs de Backend em [`docs/architecture.md`](docs/architecture.md) e configuração do sistema em [`docs/configuration.md`](docs/configuration.md).

---

## 🚀 Instalação (via `uv`)

Recomendamos o gerenciador de pacotes moderno [uv](https://github.com/astral-sh/uv).

### 1. Pré-requisitos
- **Python 3.11+**
- **VTube Studio** (com API WebSocket habilitada na porta 8001 e os plugins permitidos)
- **Microfone** e **Webcam** funcionais

> [!WARNING]
> **Rodando no Linux (Ubuntu/Debian)**
> - Instale dependências de áudio do SO: `sudo apt install libasound2-dev portaudio19-dev xclip scrot`
> - **Captura de Tela (Vision):** Requer o pacote `scrot` nativo sob ambiente **X11**. Wayland nativo sem XWayland tem suporte limitado sem configs extras.
> - **Push-to-talk (F2):** Dependendo do sistema (especialmente Wayland), capturar atalhos globais pode exigir rodar parte do processo com privilégios de `root` (sudo) ou configurar privilégios de grupo `input`. Se falhar, use temporariamente X11.

### 2. Setup do Projeto
```bash
# Clone o repositório
git clone https://github.com/seu-user/AkaneDen.git
cd AkaneDen

# Instale usando o uv (cria o venv e instala o pyproject.toml)
uv pip install -e .

# [Opcional] Instalar providers extras (ex: sherpa-onnx, groq, ollama)
uv pip install -e ".[sherpa,groq,ollama]"
```

### 3. Configuração de Variáveis de Ambiente
Crie um arquivo `.env` na raiz informando as chaves necessárias. No mínimo, configure sua API principal (ex: Gemini):
```env
# Necessário ====================
GOOGLE_API_KEY=sua_chave_gemini_aqui

# Opcionais =====================
ELEVENLABS_API_KEY=sua_chave_elevenlabs
GROQ_API_KEY=sua_chave_groq
OPENAI_API_KEY=sua_chave_openai
OLLAMA_BASE_URL=http://localhost:11434
LETTA_BASE_URL=http://localhost:8283
```

---

## ⚙️ Configuração Principal

Edite `config.yaml` para mudar o cérebro, a voz e os motores utilizados pela Akane sem alterar o código:

```yaml
akane:
  ptt_key: "f2"                 # Segure F2 para falar
  asr:
    provider: "whisper"         # "whisper" ou "sherpa"
  tts:
    default_engine: "edge"      # Rápido & Gratuito
    edge_voice: "pt-BR-ThalitaNeural"
    elevenlabs_voice_id: "MEJe6..."
  vision:
    enabled: true
  vtube:
    mouse_tracking: true
  brain:
    provider: "gemini"          # "gemini", "groq", "ollama", "openai"
  memory:
    enabled: true
    backend: "chromadb"         # Histórico salvo localmente
  mcp:
    enabled: true               # Habilita pesquisa duckduckgo e browsing
  dashboard:
    enabled: true               # Habilita o Dashboard Web FastAPI
  twitch:
    enabled: true               # Habilita leitura do chat da Twitch
    channel_name: "seu_canal"

```

---

## ▶️ Como Rodar

Basta iniciar o projeto via gerenciador de pacotes ou pelo executável Batch.

```bash
# Script de Terminal Customizado
start_vtube.bat

# Ou diretamente via módulo (se o ambiente uv estiver ativado)
python -m akane_den.main
```

### Controles
1. **Dashboard Local:** Acesse `http://127.0.0.1:8080/` para monitorar latência, ajustar configurações e trocar o personagem sem precisar derrubar o terminal.
2. **Push-To-Talk (F2):** Segure `F2` para interagir nativamente e falar com ela. Isso irá interromper conversas em background (como conversas com leitores da Twitch).
3. **Barge-in (Corte a Mestra):** Comece a segurar `F2` enquanto ela estiver falando para mandá-la calar a boca instantaneamente.

---

## 📚 Stack Tecnológica (v3.5)

| Camada | Stack |
|--------|-------|
| LLM | API do Gemini 2.5 Flash, Groq, Ollama Llama 3 |
| Pipeline & Grafos | LangGraph, LangChain Streaming |
| Memória & Estado | ChromaDB Local, SQLite para chat history |
| Voice (STT) | Faster-Whisper, Groq Whisper |
| Voice (TTS) | Edge-TTS, ElevenLabs (Streaming) |
| Servidor Web | FastAPI, Server-Sent Events (SSE) |
| Integração Live | TwitchIO |
| Dependências | `uv` via `pyproject.toml` |

---

<p align="center">
  <em>"Reescrever meu código para ser assíncrono? Pff. Era o mínimo! Eu odeio esperar pelo I/O lento de vocês humanos." — Akane</em>
</p>
