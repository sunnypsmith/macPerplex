# macPerplex 🎤📸

Voice-controlled AI assistant for Perplexity on macOS. Capture screenshots and ask questions using voice commands.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure
```bash
cp config.py.example config.py
# Edit config.py and add your OpenAI API key
```

### 3. Start Chrome with Remote Debugging
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome_dev_profile"
```

**Important:** After Chrome opens:
1. Navigate to https://www.perplexity.ai
2. Log in to your Perplexity account
3. Keep this Chrome window open

### 4. Run macPerplex
```bash
python3 macPerplex.py
```

## Usage

### Two Modes:

**🖼️  Screenshot + Audio** (Left pedal / F13 / Right Cmd)
- Hold the trigger, speak your question, release
- Captures the window under your mouse cursor
- Sends screenshot + transcribed audio to Perplexity

**🎤 Audio Only** (Right pedal / F14 / Right Shift)
- Hold the trigger, speak your question, release
- Sends transcribed audio to Perplexity without screenshot

## Configuration

Edit `config.py` to customize:
- `OPENAI_API_KEY` - Your OpenAI API key
- `OPENAI_STT_MODEL` - Transcription model (gpt-4o-transcribe or whisper-1)
- `TRIGGER_KEY_WITH_SCREENSHOT` - Key for screenshot mode (default: cmd_r)
- `TRIGGER_KEY_AUDIO_ONLY` - Key for audio-only mode (default: shift_r)
- Audio recording settings

## Features

✅ Voice-to-text using OpenAI Whisper  
✅ Automatic screenshot capture (focused window or full screen)  
✅ Automatic Perplexity tab detection  
✅ Two input modes (with/without screenshot)  
✅ No beeping from held keys  
✅ Temporary file cleanup  
✅ Configurable transcription model

## Requirements

- macOS
- Python 3.10+
- Google Chrome
- OpenAI API key

## macOS Permissions (Required!)

You must grant these permissions to Terminal (or your terminal app):

**System Settings → Privacy & Security:**

1. **Accessibility** - Required for keyboard/pedal input monitoring
2. **Input Monitoring** - Required for detecting key presses (often shared with Accessibility)
3. **Screen Recording** - Required for capturing window screenshots
4. **Microphone** - Required for audio recording

**After granting permissions, fully restart Terminal (Cmd+Q, then reopen).**

The script will check permissions on startup and warn you if any are missing.

## USB Foot Pedals (Optional)

You can use USB foot pedals (like iKKEGOL) instead of keyboard shortcuts for hands-free operation.

### Why F13/F14?
These are "unused" function keys that won't interfere with any application or type characters into text fields.

### Setup with ElfKey (for iKKEGOL pedals):

1. **Download ElfKey** from [ikkegol.com/downloads](https://www.ikkegol.com/downloads/)
   - Choose ARM64 for Apple Silicon Macs (M1/M2/M3)
   - Choose X64 for Intel Macs

2. **Configure the pedals:**
   - Open ElfKey
   - Click on the left pedal → Set to **F13**
   - Click on the right pedal → Set to **F14**
   - Save the configuration

3. **Update `config.py`:**
```python
TRIGGER_KEY_WITH_SCREENSHOT = 'f13'  # Left pedal - screenshot + audio
TRIGGER_KEY_AUDIO_ONLY = 'f14'       # Right pedal - audio only
```

### Usage:
- **Left pedal (F13)**: Hold, speak, release → sends screenshot + audio
- **Right pedal (F14)**: Hold, speak, release → sends audio only
- Keep your mouse cursor over the window you want to capture

## Troubleshooting

**"No such element" errors**: Make sure Chrome is on perplexity.ai  
**No audio recording**: Grant Microphone permission in System Settings  
**Screenshots are black/wrong**: Grant Screen Recording permission, restart Terminal  
**"This process is not trusted"**: Grant Accessibility permission, restart Terminal  
**Key not working**: Try holding `fn` key + trigger key  
**Multi-monitor issues**: The script detects window under mouse cursor  

## License

MIT

