import os
import time
import socket

import speech_recognition as sr
from google import genai
from google.genai import types
from gtts import gTTS
from pygame import mixer
import cv2

# ESP8266 UDP Configuration
ESP8266_IP = "10.109.142.186"  # Change this to your ESP8266 IP
UDP_PORT = 8888
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

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

# ===== Motor Functions via ESP8266 UDP ===== #
def send_command(cmd):
    try:
        sock.sendto(cmd.encode(), (ESP8266_IP, UDP_PORT))
        print(f"Sent UDP: {cmd}")
        return True
    except Exception as e:
        print(f"ESP8266 UDP Error: {e}")
        return False

def stop():
    send_command("STOP")

def forward():
    print("Moving Forward")
    send_command("FORWARD")

def backward():
    print("Moving Backward")
    send_command("BACKWARD")

def left():
    print("Turning Left")
    send_command("LEFT")

def right():
    print("Turning Right")
    send_command("RIGHT")

def rotate_in_place(step_time=0.4):
    print("Rotating in place for explore step...")
    send_command("RIGHT")  # Use RIGHT for rotation
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
            if matches(cmd, ["stop car", "stop moving", "halt", "freeze"]):
                speak_text("Stopping the car.")
                stop()
                return True

            # ===== Gemini AI Response for General Questions ===== #
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

    return True


# ===== Main Entry ===== #
if __name__ == "__main__":
    try:
        speak_text("Hello, I am your Gemini assistant. What can I help you with?")
        while run_assistant():
            time.sleep(1)
    finally:
        stop()