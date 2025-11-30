#!/usr/bin/env python3
import cv2
import time

url = "http://10.30.152.68/stream"
print(f"Testing connection to: {url}")

# Try different backends
backends = [
    (cv2.CAP_FFMPEG, "FFMPEG"),
    (cv2.CAP_GSTREAMER, "GSTREAMER"), 
    (cv2.CAP_ANY, "ANY")
]

for backend, name in backends:
    print(f"\nTrying backend: {name}")
    try:
        cap = cv2.VideoCapture(url, backend)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        ret, frame = cap.read()
        if ret and frame is not None:
            print(f"SUCCESS with {name}! Frame shape: {frame.shape}")
            cap.release()
            break
        else:
            print(f"Failed to read frame with {name}")
            cap.release()
    except Exception as e:
        print(f"Error with {name}: {e}")

print("Test complete")