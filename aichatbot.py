import os
import speech_recognition as sr
from google import genai
from gtts import gTTS
from pygame import mixer
import time
import socket

# ===== CONFIG (matching main2.py) =====
ESP8266_IP = "10.109.142.186"  # robot UDP IP
ESP8266_PORT = 8888

# UDP Socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


# Initialize Clients and Mixer
try:
    client = genai.Client()
    mixer.init()
except Exception as e:
    print(f"Initialization Error: {e}")
    exit()

r = sr.Recognizer()
mic = sr.Microphone()


# ===== Motor Functions (UDP Commands) ===== #
def send_command(cmd):
    try:
        sock.sendto(cmd.encode(), (ESP8266_IP, ESP8266_PORT))
        print(f"[UDP] -> {cmd}")
    except Exception as e:
        print(f"[UDP] Error: {e}")

def stop():
    send_command("STOP")

def forward():
    print("Moving Forward")
    send_command("FORWARD:200")

def backward():
    print("Moving Backward")
    send_command("BACKWARD")

def left():
    print("Turning Left")
    send_command("LEFT:180")

def right():
    print("Turning Right")
    send_command("RIGHT:180")


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

            cmd = command.lower()

            # Exit command
            if "exit" in cmd or "stop" in cmd:
                speak_text("Goodbye!")
                stop()
                return True

            # ===== Movement Commands (with return True) ===== #
            if "move forward" in cmd:
                speak_text("Moving forward!")
                forward()
                return True

            elif "move back" in cmd:
                speak_text("Moving backward!")
                backward()
                return True

            elif "move left" in cmd:
                speak_text("Turning left!")
                left()
                return True

            elif "move right" in cmd:
                speak_text("Turning right!")
                right()
                return True

            # ===== Gemini AI Response ===== #
            print("Thinking with Gemini...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=command
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

    return True  # keep the loop running


# ===== Main Entry ===== #
if __name__ == "__main__":
    speak_text("Hello, I am your Gemini assistant. What can I help you with?")
    while run_assistant():
        time.sleep(1)
