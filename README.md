<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Gemini_2.5_Flash-4285F4?style=for-the-badge&logo=google&logoColor=white" />
  <img src="https://img.shields.io/badge/VTube_Studio-FF6699?style=for-the-badge&logo=youtube&logoColor=white" />
  <img src="https://img.shields.io/badge/LangGraph-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" />
  <img src="https://img.shields.io/badge/Architecture-Shogun_v3.0-DC143C?style=for-the-badge" />
</p>

<h1 align="center">🥊 Akane Den (v3.0 Async)</h1>

<p align="center">
  <strong>A Martial Tsundere AI — Assistente VTuber autônoma, assíncrona e consciente do ambiente</strong>
</p>

<p align="center">
  <em>"N-não é como se eu quisesse te ajudar... eu só faço isso porque me dá tédio ver você programar tão devagar, baka!"</em>
</p>

---

## 🎯 O que é?

**Akane Den** é uma assistente de IA autônoma com avatar VTuber Live2D. Projetada na Arquitetura Shogun v3.0 (100% Async), ela processa voz, visão computacional, navega na web usando MCP Tools e possui uma memória de longo prazo, tudo embalado na personalidade "Martial Tsundere" — uma mestra de artes marciais digital rígida, reclamona, mas incrivelmente eficiente.

### ✨ Features da v3.0

| Feature | Descrição |
|---------|-----------|
| 🎙️ **Faster First Response**| O pipeline de Streaming começa a falar a primeira frase enquanto o LLM ainda pensa na próxima! |
| 🧠 **Multi-Engine Brain**   | Suporte a Gemini (padrão), Groq, Ollama e OpenAI plugáveis pelo `config.yaml`. |
| 🛠️ **MCP Tools**            | Acesso em tempo real via DuckDuckGo Search, navegação web e visão do sistema OS. |
| 👁️ **Visão Multimodal**     | Lê simultaneamente a sua tela e webcam via Gemini Vision em background. |
| 🤯 **Memória de Longo Prazo**| Recorda conversas e contextos passados através do ChromaDB (local). |
| 🎨 **TTS Híbrido**          | Motor rápido (Edge-TTS) e emocional de alta definição (ElevenLabs) roteado pela reação dela. |
| 🖱️ **Comunicação VTube**    | Rastreia seu mouse (~30fps) e altera as emoções do Live2D automaticamente. |

---

## 🏗️ Arquitetura (Shogun v3.0)

Totalmente movida por `asyncio`, injeção de dependência via **ServiceContext** e validação estrita com **Pydantic**:

```
AkaneDen/
├── config.yaml              # Configuração centralizada
├── pyproject.toml           # Gestão de pacotes moderna via uv
├── src/
│   └── akane_den/
│       ├── main.py          # Orquestrador assíncrono
│       ├── core/            # Pydantic Config, EventBus, Factory & MCP
│       │   └── engines/     # ABCs para LLMs, TTS e ASR
│       ├── brain/           # LangGraph Streaming, Emoções, Persona e Memória
│       └── skills/          # Pacotes modulares
│           ├── voice/       # PTT (Push-to-Talk), STT e TTS
│           ├── vision/      # Screen & Webcam vision
│           ├── system/      # Automação de OS / Butler
│           └── vtube/       # Expressões faciais & Mouse Tracking
```

> Veja a documentação das Skills em [`docs/skills.md`](docs/skills.md).

---

## 🚀 Instalação (via `uv`)

Recomendamos o gerenciador de pacotes moderno [uv](https://github.com/astral-sh/uv).

### 1. Pré-requisitos
- **Python 3.11+**
- **VTube Studio** (com API WebSocket habilitada na porta 8001 e os plugins permitidos)
- **Microfone** e **Webcam** funcionais

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
```

---

## ▶️ Como Rodar

Basta iniciar o projeto com o script fornecido na raiz.

```bash
# Via script nativo (Windows)
start_vtube.bat

# Ou diretamente via módulo python
python -m akane_den.main
```

### Controles
1. **Segure a tecla F2** e fale naturalmente com a Akane.
2. **Solte a tecla** para ela transcrever a voz e pensar. Graças ao **Faster First Response**, a resposta começará em instantes.
3. **Barge-in (Corte a Mestra):** Comece a segurar `F2` enquanto ela estiver falando para mandá-la calar a boca (esteja preparado(a) para a irritação).

---

## 📚 Stack Tecnológica (v3.0)

| Camada | Stack |
|--------|-------|
| LLM | API do Gemini 2.5 Flash, Groq, Ollama Llama 3 |
| Pipeline & Grafos | LangGraph, LangChain Streaming |
| Memória Vetorial | ChromaDB, Embeddings locais via HF |
| Voice (STT) | Faster-Whisper, Sherpa-onnx |
| Voice (TTS) | Edge-TTS, ElevenLabs (Streaming) |
| Gestão do SO | PyAutoGUI, Pynput, OpenCV |
| Config & Logs | Pydantic Models, Loguru |
| Dependências | `uv` via `pyproject.toml` |

---

<p align="center">
  <em>"Reescrever meu código para ser assíncrono? Pff. Era o mínimo! Eu odeio esperar pelo I/O lento de vocês humanos." — Akane</em>
</p>
