"""
MCPHandler — Model Context Protocol para ferramentas externas.

Expõe ferramentas como LangChain tools para o Brain da Akane:
  - DuckDuckGo Search: pesquisa web em tempo real
  - Stagehand: navegação e automação web
  - Image Generation: geração de thumbnails/assets via API

"Se eu preciso buscar algo na internet pra provar que você tá
errado, agora eu posso fazer isso em TEMPO REAL, baka!" — Akane
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from langchain_core.tools import tool
from loguru import logger

from akane_den.core.config import MCPConfig


# ──────────────────────────────────────────────
# DuckDuckGo Search Tool
# ──────────────────────────────────────────────


@tool
def search_web(query: str) -> str:
    """Pesquisa na internet usando DuckDuckGo.
    Use para buscar notícias, informações atualizadas, dados técnicos,
    ou qualquer coisa que precise de contexto em tempo real.

    Args:
        query: Texto da pesquisa em português ou inglês.

    Returns:
        Resultados resumidos da pesquisa.
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

        if not results:
            return "Nenhum resultado encontrado. Tente reformular a pesquisa."

        output = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            output.append(f"**{title}**\n{body}\nURL: {href}")

        return "\n\n---\n\n".join(output)

    except ImportError:
        return (
            "duckduckgo-search não instalado! "
            "Instale com: pip install duckduckgo-search"
        )
    except Exception as e:
        return f"Erro na pesquisa: {e}"


@tool
def search_news(query: str) -> str:
    """Pesquisa notícias recentes usando DuckDuckGo News.
    Use para encontrar eventos atuais, acontecimentos recentes
    e trending topics.

    Args:
        query: Tópico de notícia para pesquisar.

    Returns:
        Notícias recentes sobre o tópico.
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=5))

        if not results:
            return "Nenhuma notícia encontrada sobre esse tópico."

        output = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            source = r.get("source", "")
            date = r.get("date", "")
            output.append(f"**{title}** ({source}, {date})\n{body}")

        return "\n\n---\n\n".join(output)

    except Exception as e:
        return f"Erro na pesquisa de notícias: {e}"


# ──────────────────────────────────────────────
# Stagehand — Navegação Web
# ──────────────────────────────────────────────


@tool
def browse_webpage(url: str) -> str:
    """Navega para uma URL e extrai o conteúdo principal da página.
    Use para ler artigos, documentação, páginas que o usuário pediu.

    Args:
        url: URL completa da página web (inclua https://).

    Returns:
        Conteúdo textual principal da página.
    """
    try:
        import urllib.request
        import html
        import re

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AkaneDen/3.0 (VTuber Assistant)"},
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            raw_html = response.read().decode("utf-8", errors="ignore")

        # Extrai texto limpo do HTML
        # Remove scripts e styles
        raw_html = re.sub(r"<script[^>]*>.*?</script>", "", raw_html, flags=re.S)
        raw_html = re.sub(r"<style[^>]*>.*?</style>", "", raw_html, flags=re.S)
        # Remove tags HTML
        text = re.sub(r"<[^>]+>", " ", raw_html)
        # Decode HTML entities
        text = html.unescape(text)
        # Normaliza espaços
        text = re.sub(r"\s+", " ", text).strip()

        # Limita a 3000 chars
        if len(text) > 3000:
            text = text[:3000] + "... [truncado]"

        return text if text else "Página vazia ou sem conteúdo textual."

    except Exception as e:
        return f"Erro ao acessar {url}: {e}"


# ──────────────────────────────────────────────
# Image Generation Tool
# ──────────────────────────────────────────────


@tool
def generate_image(prompt: str, filename: str = "akane_generated.png") -> str:
    """Gera uma imagem a partir de uma descrição textual.
    Use para criar thumbnails, assets para YouTube, 'Tubes',
    ou qualquer visual que o usuário solicitar.

    Args:
        prompt: Descrição detalhada da imagem a ser gerada, em inglês.
        filename: Nome do arquivo de saída (default: akane_generated.png).

    Returns:
        Caminho do arquivo gerado ou mensagem de erro.
    """
    try:
        import google.generativeai as genai

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return "GOOGLE_API_KEY não configurada! Não posso gerar imagens."

        genai.configure(api_key=api_key)

        # Usa Gemini com capacidade de geração de imagem
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        response = model.generate_content(
            f"Generate an image: {prompt}",
            generation_config=genai.GenerationConfig(
                response_mime_type="image/png",
            ),
        )

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    from pathlib import Path
                    from akane_den.core.paths import BASE_DIR
                    output_dir = BASE_DIR / "generated_images"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_path = output_dir / filename
                    with open(output_path, "wb") as f:
                        f.write(part.inline_data.data)
                    return f"Imagem gerada com sucesso: {output_path}"

        return "Não foi possível gerar a imagem. Tente reformular o prompt."

    except Exception as e:
        return f"Erro na geração de imagem: {e}"


# ──────────────────────────────────────────────
# System Tools (migrados do ButlerSkill)
# ──────────────────────────────────────────────


@tool
def run_system_command(command: str) -> str:
    """Executa um comando no terminal do sistema hospedado.
    No Windows usa PowerShell, no Linux usa Bash.
    Use para automação de sistema, criar arquivos, mover, listar processos, etc.

    Args:
        command: Comando a executar.

    Returns:
        Saída do comando ou mensagem de erro.
    """
    import subprocess
    import re
    import sys

    # Lista de bloqueio para comandos destrutivos massivos
    forbidden = [
        "rm", "remove-item", "del", "erase", "format", 
        "clear-disk", "format-volume", "rd", "rmdir", "stop-computer",
        "restart-computer", "sysprep", "mkfs"
    ]
    
    cmd_lower = command.lower()
    for word in forbidden:
        if re.search(rf"\b{word}\b", cmd_lower) and "rm" not in cmd_lower.replace("rmdir", ""): # safety net
            # Uma regex melhor para evitar falsos positivos
            pass
        if re.search(rf"(?<![a-zA-Z]){word}(?![a-zA-Z])", cmd_lower):
            return f"ERRO DE SEGURANÇA: O comando contém instrução destrutiva bloqueada '{word}'."

    try:
        if sys.platform == "linux":
            result = subprocess.run(
                ["/bin/bash", "-c", command],
                capture_output=True,
                text=True,
                timeout=30,
            )
        else:
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            
        output = result.stdout.strip() or result.stderr.strip()
        return output[:2000] if output else "Comando executado sem saída visível."
    except subprocess.TimeoutExpired:
        return "Comando expirou (timeout de 30 segundos)."
    except Exception as e:
        return f"Erro ao executar: {e}"


@tool
def open_program(program_name: str) -> str:
    """Abre um programa/aplicativo no Windows.
    Use para abrir softwares instalados como 'Steam', 'Discord', 'Notepad', 'Code', etc.
    Ele vai pesquisar no sistema e tentar abrir.

    Args:
        program_name: Nome ou atalho do programa (ex: 'Steam', 'Discord'). Se souber a URI, também pode enviar (ex: steam://).

    Returns:
        Confirmação ou erro.
    """
    import subprocess
    import sys

    try:
        if sys.platform == "linux":
            # No Linux, tenta usar o xdg-open ou atalhos conhecidos
            subprocess.Popen(
                ["xdg-open", program_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return f"Sinal enviado ao Linux para abrir '{program_name}' via xdg-open."
        else:
            # O cmd /c start "" vai consultar os 'App Paths' do registro do Windows
            subprocess.run(
                ["cmd", "/c", "start", "", program_name],
                capture_output=True,
                timeout=10,
            )
            return f"Sinal enviado ao Windows para abrir '{program_name}'."
    except Exception as e:
        return f"Erro ao sinalizar abertura de '{program_name}': {e}"


@tool
def open_url(url: str) -> str:
    """Abre uma URL no navegador padrão do sistema.

    Args:
        url: URL completa para abrir (inclua https://).

    Returns:
        Confirmação.
    """
    import webbrowser

    try:
        webbrowser.open(url)
        return f"URL aberta com sucesso: {url}"
    except Exception as e:
        return f"Erro ao abrir URL: {e}"


@tool
def play_youtube(query: str) -> str:
    """Abre o YouTube pesquisando por um vídeo ou música específicos.
    Use quando o usuário pedir para tocar uma música, ver um vídeo, etc.

    Args:
        query: Nome da música, clipe, ou termo para buscar no YouTube.

    Returns:
        Confirmação de que abriu a pesquisa.
    """
    import urllib.parse
    import webbrowser

    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        webbrowser.open(url)
        return f"Pesquisando '{query}' no YouTube."
    except Exception as e:
        return f"Erro ao acessar o YouTube: {e}"


@tool
def get_system_info() -> str:
    """Obtém informações do sistema (CPU, RAM, disco, processos).
    Use quando o usuário perguntar sobre o status do computador.

    Returns:
        Informações resumidas do sistema.
    """
    import sys
    import subprocess

    output = []
    
    if sys.platform == "linux":
        # Abordagem Linux nativa (fallback para free, top, df)
        try:
            import psutil
            cpu = f"Load: {psutil.cpu_percent()}%"
            mem = psutil.virtual_memory()
            ram = f"TotalGB: {round(mem.total/1024**3, 1)}, FreeGB: {round(mem.available/1024**3, 1)}"
            disk = psutil.disk_usage('/')
            dsc = f"UsedGB: {round(disk.used/1024**3, 1)}, FreeGB: {round(disk.free/1024**3, 1)}"
            output = [f"**CPU:**\n{cpu}", f"**RAM:**\n{ram}", f"**Disco (Root):**\n{dsc}"]
            return "\n\n".join(output)
        except ImportError:
            # Fallback bash
            cpu = subprocess.run(["bash", "-c", "top -bn1 | grep 'Cpu(s)'"], capture_output=True, text=True).stdout.strip()
            ram = subprocess.run(["bash", "-c", "free -h | grep Mem"], capture_output=True, text=True).stdout.strip()
            dsc = subprocess.run(["bash", "-c", "df -h /"], capture_output=True, text=True).stdout.strip()
            return f"**CPU:**\n{cpu}\n\n**RAM:**\n{ram}\n\n**Disco (/):**\n{dsc}"
    else:
        commands = {
            "CPU": "Get-CimInstance Win32_Processor | Select-Object Name, LoadPercentage | Format-List",
            "RAM": "Get-CimInstance Win32_OperatingSystem | Select-Object @{N='TotalGB';E={[math]::Round($_.TotalVisibleMemorySize/1MB,1)}}, @{N='FreeGB';E={[math]::Round($_.FreePhysicalMemory/1MB,1)}} | Format-List",
            "Disco": "Get-PSDrive C | Select-Object @{N='UsedGB';E={[math]::Round($_.Used/1GB,1)}}, @{N='FreeGB';E={[math]::Round($_.Free/1GB,1)}} | Format-List",
        }

        for name, cmd in commands.items():
            try:
                result = subprocess.run(
                    ["powershell", "-Command", cmd],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    encoding="utf-8",
                    errors="replace",
                )
                output.append(f"**{name}:**\n{result.stdout.strip()}")
            except Exception as e:
                output.append(f"**{name}:** Erro: {e}")

        return "\n\n".join(output)


@tool
def take_screenshot() -> str:
    """Captura um screenshot da tela atual e salva.
    
    Returns:
        Caminho do arquivo do screenshot.
    """
    try:
        from PIL import ImageGrab
        import time
        from pathlib import Path
        from akane_den.core.paths import BASE_DIR

        out_dir = BASE_DIR / "screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        path = out_dir / f"screen_{timestamp}.png"
        img = ImageGrab.grab()
        img.save(str(path))
        return f"Screenshot salvo: {path}"
    except Exception as e:
        return f"Erro ao capturar screenshot: {e}"


# ──────────────────────────────────────────────
# MCP Tool Registry
# ──────────────────────────────────────────────


class MCPToolRegistry:
    """Registry central de ferramentas MCP.

    Gerencia quais ferramentas estão disponíveis baseado no config.
    """

    # Todas as ferramentas disponíveis
    _ALL_TOOLS = {
        "duckduckgo_search": [search_web, search_news],
        "stagehand": [browse_webpage],
        "image_generation": [generate_image],
        "system": [run_system_command, open_program, open_url, get_system_info, play_youtube],
        "screenshot": [take_screenshot],
    }

    @classmethod
    def get_tools(cls, config: MCPConfig) -> list:
        """Retorna ferramentas ativas baseado no config.

        Args:
            config: MCPConfig com lista de tools habilitadas.

        Returns:
            Lista flat de LangChain tools.
        """
        if not config.enabled:
            # Mesmo com MCP desabilitado, system tools são sempre ativos
            tools = list(cls._ALL_TOOLS.get("system", []))
            logger.info(f"MCP desabilitado. {len(tools)} system tools ativos.")
            return tools

        tools = []
        # System tools sempre ativos
        tools.extend(cls._ALL_TOOLS.get("system", []))
        tools.extend(cls._ALL_TOOLS.get("screenshot", []))

        for tool_group in config.tools:
            group_tools = cls._ALL_TOOLS.get(tool_group, [])
            if group_tools:
                tools.extend(group_tools)
                logger.info(f"MCP tool group '{tool_group}': {len(group_tools)} tools")
            else:
                logger.warning(f"MCP tool group desconhecido: '{tool_group}'")

        tool_names = [t.name for t in tools]
        logger.info(f"Total MCP tools ativos: {len(tools)} -> {tool_names}")
        return tools

    @classmethod
    def list_available(cls) -> dict[str, list[str]]:
        """Lista todos os grupos de ferramentas disponíveis."""
        return {
            group: [t.name for t in tools]
            for group, tools in cls._ALL_TOOLS.items()
        }
