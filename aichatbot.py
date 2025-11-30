# aichatbot.py - AI Chatbot with Microphone Switching
from flask import Flask, render_template_string, request, jsonify
import threading
import time
import subprocess
import sys
import json
import os

# Speech libraries already available from requirements_voice.txt

# ===== CONFIG =====
app = Flask(__name__)

# Microphone control
mic_lock = threading.Lock()
current_mic_source = "raspberry_pi"  # "raspberry_pi" or "phone"

def get_current_mic_source():
    """Get current microphone source"""
    with mic_lock:
        return current_mic_source

def process_voice_command(text):
    """Process voice command and return response"""
    text = text.lower().strip()
    
    # Simple command processing
    if "hello" in text or "hi" in text:
        return "Hello! How can I help you today?"
    elif "time" in text:
        import datetime
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        return f"The current time is {current_time}"
    elif "weather" in text:
        return "I don't have access to weather data, but you can check your weather app."
    elif "microphone" in text or "mic" in text:
        return f"Currently using {current_mic_source} microphone"
    elif "switch" in text and "phone" in text:
        return "Please use the web interface to switch to phone microphone"
    elif "switch" in text and ("pi" in text or "raspberry" in text):
        return "Please use the web interface to switch to Raspberry Pi microphone"
    else:
        return "I heard you say: " + text + ". How can I help you with that?"

# ===== HTML TEMPLATE =====
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>AI Voice Assistant</title>
    <style>
        body { background: #111; color: #eee; font-family: Arial; text-align: center; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        .mic-control { background: #222; border-radius: 10px; padding: 20px; margin: 20px 0; }
        .mic-status { padding: 15px; border-radius: 5px; margin: 15px 0; font-weight: bold; font-size: 18px; }
        .mic-pi { background: #28a745; color: #fff; }
        .mic-phone { background: #1e90ff; color: #fff; }
        .btn { padding: 12px 20px; margin: 10px; font-size: 16px; border-radius: 6px; border: none; cursor: pointer; }
        .btn-primary { background: #1e90ff; color: #fff; }
        .btn-success { background: #28a745; color: #fff; }
        .btn-danger { background: #dc3545; color: #fff; }
        .btn-large { padding: 20px 30px; font-size: 20px; }
        .voice-control { background: #333; border-radius: 10px; padding: 20px; margin: 20px 0; }
        .status { padding: 10px; margin: 10px 0; border-radius: 5px; }
        .status-listening { background: #ffc107; color: #000; }
        .status-processing { background: #17a2b8; color: #fff; }
        .status-ready { background: #28a745; color: #fff; }
        .response-box { background: #444; border-radius: 5px; padding: 15px; margin: 15px 0; text-align: left; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎤 AI Voice Assistant</h1>
        
        <div class="mic-control">
            <h3>Microphone Source</h3>
            <div class="mic-status" id="mic-status">Current: Raspberry Pi Microphone</div>
            <button class="btn btn-success" onclick="switchMic('raspberry_pi')">📱 Use Raspberry Pi Mic</button>
            <button class="btn btn-primary" onclick="switchMic('phone')">📞 Use Phone Mic</button>
        </div>
        
        <div class="voice-control">
            <h3>Voice Control</h3>
            <div class="status status-ready" id="voice-status">Ready to listen</div>
            <button class="btn btn-large btn-primary" id="listen-btn" onclick="startListening()">🎤 Start Listening</button>
            <button class="btn btn-large btn-danger hidden" id="stop-btn" onclick="stopListening()">⏹️ Stop</button>
        </div>
        
        <div class="response-box" id="response-box" style="display: none;">
            <h4>Response:</h4>
            <div id="response-text"></div>
        </div>
    </div>

    <script>
        let isListening = false;
        let currentMicSource = 'raspberry_pi';

        function switchMic(source) {
            fetch('/set_mic_source/' + source, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.status === 'success') {
                        currentMicSource = source;
                        updateMicStatus(source);
                        if (source === 'phone') {
                            requestPhoneMicPermission();
                        }
                    }
                })
                .catch(e => console.error('Error switching microphone:', e));
        }

        function updateMicStatus(source) {
            const statusEl = document.getElementById('mic-status');
            if (source === 'phone') {
                statusEl.textContent = 'Current: Phone Microphone';
                statusEl.className = 'mic-status mic-phone';
            } else {
                statusEl.textContent = 'Current: Raspberry Pi Microphone';
                statusEl.className = 'mic-status mic-pi';
            }
        }

        function requestPhoneMicPermission() {
            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                navigator.mediaDevices.getUserMedia({ audio: true })
                    .then(stream => {
                        console.log('Phone microphone access granted');
                        // Keep the stream active for the session
                        window.phoneAudioStream = stream;
                    })
                    .catch(err => {
                        alert('Microphone permission denied. Please allow microphone access and try again.');
                        console.error('Microphone permission error:', err);
                        // Switch back to Raspberry Pi mic
                        switchMic('raspberry_pi');
                    });
            } else {
                alert('Your browser does not support microphone access.');
                switchMic('raspberry_pi');
            }
        }

        function startListening() {
            if (isListening) return;
            
            isListening = true;
            document.getElementById('listen-btn').classList.add('hidden');
            document.getElementById('stop-btn').classList.remove('hidden');
            document.getElementById('voice-status').textContent = 'Listening...';
            document.getElementById('voice-status').className = 'status status-listening';
            
            fetch('/listen', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    document.getElementById('voice-status').textContent = 'Processing...';
                    document.getElementById('voice-status').className = 'status status-processing';
                    
                    if (data.text && !data.text.includes('Error') && !data.text.includes('Timeout')) {
                        return fetch('/process_command', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ text: data.text })
                        });
                    } else {
                        throw new Error(data.text || 'No speech detected');
                    }
                })
                .then(r => r.json())
                .then(data => {
                    showResponse(data.response);
                    document.getElementById('voice-status').textContent = 'Ready to listen';
                    document.getElementById('voice-status').className = 'status status-ready';
                })
                .catch(e => {
                    showResponse('Error: ' + e.message);
                    document.getElementById('voice-status').textContent = 'Ready to listen';
                    document.getElementById('voice-status').className = 'status status-ready';
                })
                .finally(() => {
                    stopListening();
                });
        }

        function stopListening() {
            isListening = false;
            document.getElementById('listen-btn').classList.remove('hidden');
            document.getElementById('stop-btn').classList.add('hidden');
        }

        function showResponse(text) {
            document.getElementById('response-text').textContent = text;
            document.getElementById('response-box').style.display = 'block';
        }

        // Initialize microphone status on page load
        fetch('/get_mic_source')
            .then(r => r.json())
            .then(data => {
                currentMicSource = data.source;
                updateMicStatus(data.source);
            });
    </script>
</body>
</html>
"""

# ===== FLASK ROUTES =====
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/set_mic_source/<source>', methods=['POST'])
def set_mic_source(source):
    global current_mic_source
    with mic_lock:
        if source in ['raspberry_pi', 'phone']:
            current_mic_source = source
            print(f"[MIC] Switched to {source} microphone")
            return jsonify({"status": "success", "source": source})
        else:
            return jsonify({"status": "error", "message": "Invalid microphone source"}), 400

@app.route('/get_mic_source')
def get_mic_source():
    with mic_lock:
        return jsonify({"source": current_mic_source})

@app.route('/listen', methods=['POST'])
def listen():
    """Placeholder - integrate with existing speech system"""
    return jsonify({"text": "Integrate with existing speech recognition system", "mic_source": current_mic_source})

@app.route('/process_command', methods=['POST'])
def process_command():
    """Process voice command and return response"""
    data = request.get_json()
    text = data.get('text', '')
    response = process_voice_command(text)
    return jsonify({"response": response})

@app.route('/speak', methods=['POST'])
def speak():
    """Placeholder - integrate with existing TTS system"""
    return jsonify({"status": "handled_by_existing_system", "mic_source": current_mic_source})

if __name__ == '__main__':
    print("[CHATBOT] Starting AI Voice Assistant...")
    print("[CHATBOT] Flask server starting on http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)