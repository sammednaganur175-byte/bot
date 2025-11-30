import os
import time
import serial
import threading

import speech_recognition as sr
from google import genai
from google.genai import types
from gtts import gTTS
from pygame import mixer
import cv2
from flask import Flask, render_template_string, request, jsonify

# ESP8266 Serial Configuration
BAUD_RATE = 115200

# Try to connect to serial, checking multiple USB ports
ser = None
for port in ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2", "/dev/ttyACM0", "/dev/ttyACM1"]:
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=1)
        print(f"[SERIAL] Connected to {port}")
        break
    except:
        continue

if ser is None:
    print("[SERIAL] No USB device found. Running in simulation mode.")

# Initialize Clients and Mixer
try:
    client = genai.Client()
    # Initialize mixer with specific settings to avoid ALSA warnings
    os.environ['SDL_AUDIODRIVER'] = 'pulse'
    mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
    mixer.init()
except Exception as e:
    print(f"Initialization Error: {e}")
    raise SystemExit

r = sr.Recognizer()
mic = sr.Microphone()

# Flask app for web control
app = Flask(__name__)

# Microphone control
mic_lock = threading.Lock()
current_mic_source = "raspberry_pi"  # "raspberry_pi" or "phone"

# ===== Motor Functions via ESP8266 Serial ===== #
def send_command(cmd):
    if ser is None:
        print(f"[SERIAL] Simulated: {cmd}")
        return True
    try:
        ser.write(f"{cmd}\n".encode())
        print(f"[SERIAL] Sent: {cmd}")
        return True
    except Exception as e:
        print(f"[ERROR] Serial Error: {e}")
        return False

def stop():
    print("[COMMAND] STOP")
    send_command("STOP")

def forward():
    print("[COMMAND] FORWARD")
    send_command("FORWARD")

def backward():
    print("[COMMAND] BACKWARD")
    send_command("BACKWARD")

def left():
    print("[COMMAND] LEFT")
    send_command("LEFT")

def right():
    print("[COMMAND] RIGHT")
    send_command("RIGHT")

def rotate_in_place(step_time=0.4):
    print("[EXPLORE] Rotating in place...")
    send_command("RIGHT")
    time.sleep(step_time)
    stop()


# ===== Camera / Explore Helpers ===== #
def capture_image(index: int):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera Error: cannot open camera")
        return None

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("Camera Error: cannot read frame")
        return None

    filename = f"explore_{index}.jpg"
    cv2.imwrite(filename, frame)
    print(f"Captured image: {filename}")
    return filename


def explore_mode():
    speak_text("Starting explore mode. Please wait while I scan the surroundings.")
    stop()

    image_paths = []

    for i in range(8):
        rotate_in_place(step_time=0.4)
        time.sleep(2.0)
        img_path = capture_image(i)
        if img_path:
            image_paths.append(img_path)

    if not image_paths:
        speak_text("I could not capture any images. Please check the camera.")
        return

    parts = []
    for path in image_paths:
        try:
            with open(path, "rb") as f:
                image_bytes = f.read()
            parts.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg",
                )
            )
        except Exception as e:
            print(f"Error reading image {path}: {e}")

    parts.append(
        "These are 8 images taken while a small robot rotated in place."
        " Describe, in simple language, what is around the robot: "
        "things like walls, doors, open spaces, obstacles, people, or furniture."
        " Give a short summary of the surroundings."
    )

    try:
        print("Sending images to Gemini for analysis...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=parts,
        )
        description = response.text
        print("Gemini explore description:", description)
        speak_text(description)
    except Exception as e:
        print(f"Gemini explore error: {e}")
        speak_text("There was an error analyzing the images.")

    for path in image_paths:
        try:
            os.remove(path)
        except OSError:
            pass

    stop()


# ===== Text-to-Speech ===== #
def speak_text(text):
    try:
        tts = gTTS(text=text, lang='en')
        tts.save("response.mp3")

        mixer.music.load("response.mp3")
        mixer.music.play()

        while mixer.music.get_busy():
            time.sleep(0.1)

        os.remove("response.mp3")

    except Exception as e:
        print(f"TTS Error: {e}")


# ===== Command Matching Helpers ===== #
def matches(cmd: str, phrases):
    return any(p in cmd for p in phrases)


# ===== Main Assistant Loop ===== #
def run_assistant():
    print("Assistant is ready. Speak now...")

    with mic as source:
        r.adjust_for_ambient_noise(source)
        print("Listening...")

        try:
            audio = r.listen(source)
            command = r.recognize_google(audio)
            print(f"You said: {command}")

            cmd = command.lower().strip()

            # Exit command
            if "exit" in cmd or "stop assistant" in cmd or "shutdown" in cmd:
                speak_text("Goodbye!")
                stop()
                return False

            # ===== Explore Mode ===== #
            if matches(cmd, ["explore", "explore mode", "scan area",
                             "scan surroundings", "what is around", "what's around"]):
                explore_mode()
                return True

            # ===== Movement Commands with Flexible Phrases ===== #

            # Forward
            if matches(cmd, [
                "move forward", "go forward", "forward", "come forward",
                "go straight", "move straight", "drive forward"
            ]):
                speak_text("Moving forward.")
                forward()
                return True

            # Backward
            if matches(cmd, [
                "move back", "go back", "move backward", "go backward",
                "reverse", "back up", "go in reverse"
            ]):
                speak_text("Moving backward.")
                backward()
                return True

            # Left
            if matches(cmd, [
                "move left", "go left", "turn left", "take left",
                "rotate left"
            ]):
                speak_text("Turning left.")
                left()
                return True

            # Right
            if matches(cmd, [
                "move right", "go right", "turn right", "take right",
                "rotate right"
            ]):
                speak_text("Turning right.")
                right()
                return True

            # Optional: stop car without exiting assistant
            if matches(cmd, ["stop","stop car", "stop moving", "halt", "freeze" , "brake" , "pause" ,"wait"]):
                speak_text("Stopping the car.")
                stop()
                return True

            # ===== Gemini AI Response for General Questions ===== #
            print("Thinking with Gemini...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents={"role : you aren an rc car built using esp8266 and L298N motor driver and 4 wheels and rc motors which uses google gemini api . keep the reply short and simple and avoid using * , and if some one asks you whats your name then reply chitti , you are built by satish and sammed"+command}
            )
            ai_reply = response.text

            print(f"Gemini replied: {ai_reply}")
            speak_text(ai_reply)

        except sr.UnknownValueError:
            speak_text("Sorry, I did not catch that.")
        except sr.RequestError:
            speak_text("Speech recognition error. Please check your internet connection.")
        except Exception as e:
            print(f"Unexpected error: {e}")
            speak_text("An internal error occurred.")

    return True


# ===== Flask Web Interface ===== #
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
    </div>
    <script>
        function switchMic(source) {
            if (source === 'phone') {
                navigator.mediaDevices.getUserMedia({ audio: true })
                    .then(stream => {
                        fetch('/set_mic_source/phone', { method: 'POST' })
                            .then(r => r.json())
                            .then(data => {
                                document.getElementById('mic-status').textContent = 'Current: Phone Microphone';
                                document.getElementById('mic-status').className = 'mic-status mic-phone';
                            });
                    })
                    .catch(err => {
                        alert('Microphone permission denied');
                    });
            } else {
                fetch('/set_mic_source/raspberry_pi', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        document.getElementById('mic-status').textContent = 'Current: Raspberry Pi Microphone';
                        document.getElementById('mic-status').className = 'mic-status mic-pi';
                    });
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/set_mic_source/<source>', methods=['POST'])
def set_mic_source(source):
    global current_mic_source, mic
    with mic_lock:
        if source in ['raspberry_pi', 'phone']:
            current_mic_source = source
            print(f"[MIC] Switched to {source} microphone")
            # Reinitialize microphone with new source
            try:
                if source == "phone":
                    mic = sr.Microphone()  # Default device (phone when connected)
                else:
                    # Try to find Raspberry Pi microphone
                    mic_list = sr.Microphone.list_microphone_names()
                    for i, name in enumerate(mic_list):
                        if any(keyword in name.lower() for keyword in ['usb', 'card']):
                            mic = sr.Microphone(device_index=i)
                            break
                    else:
                        mic = sr.Microphone()
            except Exception as e:
                print(f"[MIC] Error switching microphone: {e}")
            return jsonify({"status": "success", "source": source})
        else:
            return jsonify({"status": "error", "message": "Invalid source"}), 400

@app.route('/get_mic_source')
def get_mic_source():
    with mic_lock:
        return jsonify({"source": current_mic_source})

def run_flask():
    print("[FLASK] Starting web server on http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)

# ===== Main Entry ===== #
if __name__ == "__main__":
    # Start Flask server in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    print("[INFO] Web interface: http://localhost:5001")
    print(f"[INFO] Current microphone: {current_mic_source}")
    
    try:
        speak_text("Hello, I am your Gemini assistant. What can I help you with?")
        while run_assistant():
            time.sleep(1)
    finally:
        stop() 