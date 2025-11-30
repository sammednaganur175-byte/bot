import os
import speech_recognition as sr
from google import genai
from gtts import gTTS
from pygame import mixer
import time
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)

# Left motor driver pins
L_IN1 = 17
L_IN2 = 27
L_IN3 = 22
L_IN4 = 23

# Right motor driver pins
R_IN1 = 5
R_IN2 = 6
R_IN3 = 13
R_IN4 = 19

motor_pins = [L_IN1, L_IN2, L_IN3, L_IN4, R_IN1, R_IN2, R_IN3, R_IN4]
for pin in motor_pins:
    GPIO.setup(pin, GPIO.OUT)


# Initialize Clients and Mixer
try:
    client = genai.Client()
    mixer.init()
except Exception as e:
    print(f"Initialization Error: {e}")
    exit()

r = sr.Recognizer()
mic = sr.Microphone()


# ===== Motor Functions ===== #
def stop():
    for pin in motor_pins:
        GPIO.output(pin, GPIO.LOW)

def forward():
    print("Moving Forward")
    GPIO.output(L_IN1, GPIO.HIGH)
    GPIO.output(L_IN2, GPIO.LOW)
    GPIO.output(R_IN1, GPIO.HIGH)
    GPIO.output(R_IN2, GPIO.LOW)

def backward():
    print("Moving Backward")
    GPIO.output(L_IN1, GPIO.LOW)
    GPIO.output(L_IN2, GPIO.HIGH)
    GPIO.output(R_IN1, GPIO.LOW)
    GPIO.output(R_IN2, GPIO.HIGH)

def left():
    print("Turning Left")
    GPIO.output(L_IN1, GPIO.LOW)
    GPIO.output(L_IN2, GPIO.HIGH)
    GPIO.output(R_IN1, GPIO.HIGH)
    GPIO.output(R_IN2, GPIO.LOW)

def right():
    print("Turning Right")
    GPIO.output(L_IN1, GPIO.HIGH)
    GPIO.output(L_IN2, GPIO.LOW)
    GPIO.output(R_IN1, GPIO.LOW)
    GPIO.output(R_IN2, GPIO.HIGH)


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
