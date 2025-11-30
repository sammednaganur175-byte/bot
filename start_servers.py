#!/usr/bin/env python3
# start_servers.py - Start both main robot control and AI chatbot servers
import subprocess
import sys
import time
import threading

def start_main_server():
    """Start the main robot control server"""
    print("[STARTUP] Starting main robot control server...")
    try:
        subprocess.run([sys.executable, "main2.py"], check=True)
    except KeyboardInterrupt:
        print("[STARTUP] Main server stopped by user")
    except Exception as e:
        print(f"[STARTUP] Main server error: {e}")

def start_chatbot_server():
    """Start the AI chatbot server"""
    print("[STARTUP] Starting AI chatbot server...")
    time.sleep(2)  # Wait a bit for main server to start
    try:
        subprocess.run([sys.executable, "aichatbot.py"], check=True)
    except KeyboardInterrupt:
        print("[STARTUP] Chatbot server stopped by user")
    except Exception as e:
        print(f"[STARTUP] Chatbot server error: {e}")

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 ROBOT CONTROL SYSTEM STARTUP")
    print("=" * 50)
    print("Main Robot Control: http://localhost:5000")
    print("AI Voice Assistant: http://localhost:5001")
    print("=" * 50)
    
    # Start both servers in separate threads
    main_thread = threading.Thread(target=start_main_server, daemon=True)
    chatbot_thread = threading.Thread(target=start_chatbot_server, daemon=True)
    
    main_thread.start()
    chatbot_thread.start()
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STARTUP] Shutting down servers...")
        sys.exit(0)