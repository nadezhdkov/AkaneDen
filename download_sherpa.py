import os
import urllib.request
import tarfile
import shutil

target_dir = "models"
if os.path.exists(target_dir):
    shutil.rmtree(target_dir)

os.makedirs(target_dir, exist_ok=True)
# Link para modelo SenseVoiceSmall INT8 (Recomendado para AkaneDen)
url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17-int8.tar.bz2"
fname = "sensevoice_int8.tar.bz2"

try:
    print(f"Baixando {url} para {fname}...")
    # User agent para evitar 403 em alguns servidores
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-agent', 'Mozilla/5.0')]
    urllib.request.install_opener(opener)
    
    urllib.request.urlretrieve(url, fname)
    print("Baixado com sucesso. Extraindo...")
    with tarfile.open(fname, "r:bz2") as tar:
        tar.extractall(target_dir)
    print("Extraído com sucesso para a pasta models.")
finally:
    if os.path.exists(fname):
        os.remove(fname)
