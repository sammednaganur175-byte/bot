# main2.py - ESP32-CAM version (no OpenCV)
from flask import Flask, render_template_string, Response
import threading
import time
import socket
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import sys

try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    try:
        import tensorflow.lite as tflite
    except ImportError:
        print("ERROR: Install tensorflow")
        sys.exit(1)

# ===== CONFIG =====
ESP32_STREAM_URL = "http://10.30.152.68/stream"  # ESP32-CAM IP
ESP8266_IP = "10.30.152.186"  # robot UDP IP
ESP8266_PORT = 8888

FRAME_W = 320
FRAME_H = 240

# TFLite model
MODEL_PATH = "ei-model.tflite"
CONFIDENCE_THRESHOLD = 0.15

# Speed control variables
forward_speed = 150
turn_speed = 80

# Target tracking variables
DEBOUNCE_FRAMES = 8
SEARCH_FRAMES = 20
detection_history = []
HISTORY_SIZE = 5
frames_without_detection = 0
last_known_x = None
target_locked = False

CMD_MIN_INTERVAL = 0.08
FRAME_SKIP = 2

# ===== GLOBALS =====
app = Flask(__name__)
frame_lock = threading.Lock()
output_frame = None
running = True

mode_lock = threading.Lock()
current_mode = "MANUAL"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
last_send_time = 0.0
last_sent_cmd = None

# TFLite setup
interpreter = tflite.Interpreter(model_path=MODEL_PATH)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()
input_shape = input_details[0]['shape']
input_height = input_shape[1]
input_width = input_shape[2]
input_channels = input_shape[3]
input_index = input_details[0]['index']
is_fomo = len(output_details) == 1 and len(output_details[0]['shape']) == 4

# ===== MJPEG Stream Reader =====
class MJPEGCamera:
    def __init__(self, url):
        self.url = url
        self.frame = None
        self.running = False
        self.thread = None
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._read_stream)
        self.thread.daemon = True
        self.thread.start()
        time.sleep(2)
        
    def _read_stream(self):
        while self.running:
            try:
                response = requests.get(self.url, stream=True, timeout=5)
                buffer = b''
                for chunk in response.iter_content(chunk_size=1024):
                    if not self.running:
                        break
                    buffer += chunk
                    start = buffer.find(b'\xff\xd8')
                    end = buffer.find(b'\xff\xd9')
                    if start != -1 and end != -1 and end > start:
                        jpeg_data = buffer[start:end+2]
                        buffer = buffer[end+2:]
                        try:
                            img = Image.open(io.BytesIO(jpeg_data))
                            self.frame = np.array(img)
                        except:
                            pass
            except Exception as e:
                print(f"[CAMERA] Stream error: {e}")
                time.sleep(1)
                
    def read(self):
        return self.frame is not None, self.frame
        
    def isOpened(self):
        return self.running and self.frame is not None
        
    def release(self):
        self.running = False
        if self.thread:
            self.thread.join()

print(f"[CAMERA] Connecting to ESP32-CAM at {ESP32_STREAM_URL}...")
camera = MJPEGCamera(ESP32_STREAM_URL)
camera.start()
if camera.isOpened():
    print("[CAMERA] Connected to ESP32-CAM stream")
else:
    print("[ERROR] Cannot connect to ESP32-CAM stream")
    sys.exit(1)

def send_udp_once(cmd):
    global last_send_time, last_sent_cmd
    try:
        sock.sendto(cmd.encode(), (ESP8266_IP, ESP8266_PORT))
        last_send_time = time.time()
        last_sent_cmd = cmd
        print("[UDP] ->", cmd)
    except Exception as e:
        print("[UDP] send error:", e)

def send_udp_if_changed(cmd):
    now = time.time()
    global last_send_time, last_sent_cmd
    if cmd == last_sent_cmd and (now - last_send_time) < CMD_MIN_INTERVAL:
        return
    if (now - last_send_time) < CMD_MIN_INTERVAL and cmd != last_sent_cmd:
        return
    send_udp_once(cmd)

def send_speed_command(direction):
    global forward_speed, turn_speed
    if direction == "FORWARD":
        cmd = f"FORWARD:{forward_speed}"
    elif direction in ["LEFT", "RIGHT"]:
        cmd = f"{direction}:{turn_speed}"
    else:
        cmd = direction
    sock.sendto(cmd.encode(), (ESP8266_IP, ESP8266_PORT))

def tracking_loop():
    global output_frame, current_mode, frames_without_detection, last_known_x, target_locked, camera
    frame_count = 0

    while running:
        ret, frame = camera.read()
        if not ret or frame is None:
            print("[CAMERA] Stream disconnected, attempting reconnect...")
            camera.release()
            time.sleep(1)
            try:
                camera = MJPEGCamera(ESP32_STREAM_URL)
                camera.start()
                continue
            except:
                print("[CAMERA] Reconnection failed, retrying in 5 seconds...")
                time.sleep(5)
                continue

        # Convert to PIL Image for processing
        img = Image.fromarray(frame)
        img = img.resize((FRAME_W, FRAME_H))
        img_array = np.array(img)
        
        # Create drawing context
        draw = ImageDraw.Draw(img)
        
        # Draw zones
        left_zone = int(FRAME_W * 0.33)
        right_zone = int(FRAME_W * 0.67)
        
        # Zone lines
        draw.line([(left_zone, 0), (left_zone, FRAME_H)], fill=(255,255,255), width=3)
        draw.line([(right_zone, 0), (right_zone, FRAME_H)], fill=(255,255,255), width=3)
        
        # Zone labels
        draw.text((10, 10), "LEFT", fill=(255,255,0))
        draw.text((left_zone+10, 10), "CENTER", fill=(0,255,0))
        draw.text((right_zone+10, 10), "RIGHT", fill=(255,0,255))

        with mode_lock:
            mode_now = current_mode

        if mode_now == "AUTO":
            frame_count += 1
            if frame_count % FRAME_SKIP != 0:
                with frame_lock:
                    output_frame = np.array(img)
                continue

            # TFLite inference
            img_resized = img.resize((input_width, input_height))
            if input_channels == 1:
                img_processed = img_resized.convert('L')
                img_processed = np.expand_dims(np.array(img_processed), axis=-1)
            else:
                img_processed = np.array(img_resized)
            
            input_data = np.expand_dims(img_processed, axis=0)
            if input_details[0]['dtype'] == np.float32:
                input_data = np.float32(input_data) / 255.0
            elif input_details[0]['dtype'] == np.int8:
                input_data = (input_data.astype(np.int16) - 128).astype(np.int8)
            
            interpreter.set_tensor(input_index, input_data)
            interpreter.invoke()

            detected = False
            center_x = 0

            if is_fomo:
                output_data = interpreter.get_tensor(output_details[0]['index'])[0]
                if output_details[0]['dtype'] == np.int8:
                    output_data = (output_data.astype(np.float32) + 128) / 255.0
                if output_data.shape[2] > 1:
                    output_data = output_data[:, :, 1:]
                
                max_idx = np.argmax(output_data)
                max_y, max_x, max_c = np.unravel_index(max_idx, output_data.shape)
                max_val = output_data[max_y, max_x, max_c]

                detection_history.append(max_val)
                if len(detection_history) > HISTORY_SIZE:
                    detection_history.pop(0)
                
                avg_confidence = sum(detection_history) / len(detection_history)
                
                if avg_confidence > CONFIDENCE_THRESHOLD:
                    detected = True
                    grid_h, grid_w, _ = output_data.shape
                    center_x = int((max_x + 0.5) * (FRAME_W / grid_w))
                    center_y = int((max_y + 0.5) * (FRAME_H / grid_h))
                    
                    last_known_x = center_x
                    frames_without_detection = 0
                    target_locked = True
                    
                    # Draw detection
                    draw.ellipse([center_x-10, center_y-10, center_x+10, center_y+10], outline=(0,255,0), width=3)
                    draw.text((center_x+15, center_y), f"{avg_confidence:.2f}", fill=(0,255,0))

            # Control logic
            if not detected:
                frames_without_detection += 1
            
            tracking_x = center_x if detected else last_known_x
            
            status = "STOP"
            if detected or (target_locked and frames_without_detection < DEBOUNCE_FRAMES):
                if tracking_x and tracking_x < left_zone:
                    status = "LEFT"
                    send_speed_command("LEFT")
                    time.sleep(0.08)
                    send_udp_once("STOP")
                elif tracking_x and tracking_x < right_zone:
                    status = "FORWARD"
                    send_speed_command("FORWARD")
                else:
                    status = "RIGHT"
                    send_speed_command("RIGHT")
                    time.sleep(0.08)
                    send_udp_once("STOP")
            else:
                if frames_without_detection > SEARCH_FRAMES:
                    target_locked = False
                    last_known_x = None
                send_udp_if_changed("STOP")
            
            draw.text((10, FRAME_H-40), f"STATUS: {status}", fill=(255,255,255))
        else:
            draw.text((10, FRAME_H-40), "STATUS: MANUAL", fill=(255,255,255))

        with frame_lock:
            output_frame = np.array(img)
        time.sleep(0.005)

# Flask routes (simplified)
@app.route('/')
def index():
    return "<h1>Robot Control</h1><img src='/video_feed' width='400'><br><a href='/set_mode/AUTO'>AUTO</a> | <a href='/set_mode/MANUAL'>MANUAL</a>"

@app.route('/video_feed')
def video_feed():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/set_mode/<mode>')
def set_mode(mode):
    global current_mode
    with mode_lock:
        current_mode = mode
    send_udp_once("STOP")
    return "OK"

def generate():
    while running:
        with frame_lock:
            frame = None if output_frame is None else output_frame.copy()
        if frame is None:
            time.sleep(0.05)
            continue
        
        # Convert numpy array to JPEG
        img = Image.fromarray(frame.astype('uint8'))
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        frame_bytes = buffer.getvalue()
        
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.02)

if __name__ == '__main__':
    t = threading.Thread(target=tracking_loop, daemon=True)
    t.start()
    print("Starting Flask on 0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)