# Simple ESP32-CAM stream test
from flask import Flask, Response
import threading
import time
import requests
import numpy as np
from PIL import Image, ImageDraw
import io

ESP32_STREAM_URL = "http://10.30.152.68/stream"

app = Flask(__name__)
frame_lock = threading.Lock()
output_frame = None
running = True

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
                response = requests.get(self.url, stream=True, timeout=3)
                buffer = b''
                for chunk in response.iter_content(chunk_size=8192):
                    if not self.running:
                        break
                    buffer += chunk
                    
                    while True:
                        start = buffer.find(b'\xff\xd8')
                        if start == -1:
                            break
                        end = buffer.find(b'\xff\xd9', start)
                        if end == -1:
                            break
                            
                        jpeg_data = buffer[start:end+2]
                        buffer = buffer[end+2:]
                        
                        try:
                            img = Image.open(io.BytesIO(jpeg_data))
                            if self.frame is None or len(buffer) < 4096:
                                self.frame = np.array(img)
                        except:
                            pass
            except Exception as e:
                print(f"Stream error: {e}")
                time.sleep(1)
                
    def read(self):
        return self.frame is not None, self.frame

print(f"Connecting to ESP32-CAM at {ESP32_STREAM_URL}...")
camera = MJPEGCamera(ESP32_STREAM_URL)
camera.start()

def camera_loop():
    global output_frame
    while running:
        ret, frame = camera.read()
        if ret and frame is not None:
            # Add timestamp
            img = Image.fromarray(frame)
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), f"Time: {time.strftime('%H:%M:%S')}", fill=(255,255,255))
            
            with frame_lock:
                output_frame = np.array(img)
        time.sleep(0.03)

@app.route('/')
def index():
    return '<h1>ESP32-CAM Stream Test</h1><img src="/video_feed" width="640">'

@app.route('/video_feed')
def video_feed():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

def generate():
    while running:
        with frame_lock:
            frame = None if output_frame is None else output_frame.copy()
        if frame is None:
            time.sleep(0.05)
            continue
        
        img = Image.fromarray(frame.astype('uint8'))
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        frame_bytes = buffer.getvalue()
        
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.02)

if __name__ == '__main__':
    t = threading.Thread(target=camera_loop, daemon=True)
    t.start()
    print("Camera stream test starting on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)