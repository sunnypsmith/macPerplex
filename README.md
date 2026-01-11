# macPerplex 🎤📸

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)
[![Status](https://img.shields.io/badge/status-stable-brightgreen.svg)]()

Voice-controlled AI assistant for Perplexity on macOS. Capture screenshots and ask questions using voice commands.

## Quick Start

### 1. Create Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
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
- Hold the trigger, speak your question
- **Option A: Region Select** - Drag to select a specific area of the screen
- **Option B: Window Capture** - Just release without dragging to capture the window under your cursor
- Sends screenshot + transcribed audio to Perplexity

**🎤 Audio Only** (Right pedal / F14 / Right Shift)
- Hold the trigger, speak your question, release
- Sends transcribed audio to Perplexity without screenshot

### Region Selection (New!)

When using Screenshot + Audio mode, you can select a specific region:

1. Press and hold the trigger (pedal/key)
2. The screen dims with a semi-transparent overlay
3. Click and drag to draw a selection rectangle
4. Release the trigger to capture just that region
5. If you don't drag, it captures the window under your cursor

**💡 Tip:** Region selection is great for capturing specific parts of a page (like tables or charts) for better OCR accuracy. Works on all monitors!

## Configuration

Edit `config.py` to customize:
- `OPENAI_API_KEY` - Your OpenAI API key
- `OPENAI_STT_MODEL` - Transcription model (gpt-4o-transcribe or whisper-1)
- `TRANSCRIPTION_LANGUAGE` - Language code (default: "en" for English)
  - Constrains transcription to specific language for better accuracy
  - Prevents unexpected languages appearing in transcription
  - Common options: "en", "es", "fr", "de", "zh", "ja"
  - [Full list of ISO 639-1 codes](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes)
- `TRIGGER_KEY_WITH_SCREENSHOT` - Key for screenshot mode (default: cmd_r)
- `TRIGGER_KEY_AUDIO_ONLY` - Key for audio-only mode (default: shift_r)
- Audio recording settings

## Features

✅ Voice-to-text using OpenAI Whisper  
✅ **Region selection** - drag to capture specific screen areas  
✅ **Multi-monitor support** - works on all connected displays  
✅ **Live audio visualization** - real-time audio levels and recording timer  
✅ **Audio feedback** - distinct tones for start/stop/submit actions  
✅ **Progress spinners** - animated feedback for transcription and uploads  
✅ Automatic window capture (window under mouse cursor)  
✅ Automatic Perplexity tab detection  
✅ Two input modes (with/without screenshot)  
✅ High-resolution Retina screenshots with sharpening  
✅ Beautiful terminal UI with Rich library  
✅ Temporary file cleanup  
✅ Configurable transcription model

## Requirements

- macOS
- Python 3.10+
- Google Chrome
- OpenAI API key
- PySide6 (for region selection overlay)
- Rich (for beautiful terminal output)

All Python dependencies are installed via `requirements.txt`

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
- **Left pedal (F13)**: Hold, speak, optionally drag to select region, release → sends screenshot + audio
- **Right pedal (F14)**: Hold, speak, release → sends audio only
- Drag to select a specific region, or just release to capture window under cursor

## Troubleshooting

**"No such element" errors**: Make sure Chrome is on perplexity.ai  
**No audio recording**: Grant Microphone permission in System Settings  
**Screenshots are black/wrong**: Grant Screen Recording permission, restart Terminal  
**"This process is not trusted"**: Grant Accessibility permission, restart Terminal  
**Key not working**: Try holding `fn` key + trigger key  
**Region overlay not showing**: Make sure PySide6 is installed (`pip install PySide6`)  
**Multi-monitor selection**: Region selection works on all monitors - just click and drag on any screen  

## License

MIT

