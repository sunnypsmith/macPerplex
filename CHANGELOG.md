# Changelog

All notable changes to macPerplex will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Voice emotion analysis** with Hume.ai integration
  - Analyzes voice tone, pitch, and intensity
  - Detects 48 emotions (frustration, excitement, confusion, etc.)
  - Adds top N emotions as context to Perplexity prompts
  - Runs in parallel with transcription (no added latency)
  - Configurable via ENABLE_EMOTION_ANALYSIS
- Modular audio processing (audio_processor.py)
  - Clean separation of audio handling
  - Async parallel processing with asyncio
  - Easier to test and maintain

## [1.1.0] - 2026-01-12

### Added  
- Automatic Deep Research mode when "research" is spoken in query
  - Detects "research" keyword in transcription
  - Automatically clicks Research/Search button in segmented control
  - Sets correct mode for each query independently
- Audio normalization for consistent Whisper transcription quality
  - Normalizes to 90% peak volume
  - Caps boost at 10x to prevent noise amplification
  - Skips normalization if audio too quiet (< 0.05 peak)
  - Shows boost factor in logs
- Installation instructions in README (git clone and pip install options)
- Professional project structure (pyproject.toml, CHANGELOG.md, CONTRIBUTING.md)
- Enhanced .gitignore with comprehensive patterns

### Changed
- Improved window tab switching to minimize disruption of minimized windows
- Enhanced send button click with JavaScript fallback and scroll-into-view
- Better error messages for send button failures
- Replaced all bare except clauses with specific exception types
- More defensive exception handling throughout

### Fixed
- Send button now clicks reliably with multiple fallback strategies
- Window switching immediately returns to original tab if not Perplexity
- Audio stream resource leak on recording start failure
- Subprocess zombie process leak if RegionSelector crashes
- Stale element handling in upload verification loop
- File input race condition with re-querying after clearing
- Proper cleanup of overlay subprocess with __del__ destructor

### Removed
- test_overlay.py (development artifact no longer needed)

### Performance
- Upload detection: 5-10 seconds faster with instant WebDriverWait
- Audio-only mode: 3.5 seconds faster (removed unnecessary delays)
- Total speedup: ~8-13 seconds per query

## [1.0.0] - 2026-01-11

### Added
- Voice-to-text using OpenAI Whisper API
- Region selection with visual overlay (drag to select screen areas)
- Multi-monitor support with separate overlays per display
- Audio feedback tones for start/stop/submit actions
- Live audio visualization with real-time level indicators
- Progress spinners for transcription and uploads
- Beautiful terminal UI with Rich library
- High-resolution Retina screenshot capture with sharpening
- Language-constrained transcription (configurable via TRANSCRIPTION_LANGUAGE)
- Two input modes: screenshot+audio (F13) and audio-only (F14)
- Automatic window detection (captures window under mouse cursor)
- Automatic Perplexity tab detection and switching
- USB foot pedal support (iKKEGOL via ElfKey configuration)
- macOS permission checks on startup (Accessibility, Screen Recording, Microphone)
- Configurable trigger keys and audio settings

### Technical
- PySide6-based visual overlay system via subprocess
- CGWindowListCreateImage for direct window capture
- Selenium WebDriver for Perplexity automation
- Rich console for professional UI output
- NumPy-based audio processing and visualization
- Temporary file cleanup after processing

### Documentation
- Comprehensive README with setup instructions
- Permission setup guide for macOS
- USB foot pedal configuration guide
- Troubleshooting section

## [Unreleased]
- Coming soon: Edit transcription before sending
- Coming soon: Prompt templates
- Coming soon: Response capture

