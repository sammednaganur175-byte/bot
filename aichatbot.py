import os
import speech_recognition as sr
from google import genai
from gtts import gTTS
from pygame import mixer
import time
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)

# L298N Motor Driver Pins (matching ESP8266 configuration)
# Motor A (Left)
ENA = 18  # PWM Speed Control
IN1 = 17  # Direction 1
IN2 = 27  # Direction 2

# Motor B (Right)
ENB = 12  # PWM Speed Control
IN3 = 22  # Direction 1
IN4 = 23  # Direction 2

motor_pins = [ENA, IN1, IN2, ENB, IN3, IN4]
for pin in motor_pins:
    GPIO.setup(pin, GPIO.OUT)

# Setup PWM for speed control
motor_a_pwm = GPIO.PWM(ENA, 1000)  # 1kHz frequency
motor_b_pwm = GPIO.PWM(ENB, 1000)
motor_a_pwm.start(0)
motor_b_pwm.start(0)

# Motor speed settings
SPEED = 80  # Default speed (0-100%)


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
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.LOW)
    GPIO.output(IN3, GPIO.LOW)
    GPIO.output(IN4, GPIO.LOW)
    motor_a_pwm.ChangeDutyCycle(0)
    motor_b_pwm.ChangeDutyCycle(0)

def forward():
    print("Moving Forward")
    GPIO.output(IN1, GPIO.HIGH)
    GPIO.output(IN2, GPIO.LOW)
    GPIO.output(IN3, GPIO.HIGH)
    GPIO.output(IN4, GPIO.LOW)
    motor_a_pwm.ChangeDutyCycle(SPEED)
    motor_b_pwm.ChangeDutyCycle(SPEED)

def backward():
    print("Moving Backward")
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.HIGH)
    GPIO.output(IN3, GPIO.LOW)
    GPIO.output(IN4, GPIO.HIGH)
    motor_a_pwm.ChangeDutyCycle(SPEED)
    motor_b_pwm.ChangeDutyCycle(SPEED)

def left():
    print("Turning Left")
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.HIGH)
    GPIO.output(IN3, GPIO.HIGH)
    GPIO.output(IN4, GPIO.LOW)
    motor_a_pwm.ChangeDutyCycle(SPEED)
    motor_b_pwm.ChangeDutyCycle(SPEED)

def right():
    print("Turning Right")
    GPIO.output(IN1, GPIO.HIGH)
    GPIO.output(IN2, GPIO.LOW)
    GPIO.output(IN3, GPIO.LOW)
    GPIO.output(IN4, GPIO.HIGH)
    motor_a_pwm.ChangeDutyCycle(SPEED)
    motor_b_pwm.ChangeDutyCycle(SPEED)


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
                motor_a_pwm.stop()
                motor_b_pwm.stop()
                GPIO.cleanup()
                return False

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
