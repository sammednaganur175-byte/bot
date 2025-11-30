# main2.py - Raspberry Pi Camera version
from flask import Flask, render_template_string, Response, request, jsonify
import threading
import time
import socket
import requests
import numpy as np
import subprocess
import sys
import json
try:
    import cv2
except ImportError:
    print("ERROR: Install opencv-python")
    sys.exit(1)

try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    try:
        import tensorflow.lite as tflite
    except ImportError:
        print("ERROR: Install tensorflow")
        sys.exit(1)

# ===== CONFIG =====
ESP8266_IP = "10.82.36.186"  # robot UDP IP
ESP8266_PORT = 8888
ESP8266_STATUS_PORT = 8889  # For receiving status updates

# Car Assistant API
CAR_ASSISTANT_URL = "http://10.82.36.233:8000"  # Chat bot server IP (fallback if offline)

FRAME_W = 320
FRAME_H = 240

# TFLite model
MODEL_PATH = "ei-model.tflite"
CONFIDENCE_THRESHOLD = 0.12  # Lower for better edge detection

# Speed control variables
forward_speed = 200  # Default forward speed (0-255) - increased
turn_speed = 120     # Default turn speed (0-255) - increased

# Target tracking variables
DEBOUNCE_FRAMES = 5   # Reduced for faster response
SEARCH_FRAMES = 15    # Reduced search time
detection_history = []  # Track recent detections
HISTORY_SIZE = 3      # Smaller window for faster response
position_history = []  # Track position for smoothing
POSITION_HISTORY_SIZE = 3
frames_without_detection = 0
last_known_x = None
target_locked = False

CMD_MIN_INTERVAL = 0.05
FRAME_SKIP = 4

# ===== GLOBALS =====
app = Flask(__name__)
frame_lock = threading.Lock()
output_frame = None
running = True

mode_lock = threading.Lock()
current_mode = "MANUAL"  # MANUAL or AUTO

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
last_send_time = 0.0
last_sent_cmd = None

# Ultrasonic status
ultrasonic_distance = 0
ultrasonic_safe = True
status_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
status_sock.bind(('', ESP8266_STATUS_PORT))
status_sock.settimeout(0.1)

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

# ===== Raspberry Pi Camera =====
class RPiCamera:
    def __init__(self):
        self.frame = None
        self.running = False
        self.thread = None
        self.process = None
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._capture_frames)
        self.thread.daemon = True
        self.thread.start()
        time.sleep(3)
        
    def _capture_frames(self):
        while self.running:
            try:
                cmd = ['rpicam-jpeg', '-o', '-', '--width', '640', '--height', '480', 
                       '--nopreview', '-n', '-t', '1']
                
                while self.running:
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2)
                    if result.returncode == 0 and result.stdout:
                        try:
                            frame = cv2.imdecode(np.frombuffer(result.stdout, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if frame is not None:
                                self.frame = frame
                        except:
                            pass
                    time.sleep(0.03)
                            
            except Exception as e:
                print(f"[CAMERA] Error: {e}")
                time.sleep(1)
                
    def read(self):
        return self.frame is not None, self.frame
        
    def isOpened(self):
        return self.running and self.frame is not None
        
    def release(self):
        self.running = False
        if self.process:
            self.process.terminate()
        if self.thread:
            self.thread.join()

print("[CAMERA] Starting Raspberry Pi Camera...")
camera = RPiCamera()
camera.start()
time.sleep(1)
if camera.isOpened():
    print("[CAMERA] Raspberry Pi Camera ready")
else:
    print("[CAMERA] Waiting for camera initialization...")

def send_burst(command, times, delay=0.05):
    for _ in range(times):
        sock.sendto(command.encode(), (ESP8266_IP, ESP8266_PORT))
        time.sleep(delay)
    sock.sendto("STOP".encode(), (ESP8266_IP, ESP8266_PORT))

def send_speed_command(direction):
    """Send direction command with current speed settings"""
    global forward_speed, turn_speed
    if direction == "FORWARD":
        cmd = f"FORWARD:{forward_speed}"
    elif direction in ["LEFT", "RIGHT"]:
        cmd = f"{direction}:{turn_speed}"
    else:
        cmd = direction
    sock.sendto(cmd.encode(), (ESP8266_IP, ESP8266_PORT))

def query_car_assistant(question):
    """Send POST request to car assistant /query endpoint with fallback"""
    try:
        response = requests.post(f"{CAR_ASSISTANT_URL}/query", 
                               json={"query": question}, 
                               timeout=3)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API offline - HTTP {response.status_code}"}
    except Exception as e:
        return {"error": f"API offline - {str(e)}"}

# ===== UDP sending helpers (rate-limited, send-on-change) =====
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
        # respect min interval
        return
    send_udp_once(cmd)

def tracking_loop():
    global output_frame, current_mode, frames_without_detection, last_known_x, target_locked, camera, ultrasonic_distance, ultrasonic_safe
    frame_count = 0

    while running:
        ret, frame = camera.read()
        if not ret or frame is None:
            time.sleep(0.1)
            continue

        img = cv2.resize(frame, (FRAME_W, FRAME_H))
        H, W = img.shape[:2]

        # Always draw zone lines regardless of mode
        # 3-Zone system: LEFT | CENTER | RIGHT (adjusted for better edge detection)
        left_zone = int(W * 0.35)   # 0-35% (wider left zone)
        right_zone = int(W * 0.65)  # 65-100% (wider right zone)
        
        # Draw zone boundaries with thick white lines
        cv2.line(img, (left_zone, 0), (left_zone, H), (255, 255, 255), 5)
        cv2.line(img, (right_zone, 0), (right_zone, H), (255, 255, 255), 5)
        
        # Draw colored zone overlays (semi-transparent)
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (left_zone, H), (0, 255, 255), -1)  # Yellow LEFT
        cv2.rectangle(overlay, (left_zone, 0), (right_zone, H), (0, 255, 0), -1)  # Green CENTER
        cv2.rectangle(overlay, (right_zone, 0), (W, H), (255, 0, 255), -1)  # Magenta RIGHT
        cv2.addWeighted(overlay, 0.1, img, 0.9, 0, img)
        
        # Zone labels
        cv2.putText(img, "LEFT", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(img, "CENTER", (left_zone+10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(img, "RIGHT", (right_zone+10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 255), 2)

        with mode_lock:
            mode_now = current_mode

        if mode_now == "AUTO":
            frame_count += 1
            if frame_count % FRAME_SKIP != 0:
                with frame_lock:
                    output_frame = img.copy()
                continue

            # TFLite inference
            img_resized = cv2.resize(img, (input_width, input_height), interpolation=cv2.INTER_NEAREST)
            if input_channels == 1:
                img_processed = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
                img_processed = np.expand_dims(img_processed, axis=-1)
            else:
                img_processed = img_resized[:, :, ::-1]
            
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

                # Add to detection history for smoothing
                detection_history.append(max_val)
                if len(detection_history) > HISTORY_SIZE:
                    detection_history.pop(0)
                
                # Use average confidence for more stable detection
                avg_confidence = sum(detection_history) / len(detection_history)
                
                if avg_confidence > CONFIDENCE_THRESHOLD:
                    detected = True
                    grid_h, grid_w, _ = output_data.shape
                    center_x = int((max_x + 0.5) * (W / grid_w))
                    center_y = int((max_y + 0.5) * (H / grid_h))
                    
                    # Add position smoothing
                    position_history.append(center_x)
                    if len(position_history) > POSITION_HISTORY_SIZE:
                        position_history.pop(0)
                    
                    # Use smoothed position
                    center_x = int(sum(position_history) / len(position_history))
                    
                    # Update tracking
                    last_known_x = center_x
                    frames_without_detection = 0
                    target_locked = True
                    
                    # Show detection with confidence and zone info
                    zone_name = "LEFT" if center_x < left_zone else "RIGHT" if center_x > right_zone else "CENTER"
                    cv2.circle(img, (center_x, center_y), 15, (0, 255, 0), 3)
                    cv2.putText(img, f"{avg_confidence:.2f} {zone_name}", (center_x+20, center_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            else:
                boxes = interpreter.get_tensor(output_details[0]['index'])[0]
                scores = interpreter.get_tensor(output_details[2]['index'])[0]
                best_idx = np.argmax(scores)
                # Add to detection history for smoothing
                detection_history.append(scores[best_idx])
                if len(detection_history) > HISTORY_SIZE:
                    detection_history.pop(0)
                
                # Use average confidence for more stable detection
                avg_confidence = sum(detection_history) / len(detection_history)
                
                if avg_confidence > CONFIDENCE_THRESHOLD:
                    ymin, xmin, ymax, xmax = boxes[best_idx]
                    center_x = int((xmin + xmax) / 2 * W)
                    center_y = int((ymin + ymax) / 2 * H)
                    detected = True
                    
                    # Add position smoothing
                    position_history.append(center_x)
                    if len(position_history) > POSITION_HISTORY_SIZE:
                        position_history.pop(0)
                    
                    # Use smoothed position
                    center_x = int(sum(position_history) / len(position_history))
                    
                    # Update tracking
                    last_known_x = center_x
                    frames_without_detection = 0
                    target_locked = True
                    
                    zone_name = "LEFT" if center_x < left_zone else "RIGHT" if center_x > right_zone else "CENTER"
                    cv2.rectangle(img, (int(xmin*W), int(ymin*H)), (int(xmax*W), int(ymax*H)), (0,255,0), 3)
                    cv2.putText(img, f"{avg_confidence:.2f} {zone_name}", (int(xmin*W), int(ymin*H)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Target tracking logic
            if not detected:
                frames_without_detection += 1
            
            # Use last known position if recently lost
            tracking_x = center_x if detected else last_known_x
            
            # Control logic with 3 zones (improved responsiveness)
            status = "STOP"
            zone_color = (0, 0, 255)  # Red for stop
            
            if detected or (target_locked and frames_without_detection < DEBOUNCE_FRAMES):
                if tracking_x and tracking_x < left_zone:
                    status = "LEFT"
                    zone_color = (0, 255, 255)  # Yellow
                    send_speed_command("LEFT")
                    time.sleep(0.06)  # Reduced delay for faster response
                    send_udp_once("STOP")
                elif tracking_x and tracking_x < right_zone:
                    status = "FORWARD"
                    zone_color = (0, 255, 0)  # Green
                    send_speed_command("FORWARD")
                else:
                    status = "RIGHT"
                    zone_color = (255, 0, 255)  # Magenta
                    send_speed_command("RIGHT")
                    time.sleep(0.06)  # Reduced delay for faster response
                    send_udp_once("STOP")
            else:
                if frames_without_detection > SEARCH_FRAMES:
                    target_locked = False
                    last_known_x = None
                    position_history.clear()  # Clear position history when target lost
                send_udp_if_changed("STOP")
            
            # Status display
            cv2.putText(img, f"STATUS: {status}", (10, H-60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, zone_color, 3)
            cv2.putText(img, f"SPEED: F{forward_speed} T{turn_speed}", (10, H-40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            safety_color = (0, 255, 0) if ultrasonic_safe else (0, 0, 255)
            cv2.putText(img, f"ULTRASONIC: {ultrasonic_distance}cm", (10, H-15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, safety_color, 2)
        else:
            # Manual mode - show static status
            cv2.putText(img, "STATUS: MANUAL", (10, H-60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 3)
            cv2.putText(img, f"SPEED: F{forward_speed} T{turn_speed}", (10, H-40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            safety_color = (0, 255, 0) if ultrasonic_safe else (0, 0, 255)
            cv2.putText(img, f"ULTRASONIC: {ultrasonic_distance}cm", (10, H-15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, safety_color, 2)

        # Check for ultrasonic status updates
        try:
            data, addr = status_sock.recvfrom(64)
            status_msg = data.decode().strip()
            if status_msg.startswith("DIST:"):
                ultrasonic_distance = int(status_msg.split(":")[1])
                ultrasonic_safe = ultrasonic_distance > 100 or ultrasonic_distance == 0
        except:
            pass

        with frame_lock:
            output_frame = img.copy()
        time.sleep(0.001)

# ===== Flask endpoints and video generator =====
HTML_PAGE = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Robot Control</title>
  <style>
    body{background:#111;color:#eee;font-family:Arial;text-align:center}
    .video{border:4px solid #333;display:inline-block;margin:12px}
    .btn{padding:12px 18px;margin:6px;font-size:16px;border-radius:6px;border:none;cursor:pointer}
    .btn-mode{background:#1e90ff;color:#fff;width:80%}
    .btn-danger{background:#dc3545;color:#fff}
    .rc{display:flex;gap:10px;justify-content:center;align-items:center;flex-wrap:wrap}
    .dir{width:60px;height:60px;border-radius:6px;background:#333;color:#fff;font-size:20px}
    .speed-control{margin:20px auto;max-width:400px;padding:20px;background:#222;border-radius:10px}
    .slider-container{margin:15px 0;text-align:left}
    .slider{width:100%;height:25px;border-radius:5px;background:#444;outline:none;-webkit-appearance:none}
    .slider::-webkit-slider-thumb{appearance:none;width:25px;height:25px;border-radius:50%;background:#1e90ff;cursor:pointer}
    .slider::-moz-range-thumb{width:25px;height:25px;border-radius:50%;background:#1e90ff;cursor:pointer;border:none}
    .chatbot{max-width:500px;margin:20px auto;background:#222;border-radius:10px;padding:20px}
    .chat-messages{height:200px;overflow-y:auto;background:#333;border-radius:5px;padding:10px;margin-bottom:10px}
    .message{margin:5px 0;padding:8px;border-radius:5px}
    .user-message{background:#1e90ff;text-align:right}
    .bot-message{background:#555;text-align:left}
    .api-status{background:#dc3545;color:#fff;padding:5px;border-radius:3px;font-size:12px;margin-bottom:10px}
    .chat-input{display:flex;gap:10px}
    .chat-input input{flex:1;padding:10px;border:none;border-radius:5px;background:#444;color:#fff}
    .chat-input button{padding:10px 15px;background:#1e90ff;color:#fff;border:none;border-radius:5px;cursor:pointer}
  </style>
</head>
<body>
  <h1>Human Follower Robot</h1>
  <div class="video">
    <img src="{{ url_for('video_feed') }}" width="400" />
  </div>
  <h3>Mode: <span id="mode">{{ mode }}</span></h3>
  <button class="btn btn-mode" onclick="setMode('AUTO')">ENABLE AUTO TRACKING</button>
  <button class="btn btn-mode btn-danger" onclick="setMode('MANUAL')">SWITCH TO MANUAL</button>

  <div class="speed-control">
    <h3>Speed Control</h3>
    <div class="slider-container">
      <label>Forward Speed: <span id="forward-value">{{ forward_speed }}</span></label>
      <input type="range" min="100" max="255" value="{{ forward_speed }}" class="slider" id="forward-speed" oninput="updateSpeed('forward', this.value)">
    </div>
    <div class="slider-container">
      <label>Turn Speed: <span id="turn-value">{{ turn_speed }}</span></label>
      <input type="range" min="80" max="200" value="{{ turn_speed }}" class="slider" id="turn-speed" oninput="updateSpeed('turn', this.value)">
    </div>
  </div>

  <div id="rc" style="display:{{ 'block' if mode=='MANUAL' else 'none' }};">
    <h3>Remote Control</h3>
    <div class="rc">
      <button class="dir" onmousedown="sendWithSpeed('FORWARD')" onmouseup="send('STOP')">▲</button>
      <button class="dir" onmousedown="sendWithSpeed('LEFT')" onmouseup="send('STOP')">◀</button>
      <button class="dir" onmousedown="send('STOP')" onmouseup="send('STOP')">■</button>
      <button class="dir" onmousedown="sendWithSpeed('RIGHT')" onmouseup="send('STOP')">▶</button>
      <button class="dir" onmousedown="send('BACKWARD')" onmouseup="send('STOP')">▼</button>
    </div>
    <br/>
    <button class="btn" onclick="testBackward()">TEST BACKWARD (0.5s)</button>
    <button class="btn" onclick="send('MOTOR_TEST')">MOTOR TEST</button>
  </div>

  <div class="chatbot">
    <h3>Car Assistant</h3>
    <div class="api-status" id="api-status">API Status: Checking...</div>
    <div class="chat-messages" id="chat-messages"></div>
    <div class="chat-input">
      <input type="text" id="chat-input" placeholder="Ask about car maintenance, repairs, etc..." onkeypress="if(event.key==='Enter')sendMessage()">
      <button onclick="sendMessage()">Send</button>
    </div>
  </div>

<script>
let forwardSpeed = {{ forward_speed }};
let turnSpeed = {{ turn_speed }};

function setMode(m){
  fetch('/set_mode/' + m).then(()=> location.reload());
}
function send(cmd){
  fetch('/control/' + cmd);
}
function sendWithSpeed(direction){
  let speed = direction === 'FORWARD' ? forwardSpeed : turnSpeed;
  fetch('/control/' + direction + ':' + speed);
}
function updateSpeed(type, value){
  if(type === 'forward'){
    forwardSpeed = value;
    document.getElementById('forward-value').textContent = value;
    fetch('/set_speed/forward/' + value);
  } else {
    turnSpeed = value;
    document.getElementById('turn-value').textContent = value;
    fetch('/set_speed/turn/' + value);
  }
}
function testBackward(){
  send('BACKWARD');
  setTimeout(()=> send('STOP'), 500);
}

function addMessage(message, isUser){
  const messages = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'message ' + (isUser ? 'user-message' : 'bot-message');
  div.textContent = message;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function sendMessage(){
  const input = document.getElementById('chat-input');
  const query = input.value.trim();
  if(!query) return;
  
  addMessage(query, true);
  input.value = '';
  
  fetch('/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({query: query})
  })
  .then(r => r.json())
  .then(data => addMessage(data.response, false))
  .catch(e => addMessage('Error connecting to assistant', false));
}

// Check API status on page load
fetch('/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({query: 'test'})
})
.then(r => r.json())
.then(data => {
  const status = document.getElementById('api-status');
  if(data.response.includes('offline')) {
    status.textContent = 'API Status: Offline (Using Local Responses)';
    status.style.background = '#dc3545';
  } else {
    status.textContent = 'API Status: Online';
    status.style.background = '#28a745';
  }
})
.catch(e => {
  document.getElementById('api-status').textContent = 'API Status: Error';
});
</script>
</body>
</html>
"""

@app.route('/')
def index():
    with mode_lock:
        mode = current_mode
    return render_template_string(HTML_PAGE, mode=mode, forward_speed=forward_speed, turn_speed=turn_speed)

@app.route('/video_feed')
def video_feed():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/set_mode/<mode>')
def set_mode(mode):
    global current_mode
    with mode_lock:
        current_mode = mode
    # ensure robot safe state on mode switch
    send_udp_once("STOP")
    return "OK"

@app.route('/control/<cmd>')
def control(cmd):
    with mode_lock:
        if current_mode == "MANUAL":
            # direct immediate command (single send). The ESP implements safety timeout.
            send_udp_once(cmd.upper())
    return "OK"

@app.route('/set_speed/<speed_type>/<int:value>')
def set_speed(speed_type, value):
    global forward_speed, turn_speed
    if speed_type == 'forward':
        forward_speed = max(100, min(255, value))  # Minimum 100 for movement
    elif speed_type == 'turn':
        turn_speed = max(80, min(200, value))      # Minimum 80 for turning
    return "OK"

# ===== CHATBOT ROUTES =====
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        query = data.get('query', '').lower()
        
        # Try to connect to Car Assistant API first
        try:
            response = requests.post(
                f"{CAR_ASSISTANT_URL}/query",
                json={"query": query},
                timeout=3
            )
            if response.status_code == 200:
                return jsonify(response.json())
        except:
            pass  # Fall back to local responses
        
        # Fallback local car assistant responses
        if any(word in query for word in ['engine', 'motor', 'start']):
            return jsonify({"response": "Check engine oil level, battery connections, and fuel. If engine won't start, verify spark plugs and air filter."})
        elif any(word in query for word in ['brake', 'stop']):
            return jsonify({"response": "Check brake fluid level, brake pads thickness, and listen for squealing sounds. Replace pads if worn."})
        elif any(word in query for word in ['oil', 'change']):
            return jsonify({"response": "Change engine oil every 5,000-7,500 miles. Use recommended oil viscosity for your vehicle."})
        elif any(word in query for word in ['tire', 'wheel']):
            return jsonify({"response": "Check tire pressure monthly, rotate tires every 6,000 miles, and inspect for wear patterns."})
        elif any(word in query for word in ['battery']):
            return jsonify({"response": "Clean battery terminals, check voltage (12.6V when off), and replace every 3-5 years."})
        elif any(word in query for word in ['transmission']):
            return jsonify({"response": "Check transmission fluid level and color. Service every 30,000-60,000 miles depending on usage."})
        elif any(word in query for word in ['coolant', 'radiator', 'overheat']):
            return jsonify({"response": "Check coolant level, inspect for leaks, and flush system every 30,000 miles or as recommended."})
        else:
            return jsonify({"response": "Car Assistant API is offline. I can help with basic car maintenance questions about engine, brakes, oil, tires, battery, transmission, and cooling system."})
            
    except Exception as e:
        return jsonify({"response": "Sorry, there was an error processing your request."})

def generate():
    while running:
        with frame_lock:
            frame = None if output_frame is None else output_frame.copy()
        if frame is None:
            time.sleep(0.05)
            continue
        (flag, encodedImage) = cv2.imencode(".jpg", frame)
        if not flag:
            time.sleep(0.05)
            continue
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')
        time.sleep(0.02)

# ===== app start =====
if __name__ == '__main__':
    t = threading.Thread(target=tracking_loop, daemon=True)
    t.start()
    # start Flask
    print("Starting Flask on 0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)