# Voice Assistant Setup Guide

## Installation

1. **Install voice dependencies:**
   ```bash
   pip install -r requirements_voice.txt
   ```

2. **For Raspberry Pi, you may need additional system packages:**
   ```bash
   sudo apt-get update
   sudo apt-get install portaudio19-dev python3-pyaudio
   sudo apt-get install espeak espeak-data libespeak1 libespeak-dev
   sudo apt-get install flac
   ```

## Usage

### Option 1: Run Both Servers Together
```bash
python start_servers.py
```
- Main Robot Control: http://localhost:5000
- AI Voice Assistant: http://localhost:5001

### Option 2: Run Servers Separately
```bash
# Terminal 1 - Main robot control
python main2.py

# Terminal 2 - AI voice assistant
python aichatbot.py
```

## Microphone Switching

### Default Behavior
- **Raspberry Pi Microphone**: Uses the physical microphone connected to the Raspberry Pi
- **Phone Microphone**: Uses the phone's microphone via web browser

### How to Switch Microphones

1. **Via Web Interface:**
   - Go to http://localhost:5001 (AI Voice Assistant)
   - Click "Use Phone Mic" button
   - Browser will ask for microphone permission
   - Accept the permission to use phone microphone
   - Click "Use Raspberry Pi Mic" to switch back

2. **Via Main Robot Control:**
   - Go to http://localhost:5000 (Main Robot Control)
   - Use the microphone control section
   - Same permission flow applies

### Features

- **Automatic Permission Request**: When switching to phone microphone, browser automatically requests permission
- **Visual Status Indicator**: Shows which microphone is currently active
- **Fallback Support**: If phone microphone fails, automatically falls back to Raspberry Pi microphone
- **Voice Commands**: Supports basic voice commands like:
  - "Hello" - Greeting
  - "What time is it?" - Current time
  - "Switch microphone" - Information about current microphone
  - Any other speech is echoed back with a helpful response

### Troubleshooting

1. **Microphone Permission Denied:**
   - Check browser settings for microphone access
   - Try refreshing the page and clicking "Use Phone Mic" again

2. **No Audio Input:**
   - Check if microphone is working in other applications
   - Verify USB microphone is connected (for Raspberry Pi)
   - Check system audio settings

3. **Speech Recognition Errors:**
   - Ensure internet connection (uses Google Speech Recognition)
   - Speak clearly and avoid background noise
   - Check microphone levels

4. **Text-to-Speech Not Working:**
   - Install espeak on Linux: `sudo apt-get install espeak`
   - Check system audio output settings

## Technical Details

- **Speech Recognition**: Uses Google Speech Recognition API
- **Text-to-Speech**: Uses pyttsx3 with system TTS engine
- **Microphone Switching**: Seamless switching between hardware sources
- **Web Integration**: Full web-based control interface
- **Thread Safety**: All microphone operations are thread-safe