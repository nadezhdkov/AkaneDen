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

## 🚀 Criando Novas Skills (Tutorial Rápido)

Graças ao padrão `ServiceContext`, ensinar novas habilidades à Akane é limpo e modularizado. Uma "Skill" precisa apenas herdar de `BaseSkill` e plugar-se aos fluxos de conversão adequados (EventBus ou chamadas diretas).

### 1. O Ciclo de Vida da Skill
Toda Skill possui três fases primordiais garantidas pelo `SkillManager` durante o ciclo global de *boot* e *shutdown*:
- `setup()`: Roda uma vez. Configura listeners, APIs e valida tokens asincronamente.
- `execute()`: A lógica executiva da classe caso a ative manualmente pelo código ou via uma Tool Calls.
- `teardown()`: Clean up e desconexões seguras no desligamento natural do sistema.

### 2. Exemplo: Construindo uma DiscordSkill
Queremos que a Akane reencaminhe sua fala ou mande um recadinho pro Discord toda vez que gerar algum output na engine de NLP.

Crie `src/akane_den/skills/social/discord_skill.py`:

```python
from loguru import logger
from akane_den.core.base_skill import BaseSkill, SkillContext

class DiscordSkill(BaseSkill):
    def __init__(self, service_context):
        # Todo submódulo requer um SkillContext básico (nome, cooldowns em segundos)
        ctx = SkillContext(skill_name="discord", min_cooldown=1.0, max_cooldown=5.0)
        
        # O Super recebe este contexto da skill + e o service_context (que possui as configs e Motores!)
        super().__init__(ctx, service_context)
    
    async def setup(self) -> None:
        """Phase 1: Chamado quando a Akane liga."""
        # Se você ler o YAML, você o puxa via self.service_context.config...
        logger.info("DiscordSkill setup iniciado...")

        # A magia: Plugar-se aos eventos globais do sistema via self.event_bus
        self.event_bus.on("akane_response_ready", self._handler_discord_push)
        logger.success("Ouvinte do Discord registrado.")

    async def _handler_discord_push(self, data: dict) -> None:
        """Callback lançado assincronamente quando a Akane terminar de pensar."""
        texto = data.get("text", "")
        # Lógica assíncrona pra HTTP Request pro Discord aqui
        logger.debug(f"A Akane enviou para o Discord: {texto[:20]}...")
    
    async def execute(self, **kwargs) -> dict:
        """Phase 2: Execução manual da Skill (Ex: Invocado em main() iterativamente)."""
        mensagem = kwargs.get("mensagem", "Olá Discord.")
        logger.info(f"Executando postagem forçada: {mensagem}")
        return {"status": "enviado", "msg": mensagem}
    
    async def teardown(self) -> None:
        """Phase 3: Chamado quando a Akane é desligada."""
        logger.info("DiscordSkill desativado com segurança.")
```

### 3. Registro no Skill Manager
Para o motor principal da Assistente dar conta da Skill nova, você a inicializa no orquestrador raiz (ex: em `src/akane_den/main.py`):

```python
from akane_den.skills.social.discord_skill import DiscordSkill

async def main():
    service = await ServiceContext.create(config)
    manager = SkillManager(service)
    
    # Registrando
    discord_skill = DiscordSkill(service)
    manager.register_skill(discord_skill)

    # Ao chamar setup_all(), ela disparará o self.setup() do DiscordSkill no background
    await manager.setup_all()
```

Com apenas essa estrutura você consegue integrar a Akane para controlar playlists do Spotify, tuitar coisas e até orquestrar lâmpadas IoT pela casa (se o Mestre permitir).
