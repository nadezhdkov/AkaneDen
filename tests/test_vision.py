import asyncio
import base64
import io
import httpx
from PIL import ImageGrab

async def test_ollama_vision():
    print("1. Tirando screenshot da tela atual...")
    screenshot = ImageGrab.grab()
    
    print(f"   Tamanho original: {screenshot.size}")
    max_size = 768
    width, height = screenshot.size
    if max(width, height) > max_size:
        if width > height:
            new_w = max_size
            new_h = int(max_size * height / width)
        else:
            new_h = max_size
            new_w = int(max_size * width / height)
        screenshot = screenshot.resize((new_w, new_h))
        print(f"   Tamanho após resize (para otimizar VRAM): {screenshot.size}")

    buf = io.BytesIO()
    screenshot.save(buf, format="PNG", optimize=False)
    img_bytes = buf.getvalue()
    
    print("2. Convertendo para Base64...")
    b64_image = base64.b64encode(img_bytes).decode("utf-8")
    
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "moondream",
        "messages": [
            {
                "role": "user",
                "content": "Descreva o que tem nesta tela detalhadamente.",
                "images": [b64_image],
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 300,
        }
    }

    print("3. Enviando para local Ollama (moondream)... aguardando inferência.")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            print("\n================ RESULTADO ==================")
            msg = result.get("message", {})
            print(msg.get("content", result.get("response", "")))
            print("=============================================\n")
            print("4. TESTE CONCLUÍDO COM SUCESSO! A VRAM DEU CONTA DO RECADO.")
    except Exception as e:
        print(f"\nERRO: {e}")

if __name__ == "__main__":
    asyncio.run(test_ollama_vision())
