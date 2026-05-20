import os
import requests
import urllib.parse
from datetime import datetime

RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

def text_to_speech(text: str, voice_gender: str = "femminile", language: str = "it") -> str:
    """
    Genera audio usando Google TTS - VOCE FEMMINILE, funziona sempre
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    audio_file = os.path.join(RECORDINGS_DIR, f"voice_{timestamp}.mp3")
    
    # Mappa lingue per Google TTS
    lang_map = {"it": "it", "en": "en", "es": "es", "fr": "fr"}
    lang_code = lang_map.get(language, "it")
    
    # Codifica il testo per l'URL
    text_encoded = urllib.parse.quote(text)
    
    # Google TTS - voce femminile naturale
    url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl={lang_code}&client=tw-ob"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            with open(audio_file, 'wb') as f:
                f.write(response.content)
            print(f"✅ Audio generato (Google TTS) per: {text[:50]}...")
            return audio_file
        else:
            raise Exception(f"Google TTS error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Errore: {e}")
        raise Exception(f"Impossibile generare l'audio: {e}")

def get_available_voices(language: str = "it"):
    """Restituisce solo voce femminile (funziona sempre)"""
    return [
        {"id": "femminile", "name": "👩 Voce Femminile (Google TTS - Chiara e naturale)"}
    ]