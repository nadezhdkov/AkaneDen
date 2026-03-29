"""Smoke test v3.0 COMPLETO — Valida Fases 1 a 6."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
os.environ.setdefault("GOOGLE_API_KEY", "test_key")
os.environ.setdefault("ELEVENLABS_API_KEY", "test_key")

import asyncio

errors = []
passed = 0


def test(name, fn):
    global passed
    try:
        fn()
        passed += 1
        print(f"  [OK] {name}")
    except Exception as e:
        errors.append(f"{name}: {e}")
        print(f"  [FAIL] {name}: {e}")


print("=" * 60)
print("  VALIDACAO SHOGUN v3.0 — COMPLETA (Fases 1-6)")
print("=" * 60)

# ── Fase 1: Infraestrutura ──
print("\n[Fase 1: Infraestrutura]")
test("Package import + version", lambda: (
    __import__("akane_den").__version__ == "3.0.0" or (_ for _ in ()).throw(AssertionError)
))

def test_version():
    import akane_den
    assert akane_den.__version__ == "3.0.0"
test("Package version 3.0.0", test_version)

def test_loguru():
    from akane_den import logger
    assert logger is not None
test("Loguru available", test_loguru)

# ── Fase 2: Config Pydantic ──
print("\n[Fase 2: Config Pydantic]")

def test_config_defaults():
    from akane_den.core.config import AkaneConfig
    c = AkaneConfig()
    assert c.brain.provider == "gemini"
    assert c.brain.active_model == "gemini-2.5-flash"
    assert c.tts.default_engine == "edge"
    assert c.asr.provider == "whisper"
    assert c.memory.backend == "chromadb"
test("Config defaults", test_config_defaults)

def test_config_validation():
    from akane_den.core.config import AkaneConfig
    from pydantic import ValidationError
    try:
        AkaneConfig(brain={"temperature": 5.0})
        assert False
    except ValidationError:
        pass
test("Config validation", test_config_validation)

def test_config_loader():
    from akane_den.core.config_loader import load_config
    c = load_config("config.yaml")
    assert c.ptt_key == "f2"
    assert c.brain.provider == "gemini"
    assert c.brain.gemini_model == "gemini-2.5-flash"
    assert c.mcp.enabled is True
    assert "duckduckgo_search" in c.mcp.tools
    assert c.memory.enabled is True
test("Config loader (v3.0 config.yaml)", test_config_loader)

# ── Fase 2: Engines + Factory ──
print("\n[Fase 2: Engines + Factory]")

def test_engine_imports():
    from akane_den.core.engines import LLMEngine, TTSEngine, ASREngine
    from akane_den.core.engines.llm_engine import GeminiLLMEngine, GroqLLMEngine
    from akane_den.core.engines.tts_engine import EdgeTTSEngine, ElevenLabsTTSEngine
    from akane_den.core.engines.asr_engine import WhisperASREngine, SherpaOnnxASREngine
test("Engine classes importable", test_engine_imports)

def test_factory():
    from akane_den.core.engine_factory import EngineFactory
    p = EngineFactory.list_providers()
    assert "gemini" in p["llm"]
    assert "groq" in p["llm"]
    assert "ollama" in p["llm"]
    assert "openai" in p["llm"]
    assert "edge" in p["tts"]
    assert "whisper" in p["asr"]
    assert "sherpa" in p["asr"]
test("Factory registry (4 LLM, 2 TTS, 2 ASR)", test_factory)

def test_service_context():
    from akane_den.core.service_context import ServiceContext
    assert ServiceContext is not None
test("ServiceContext importable", test_service_context)

# ── Fase 3: EventBus + SkillManager ──
print("\n[Fase 3: Core Components]")

def test_eventbus():
    from akane_den.core.event_bus import EventBus
    bus = EventBus()
    results = []
    bus.on("test", lambda d: results.append(d))
    asyncio.run(bus.emit("test", {"ok": True}))
    assert len(results) == 1
test("EventBus pub/sub", test_eventbus)

def test_skillmanager():
    from akane_den.core.skill_manager import SkillManager
    mgr = SkillManager()
    assert len(mgr) == 0
test("SkillManager instantiation", test_skillmanager)

# ── Fase 4: Brain + Streaming ──
print("\n[Fase 4: Brain + Streaming]")

def test_brain_import():
    from akane_den.brain.graph_state import AkaneBrain
    assert AkaneBrain is not None
test("AkaneBrain importable", test_brain_import)

def test_persona():
    from akane_den.brain.persona import get_akane_system_prompt
    prompt = get_akane_system_prompt(
        vision_context="VS Code aberto",
        barge_in=True,
        webcam_context="Usuário sorrindo",
    )
    assert "VS Code aberto" in prompt
    assert "BARGE-IN" in prompt
    assert "Usuário sorrindo" in prompt
    assert "tsundere" in prompt.lower()
test("Persona dynamic context (vision + webcam + barge-in)", test_persona)

def test_emotion():
    from akane_den.brain.emotion_analyzer import EmotionAnalyzer
    ea = EmotionAnalyzer()
    e, s = ea.analyze("Cuspindo cheitos! Você é um baka incompetente!")
    assert e == "raiva"
    assert s > 0.3
    e2, s2 = ea.analyze("Q-quem você pensa que é, b-baka?!")
    assert e2 == "vergonha"
    e3, s3 = ea.analyze("Olá, como vai?")
    assert e3 == "neutro"
test("EmotionAnalyzer patterns", test_emotion)

# ── Fase 5: MCP Tools ──
print("\n[Fase 5: MCP Tools]")

def test_mcp_registry():
    from akane_den.core.mcp_handler import MCPToolRegistry
    from akane_den.core.config import MCPConfig
    available = MCPToolRegistry.list_available()
    assert "duckduckgo_search" in available
    assert "stagehand" in available
    assert "image_generation" in available
    assert "system" in available
test("MCP registry (all groups)", test_mcp_registry)

def test_mcp_tools_from_config():
    from akane_den.core.mcp_handler import MCPToolRegistry
    from akane_den.core.config import MCPConfig
    config = MCPConfig(
        enabled=True,
        tools=["duckduckgo_search", "stagehand", "image_generation"],
    )
    tools = MCPToolRegistry.get_tools(config)
    tool_names = [t.name for t in tools]
    assert "search_web" in tool_names
    assert "search_news" in tool_names
    assert "browse_webpage" in tool_names
    assert "generate_image" in tool_names
    assert "run_powershell_command" in tool_names  # system always on
    assert "get_system_info" in tool_names
    assert len(tools) >= 9  # system(4) + screenshot(1) + ddg(2) + stagehand(1) + imggen(1)
test("MCP tools from config (9+)", test_mcp_tools_from_config)

# ── Fase 5: Memory ──
print("\n[Fase 5: Memory]")

def test_memory_handlers():
    from akane_den.brain.memory_handler import (
        ChromaMemoryHandler, LettaMemoryHandler, create_memory_handler,
    )
    from akane_den.core.config import MemoryConfig
    handler = create_memory_handler(MemoryConfig(enabled=True, backend="chromadb"))
    assert handler is not None
    assert handler.backend_name == "chromadb"
    none_handler = create_memory_handler(MemoryConfig(enabled=False))
    assert none_handler is None
test("Memory handler factory", test_memory_handlers)

# ── Fase 6: Skills ──
print("\n[Fase 6: Skills]")

def test_skill_imports():
    from akane_den.skills.voice.ptt_skill import PTTSkill
    from akane_den.skills.voice.stt_skill import STTSkill
    from akane_den.skills.voice.tts_skill import TTSSkill
    from akane_den.skills.vision.screen_vision_skill import ScreenVisionSkill
    from akane_den.skills.vtube.expression_skill import ExpressionSkill
    from akane_den.skills.vtube.mouse_tracker_skill import MouseTrackerSkill
test("All skill classes importable", test_skill_imports)

def test_main_import():
    from akane_den.main import main, cli_entry
    assert asyncio.iscoroutinefunction(main)
test("Main orchestrator importable", test_main_import)

# ── Resultado ──
print(f"\n{'=' * 60}")
total = passed + len(errors)
print(f"  RESULTADO: {passed}/{total} testes passaram")
if errors:
    print(f"\n  FALHAS:")
    for err in errors:
        print(f"    - {err}")
else:
    print("  TUDO VERDE! Akane v3.0 validada!")
print(f"{'=' * 60}")

sys.exit(0 if not errors else 1)
