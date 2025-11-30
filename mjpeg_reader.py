import requests
import numpy as np
from PIL import Image
import io
import threading
import time

class MJPEGReader:
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
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
            
    def _read_stream(self):
        try:
            response = requests.get(self.url, stream=True, timeout=5)
            response.raise_for_status()
            
            buffer = b''
            for chunk in response.iter_content(chunk_size=1024):
                if not self.running:
                    break
                    
                buffer += chunk
                
                # Look for JPEG boundaries
                start = buffer.find(b'\xff\xd8')  # JPEG start
                end = buffer.find(b'\xff\xd9')    # JPEG end
                
                if start != -1 and end != -1 and end > start:
                    jpeg_data = buffer[start:end+2]
                    buffer = buffer[end+2:]
                    
                    try:
                        # Convert to PIL Image then numpy array
                        img = Image.open(io.BytesIO(jpeg_data))
                        self.frame = np.array(img)
                    except Exception as e:
                        print(f"Error decoding frame: {e}")
                        
        except Exception as e:
            print(f"Stream error: {e}")
            
    def read(self):
        return self.frame is not None, self.frame
        
    def isOpened(self):
        return self.running and self.frame is not None

# Test the reader
if __name__ == "__main__":
    reader = MJPEGReader("http://10.30.152.68/stream")
    reader.start()
    
    time.sleep(2)  # Wait for first frame
    
    ret, frame = reader.read()
    if ret:
        print(f"Success! Frame shape: {frame.shape}")
    else:
        print("Failed to read frame")
        
    reader.stop()