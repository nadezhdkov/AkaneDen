# Guia de Skills & MCP — AkaneDen v3.0

O coração do AkaneDen são suas **Skills**. Elas rodam de forma não-bloqueante via módulo `asyncio` e adquirem ferramentas (como ASR ou TTS) diretamente do **Container de DI (`ServiceContext`)**.

---

## 🎙️ Voice Pipeline (`src/akane_den/skills/voice/`)

### 1. PTTSkill — Push-to-Talk
**Cooldown:** 0.3s – 0.5s
Captura eventos do microfone em uma thread paralela não bloqueante.
- Escuta `F2` em background. Gravando os streams gerados pela biblioteca `sounddevice`.
- Se a Akane estiver falando na hora (`barge-in`), corta o áudio atual dela com interrupção sutil.
- Libera o evento `user_speech_ready` enviando o pacote via `EventBus`.

### 2. STTSkill — Transcrição (Whisper / Sherpa)
- Recebe o buffer, checa que o áudio > 0.4s.
- Injeta no `asr_engine` habilitado no `ServiceContext`.
- Entrega o texto limpo via `user_text_ready` direto pro `AkaneBrain` pensar.

### 3. TTSSkill — Motor Duplo & Streaming ("Faster First Response")
**A Magia da Latência Zero.**
Esse módulo introduz a função `speak_streaming`:
1. Enquanto o gerador `LangGraph` da Akane cospe *chunks*, o `ServiceContext` corta a string ao final da primeira frase (`.` ou `?`).
2. O `TTSSkill` captura e sintetiza a fala local *imediatamente*, dando play na stream. O usuário inicia a ouvir o áudio ~2 segundos pós `F2`.
3. Sentenças subsequentes entram no `Queue` para garantir playback contínuo.
4. **Híbrido Emotion-Aware**: `ServiceContext` examina o detector de expressões. Se a emoção passar de `0.7` (`Raiva` ou `Vergonha`), ele troca o motor default nativo para instanciar a API da `ElevenLabs`.

---

## 🧠 Brain & Tool Calling (Model Context Protocol)
Antigamente hardcoded em ButlerSkill, agora externalizado no `MCPToolRegistry`.

**Módulo:** `src/akane_den/core/mcp_handler.py`

| Grupo MCP | Tool | O que faz |
|-----------|------|------------|
| **System** | `run_powershell_command` | Roda shell no host por trás dos panos. |
| **System** | `open_program` / `open_url` | Controla navegador e processos do OS. |
| **System** | `take_screenshot` | Mapeado no pyAutoGUI para salvar a captura e mandar pro Gemini. |
| **Search** | `search_web` / `search_news` | Dispara instâncias *DuckDuckGo* para a IA trazer atualidades (s/ API key). |
| **Web**    | `browse_webpage` | Agent Crawler pra ler documentação (Stagehand nativo). |
| **Images** | `generate_image` | Usa o Gemini / SD para criar thumbnails / memes sob demanda. |

---

## 👁️ Vision Skill (`src/akane_den/skills/vision/`)

### ScreenVisionSkill — Consciência Constante
- Um `Task` contínuo que roda a cada XX segundos ditados pelo `config.auto_capture_interval`.
- Redimensiona um Print do display (ou do OpenCV / Webcam) pra não entupir a janela de tokens.
- O Node multimodal escreve uma sintaxe resumida: `"O usuário está debugando Python"`. 
- Isso entra no System Prompt. Se a Akane reclamar, ela fará refs à tela (ex: *"Dá pra fechar o Youtube e voltar pro VSCode?!"*).

---

## 🎭 Live2D VTube (`src/akane_den/skills/vtube/`)

### ExpressionSkill
Responsável pela mimetização de emoções detectadas pela IA no Output Texto via LangChain.
1. Analisa a saída da IA (`EmotionAnalyzer` detecta `Baka` -> Atribui `Raiva`).
2. Mapeia no YAML (ex: `Raiva` -> hotkey `"阴险启用"`).
3. Sinaliza via WebSockets no VTube Studio p/ o Live2D transicionar animação instantânea.

### MouseTrackerSkill
- Um Worker minucioso a 30fps.
- Puxa as coordenadas X/Y do mouse via `pyautogui`, normaliza `-30` a `+30`.
- Usa filtro LPF/exponencial (X = alvo_X * 0.3) pra garantir um tracking dos "olhos" bem natural no VTube Studio sem os soluços causados por API requests.

---

## Criando Novas Skills!
Quer colocar a Akane p/ enviar mensagens no Discord? 
Herde a base e implemente os handlers *Async*:

```python
from akane_den.core.base_skill import BaseSkill, SkillContext

class DiscordSkill(BaseSkill):
    def __init__(self, context: SkillContext, service_context):
        super().__init__(context, service_context)
    
    async def setup(self):
        # Conecta no Discord via service_context
        self._bus.on("user_text_ready", self._handler)
    
    async def execute(self, **kwargs) -> dict: ...
```
