#!/usr/bin/env python3
"""
macPerplex - Voice-controlled AI assistant for Perplexity
Capture screenshots and ask questions using voice commands

Author: macPerplex
Python: 3.10+
Platform: macOS
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime
from pynput import keyboard
import sounddevice as sd
import numpy as np
import wave
from openai import OpenAI
import socket
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

# Rich console for beautiful output
console = Console()

# Import configuration
try:
    from config import (
        OPENAI_API_KEY,
        OPENAI_STT_MODEL,
        TRIGGER_KEY_WITH_SCREENSHOT,
        TRIGGER_KEY_AUDIO_ONLY,
        AUDIO_SAMPLE_RATE,
        AUDIO_CHANNELS,
        MAX_RECORDING_DURATION
    )
except ImportError:
    print("❌ Error: config.py not found!")
    print("Please create config.py with your settings.")
    print("See config.py.example for reference.")
    exit(1)

# Cache for Perplexity window handle (so we don't search every time)
PERPLEXITY_WINDOW_HANDLE = None

# Global region selector instance
REGION_SELECTOR = None


# ============ AUDIO FEEDBACK ============
def play_beep(frequency=800, duration=0.1, volume=0.3):
    """Play a simple beep tone for audio feedback."""
    try:
        sample_rate = 44100
        samples = int(sample_rate * duration)
        t = np.linspace(0, duration, samples, False)
        tone = volume * np.sin(2 * np.pi * frequency * t)
        sd.play(tone, sample_rate)
        sd.wait()
    except Exception as e:
        # Don't let beep failures break the app
        pass

def play_double_beep():
    """Play double beep for screenshot + audio mode."""
    try:
        play_beep(800, 0.08, 0.25)  # First beep
        time.sleep(0.05)
        play_beep(1000, 0.08, 0.25)  # Second beep (higher)
    except:
        pass

def play_start_beep():
    """Play single beep for audio-only mode start."""
    play_beep(900, 0.1, 0.3)

def play_stop_beep():
    """Play beep when recording stops."""
    play_beep(700, 0.12, 0.3)  # Lower tone

def play_submit_beep():
    """Play beep when message is submitted."""
    play_beep(1200, 0.15, 0.25)  # Higher, longer tone


# ============ REGION SELECTION WITH QT OVERLAY ============
class RegionSelector:
    """
    Track mouse drag to select a screen region while recording.
    Uses PySide6/Qt for visual overlay via subprocess (overlay_process.py).
    Falls back to pynput-only if PySide6 not available.
    """
    
    def __init__(self):
        self.start_point = None  # Screen coordinates
        self.end_point = None    # Screen coordinates
        self.is_selecting = False
        self.selection_complete = False
        self._process = None
        self._result_file = None
        
    def start(self):
        """Start the overlay via subprocess."""
        import tempfile
        import os
        
        self.start_point = None
        self.end_point = None
        self.is_selecting = False
        self.selection_complete = False
        
        # Create temp file for result
        self._result_file = tempfile.mktemp(suffix='.txt', prefix='region_')
        
        # Find overlay_process.py (same directory as this script)
        script_dir = Path(__file__).parent
        overlay_script = script_dir / "overlay_process.py"
        
        if not overlay_script.exists():
            print(f"   ⚠ Overlay script not found: {overlay_script}")
            self._start_pynput_fallback()
            return
        
        # Run as subprocess - use pythonw if available for better GUI behavior
        python_exe = sys.executable
        
        try:
            # Start subprocess - keep it simple, don't capture output so GUI can work
            self._process = subprocess.Popen(
                [python_exe, str(overlay_script), self._result_file]
            )
            print("   📐 REGION SELECT: Drag to select, ESC to cancel")
            print("   📐 (Or just release pedal for window under cursor)")
            
        except Exception as e:
            print(f"   ⚠ Could not start overlay: {e}")
            self._start_pynput_fallback()
    
    def _start_pynput_fallback(self):
        """Fallback to pynput-only mode (no visual overlay)."""
        from pynput import mouse
        
        def on_click(x, y, button, pressed):
            from pynput.mouse import Button
            if button != Button.left:
                return
            if pressed:
                self.start_point = (x, y)
                self.end_point = (x, y)
                self.is_selecting = True
                print(f"   ✓ Selection started at ({x}, {y})")
            else:
                if self.is_selecting:
                    self.end_point = (x, y)
                    self.is_selecting = False
                    self.selection_complete = True
                    region = self.get_region()
                    if region:
                        print(f"   ✓ Region selected: {region[2]}x{region[3]} pixels")
        
        def on_move(x, y):
            if self.is_selecting:
                self.end_point = (x, y)
        
        self._mouse_listener = mouse.Listener(on_click=on_click, on_move=on_move)
        self._mouse_listener.start()
        print("   📐 (No visual overlay - using mouse tracking)")
    
    def stop(self):
        """Stop the overlay and read result."""
        import os
        
        # Wait for subprocess to finish (with timeout)
        if self._process:
            try:
                self._process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                try:
                    self._process.wait(timeout=0.5)
                except:
                    self._process.kill()
        
        # Read result from file
        if self._result_file:
            try:
                if os.path.exists(self._result_file):
                    with open(self._result_file, 'r') as f:
                        content = f.read().strip()
                    if content:
                        parts = content.split(',')
                        if len(parts) == 4:
                            x, y, w, h = map(int, parts)
                            self.start_point = (x, y)
                            self.end_point = (x + w, y + h)
                            self.selection_complete = True
                            print(f"   ✓ Region: {w}x{h} at ({x}, {y})")
                    os.unlink(self._result_file)
            except:
                pass
        
        # Stop pynput listener if it was used
        if hasattr(self, '_mouse_listener'):
            self._mouse_listener.stop()
    
    def get_region(self):
        """Get the selected region as (x, y, width, height) or None if no selection."""
        if not self.selection_complete or not self.start_point or not self.end_point:
            return None
        
        x1, y1 = self.start_point
        x2, y2 = self.end_point
        
        # Normalize coordinates
        x = min(x1, x2)
        y = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        
        # Minimum size threshold
        if width < 50 or height < 50:
            return None
        
        return (int(x), int(y), int(width), int(height))


# ============ PERMISSION CHECKS ============
def check_accessibility_permission():
    """Check if Accessibility permission is granted."""
    try:
        from ApplicationServices import AXIsProcessTrusted
        return AXIsProcessTrusted()
    except ImportError:
        return None  # Can't check

def check_screen_recording_permission():
    """Check if Screen Recording permission is granted (macOS 10.15+)."""
    try:
        from Quartz import CGPreflightScreenCaptureAccess
        return CGPreflightScreenCaptureAccess()
    except (ImportError, AttributeError):
        # CGPreflightScreenCaptureAccess not available on older macOS
        return None  # Can't check

def check_microphone_permission():
    """Check if Microphone permission is granted by trying to list audio devices."""
    try:
        import sounddevice as sd
        # Try to get the default input device - this will fail if no permission
        devices = sd.query_devices()
        default_input = sd.query_devices(kind='input')
        return default_input is not None
    except Exception:
        return None  # Can't check or no permission

def check_permissions():
    """Check all required macOS permissions and warn if missing."""
    console.print("\n[bold cyan]🔐 Checking macOS permissions...[/bold cyan]")
    
    all_ok = True
    
    # Check Accessibility
    accessibility = check_accessibility_permission()
    if accessibility is True:
        console.print("   [green]✓[/green] Accessibility: Granted")
    elif accessibility is False:
        console.print("   [red]❌ Accessibility: NOT GRANTED[/red]")
        console.print("      [yellow]→[/yellow] System Settings → Privacy & Security → Accessibility")
        console.print("      [yellow]→[/yellow] Add and enable Terminal (or your terminal app)")
        all_ok = False
    else:
        console.print("   [yellow]?[/yellow] Accessibility: Could not check")
    
    # Check Screen Recording
    screen_recording = check_screen_recording_permission()
    if screen_recording is True:
        console.print("   [green]✓[/green] Screen Recording: Granted")
    elif screen_recording is False:
        console.print("   [red]❌ Screen Recording: NOT GRANTED[/red]")
        console.print("      [yellow]→[/yellow] System Settings → Privacy & Security → Screen Recording")
        console.print("      [yellow]→[/yellow] Add and enable Terminal (or your terminal app)")
        all_ok = False
    else:
        console.print("   [yellow]?[/yellow] Screen Recording: Could not check")
    
    # Input Monitoring is usually bundled with Accessibility on modern macOS
    console.print("   [blue]ℹ️[/blue]  Input Monitoring: Usually shares Accessibility permission")
    
    # Check Microphone
    microphone = check_microphone_permission()
    if microphone is True:
        console.print("   [green]✓[/green] Microphone: Available")
    elif microphone is False:
        console.print("   [red]❌ Microphone: NOT AVAILABLE[/red]")
        console.print("      [yellow]→[/yellow] System Settings → Privacy & Security → Microphone")
        console.print("      [yellow]→[/yellow] Add and enable Terminal (or your terminal app)")
        all_ok = False
    else:
        console.print("   [yellow]?[/yellow] Microphone: Could not check")
    
    if not all_ok:
        console.print("\n[bold yellow]⚠️  Some permissions missing! The app may not work correctly.[/bold yellow]")
        console.print("   After granting permissions, RESTART Terminal completely (Cmd+Q).\n")
    else:
        console.print("   [bold green]✓ All permissions OK![/bold green]\n")
    
    return all_ok

# ============ AUDIO RECORDING ============
class AudioRecorder:
    """Simple push-to-talk audio recorder with live visualization."""
    def __init__(self):
        self.is_recording = False
        self.audio_chunks = []
        self.stream = None
        self.capture_screenshot = True  # Track whether to capture screenshot
        self.screenshot_path = None  # Store screenshot taken at start
        self.live_display = None  # Rich Live display for audio visualization
        self.start_time = None  # Track recording start time
    
    def start_recording(self, take_screenshot=False, window_id=None, app_name=None, window_bounds=None):
        """Start recording audio. Optionally capture screenshot of specified window."""
        if self.is_recording:
            return
        
        self.is_recording = True
        self.audio_chunks = []
        self.screenshot_path = None
        
        # Capture screenshot using the pre-captured window ID and bounds
        if take_screenshot:
            console.print(f"[cyan]📸 Capturing screenshot of {app_name or 'window'}...[/cyan]")
            self.screenshot_path = capture_screenshot_func(window_id, app_name, window_bounds)
            if self.screenshot_path:
                console.print("[green]✓ Screenshot captured![/green]")
            else:
                console.print("[yellow]⚠ Screenshot failed, continuing with audio only[/yellow]")
        
        mode = "with screenshot" if self.capture_screenshot else "audio only"
        console.print(f"[bold]🎤 Recording {mode}...[/bold] [dim](release pedal to stop)[/dim]")
        
        self.start_time = time.time()
        
        def audio_callback(indata, frames, time_info, status):
            # Calculate RMS (volume level)
            rms = np.sqrt(np.mean(indata**2))
            
            # Store audio data
            self.audio_chunks.append(indata.copy())
            
            # Update live display with audio visualization
            if self.live_display and self.start_time:
                elapsed = time.time() - self.start_time
                
                # Create visual bar based on audio level
                bar_length = int(rms * 50)  # Scale to reasonable length
                bar_length = min(bar_length, 40)  # Cap at 40
                
                if rms > 0.02:
                    bar = "█" * bar_length
                    color = "green"
                elif rms > 0.01:
                    bar = "▓" * bar_length
                    color = "yellow"
                else:
                    bar = "░" * max(1, bar_length)
                    color = "dim"
                
                # Format elapsed time
                mins = int(elapsed // 60)
                secs = int(elapsed % 60)
                time_str = f"{mins:02d}:{secs:02d}"
                
                display_text = Text()
                display_text.append("🔴 RECORDING ", style="bold red")
                display_text.append(f"[{time_str}]", style="cyan")
                display_text.append("\n")
                display_text.append("Audio: ", style="dim")
                display_text.append(bar, style=color)
                
                try:
                    self.live_display.update(Panel(display_text, border_style="red", width=60))
                except:
                    pass
        
        try:
            # Start live display
            self.live_display = Live(console=console, refresh_per_second=10)
            self.live_display.start()
            
            self.stream = sd.InputStream(
                samplerate=AUDIO_SAMPLE_RATE,
                channels=AUDIO_CHANNELS,
                dtype='float32',
                blocksize=1024,
                callback=audio_callback
            )
            self.stream.start()
        except Exception as e:
            console.print(f"\n[bold red]❌ Error starting recording:[/bold red] {e}")
            self.is_recording = False
            if self.live_display:
                self.live_display.stop()
                self.live_display = None
    
    def stop_recording(self):
        """Stop recording and save audio file."""
        if not self.is_recording:
            return None
        
        self.is_recording = False
        
        # Stop live display
        if self.live_display:
            self.live_display.stop()
            self.live_display = None
        
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            
            console.print("[green]✓ Recording stopped[/green]")
            
            if not self.audio_chunks:
                console.print("[yellow]⚠ No audio recorded[/yellow]")
                return None
            
            # Combine all chunks
            audio_data = np.concatenate(self.audio_chunks, axis=0)
            
            # Save to WAV file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_path = Path(f"/tmp/perplexity_audio_{timestamp}.wav")
            
            # Convert to int16 for WAV
            audio_int16 = (audio_data * 32767).astype(np.int16)
            
            with wave.open(str(audio_path), 'wb') as wf:
                wf.setnchannels(AUDIO_CHANNELS)
                wf.setsampwidth(2)  # 2 bytes for int16
                wf.setframerate(AUDIO_SAMPLE_RATE)
                wf.writeframes(audio_int16.tobytes())
            
            duration = len(audio_data) / AUDIO_SAMPLE_RATE
            console.print(f"[green]✓ Audio saved:[/green] [dim]{audio_path}[/dim] [cyan]({duration:.1f} seconds)[/cyan]")
            return str(audio_path)
            
        except Exception as e:
            console.print(f"[bold red]❌ Error stopping recording:[/bold red] {e}")
            return None


def transcribe_audio(audio_path):
    """Transcribe audio using OpenAI Whisper API."""
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Transcribing audio..."),
            console=console
        ) as progress:
            task = progress.add_task("transcribe", total=None)
            
            client = OpenAI(api_key=OPENAI_API_KEY)
            
            with open(audio_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model=OPENAI_STT_MODEL,
                    file=audio_file,
                    response_format="text"
                )
        
        console.print(f"[green]✓ Transcription:[/green] [cyan]\"{transcript}\"[/cyan]")
        return transcript.strip()
        
    except Exception as e:
        console.print(f"[bold red]❌ Error transcribing audio:[/bold red] {e}")
        return None


# ============ SCREENSHOT CAPTURE ============

# Apps to skip when looking for the topmost window
SKIP_APPS = {'Terminal', 'iTerm2', 'iTerm', 'Code', 'Cursor', 'WindowServer', 'Dock'}


def get_window_under_mouse():
    """Get the window ID of the window under the mouse cursor.
    
    This captures whatever window the user is actually looking at / hovering over.
    Returns (window_id, app_name) or (None, None).
    """
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGWindowListExcludeDesktopElements,
            kCGNullWindowID,
            CGEventCreate,
            CGEventGetLocation,
        )
        from AppKit import NSScreen
        
        # Get current mouse position
        event = CGEventCreate(None)
        mouse_pos = CGEventGetLocation(event)
        mouse_x, mouse_y = mouse_pos.x, mouse_pos.y
        
        # Get all screens (for reference)
        screens = NSScreen.screens()
        
        # Get all windows
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID
        )
        
        # Find the topmost window containing the mouse cursor
        for window in window_list:
            owner_name = window.get('kCGWindowOwnerName', '')
            layer = window.get('kCGWindowLayer', -1)
            bounds = window.get('kCGWindowBounds', {})
            x = bounds.get('X', 0)
            y = bounds.get('Y', 0)
            width = bounds.get('Width', 0)
            height = bounds.get('Height', 0)
            window_id = window.get('kCGWindowNumber')
            alpha = window.get('kCGWindowAlpha', 1.0)
            
            # Skip non-normal windows, tiny windows, transparent windows
            if layer != 0:
                continue
            if width < 100 or height < 100:
                continue
            if alpha < 0.5:
                continue
            
            # Check if mouse is inside this window's bounds
            if x <= mouse_x <= x + width and y <= mouse_y <= y + height:
                # Skip Terminal/IDE if there's something else we could capture
                if owner_name in SKIP_APPS:
                    continue
                    
                print(f"   ✓ SELECTED: {owner_name} (window {window_id})")
                return window_id, owner_name, (x, y, width, height)
        
        print("   ⚠ No window found under mouse cursor")
        return None, None, None
        
    except Exception as e:
        import traceback
        print(f"   ⚠ Error getting window under mouse: {e}")
        traceback.print_exc()
        return None, None, None


def get_frontmost_window_id():
    """Get the window ID of the topmost visible application window.
    
    First tries to get the window under the mouse cursor (most intuitive).
    Falls back to scanning all windows front-to-back.
    Returns (window_id, app_name, bounds) or (None, None, None).
    bounds is (x, y, width, height) tuple.
    """
    # First, try to get the window under the mouse cursor
    window_id, app_name, bounds = get_window_under_mouse()
    if window_id:
        return window_id, app_name, bounds
    
    # Fallback: scan all windows front-to-back
    print("   Falling back to front-to-back scan...")
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGWindowListExcludeDesktopElements,
            kCGNullWindowID,
        )
        
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID
        )
        
        for window in window_list:
            owner_name = window.get('kCGWindowOwnerName', '')
            layer = window.get('kCGWindowLayer', -1)
            win_bounds = window.get('kCGWindowBounds', {})
            x = win_bounds.get('X', 0)
            y = win_bounds.get('Y', 0)
            width = win_bounds.get('Width', 0)
            height = win_bounds.get('Height', 0)
            window_id = window.get('kCGWindowNumber')
            alpha = window.get('kCGWindowAlpha', 1.0)
            
            if layer != 0 or width < 200 or height < 200 or alpha < 0.5:
                continue
            if owner_name in SKIP_APPS:
                continue
            
            print(f"   Found: {owner_name} (window {window_id})")
            return window_id, owner_name, (x, y, width, height)
        
        print("   ⚠ No suitable window found")
        return None, None, None
        
    except Exception as e:
        print(f"   ⚠ Error: {e}")
        return None, None, None


def sharpen_image_and_save(input_path, output_path):
    """Apply sharpening and save as lossless PNG for better text readability."""
    try:
        from PIL import Image, ImageFilter, ImageEnhance
        
        img = Image.open(input_path)
        
        # Apply unsharp mask for better text clarity
        # Parameters: radius, percent, threshold
        img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))
        
        # Slightly increase contrast to make text pop
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.05)
        
        # Save as lossless PNG
        img.save(output_path, 'PNG', optimize=True)
        print(f"   ✓ Sharpened and saved as lossless PNG")
        return True
    except Exception as e:
        print(f"   ⚠ Sharpening failed: {e}")
        # Fallback: just copy the file
        try:
            import shutil
            shutil.copy(input_path, output_path)
            return True
        except:
            return False


def capture_region_screenshot(region, screenshot_path):
    """
    Capture a specific region of the screen.
    
    Args:
        region: tuple of (x, y, width, height) in screen coordinates
        screenshot_path: Path to save the screenshot
    
    Returns:
        True if successful, False otherwise
    """
    x, y, width, height = region
    
    try:
        # Use screencapture with -R flag for region capture
        # -R<x,y,w,h> captures a specific region
        temp_png = Path(str(screenshot_path) + '.temp')
        
        result = subprocess.run(
            ["screencapture", "-x", "-R", f"{x},{y},{width},{height}", "-t", "png", str(temp_png)],
            capture_output=True,
            timeout=5
        )
        
        if result.returncode == 0 and temp_png.exists() and temp_png.stat().st_size > 1000:
            # Apply sharpening and save
            if sharpen_image_and_save(temp_png, screenshot_path):
                temp_png.unlink(missing_ok=True)
                return True
            else:
                # Fallback: just rename
                temp_png.rename(screenshot_path)
                return True
        else:
            if result.stderr:
                print(f"   ⚠ Region capture failed: {result.stderr.decode().strip()}")
            return False
            
    except Exception as e:
        print(f"   ⚠ Region capture error: {e}")
        return False


def capture_window_with_quartz(window_id, screenshot_path):
    """Capture a window using CGWindowListCreateImage (works better on multi-monitor)."""
    try:
        from Quartz import (
            CGWindowListCreateImage,
            CGRectNull,
            kCGWindowListOptionIncludingWindow,
            kCGWindowImageBoundsIgnoreFraming,
        )
        from Quartz import CGImageDestinationCreateWithURL, CGImageDestinationAddImage, CGImageDestinationFinalize
        from CoreFoundation import CFURLCreateFromFileSystemRepresentation, kCFAllocatorDefault
        import os
        
        # Capture the specific window at FULL Retina resolution (no kCGWindowImageNominalResolution)
        # This gives us 2x pixels on Retina displays for better text clarity
        image = CGWindowListCreateImage(
            CGRectNull,  # Capture the window's natural bounds
            kCGWindowListOptionIncludingWindow,
            window_id,
            kCGWindowImageBoundsIgnoreFraming  # Full resolution, not nominal
        )
        
        if image is None:
            print(f"   ⚠ CGWindowListCreateImage returned None")
            return False
        
        # Save as PNG (lossless) - first to temp file for sharpening
        temp_png_path = str(screenshot_path) + '.temp'
        url = CFURLCreateFromFileSystemRepresentation(
            kCFAllocatorDefault,
            temp_png_path.encode('utf-8'),
            len(temp_png_path),
            False
        )
        
        # Create PNG destination (use string UTI - constants moved in newer macOS)
        destination = CGImageDestinationCreateWithURL(url, 'public.png', 1, None)
        if destination is None:
            print(f"   ⚠ Could not create image destination")
            return False
        
        CGImageDestinationAddImage(destination, image, None)
        
        if not CGImageDestinationFinalize(destination):
            print(f"   ⚠ Failed to finalize image")
            return False
        
        # Apply sharpening and save as PNG (lossless)
        try:
            from PIL import Image, ImageFilter, ImageEnhance
            img = Image.open(temp_png_path)
            
            # Apply sharpening for better text clarity
            img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.05)
            
            # Save as PNG (lossless)
            img.save(screenshot_path, 'PNG', optimize=True)
            
            # Clean up temp file
            os.unlink(temp_png_path)
            print(f"   ✓ Captured at Retina resolution, sharpened, saved as lossless PNG")
            return True
        except Exception as e:
            # If PIL fails, just rename the temp file
            print(f"   ⚠ Sharpening failed ({e}), using raw capture")
            os.rename(temp_png_path, str(screenshot_path))
            return True
            
    except Exception as e:
        print(f"   ⚠ Quartz capture error: {e}")
        return False


def capture_screenshot_func(target_window_id=None, target_app_name=None, window_bounds=None):
    """Capture a specific window by ID or bounds, or fall back to full screen."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Use /tmp for temporary screenshots (PNG for lossless quality)
    screenshot_path = Path(f"/tmp/perplexity_screenshot_{timestamp}.png")
    
    try:
        window_captured = False
        
        # If we have a pre-captured window ID, try to capture it
        if target_window_id:
            print(f"   Capturing window ID {target_window_id} ({target_app_name or 'unknown app'})...")
            
            # First try: CGWindowListCreateImage (most reliable for specific windows)
            print(f"   Trying Quartz/CGWindowListCreateImage...")
            if capture_window_with_quartz(target_window_id, screenshot_path):
                if screenshot_path.exists() and screenshot_path.stat().st_size > 1000:
                    print(f"✓ Captured window via Quartz: {target_app_name or 'unknown'}")
                    window_captured = True
            
            # Second try: screencapture -l (window ID)
            if not window_captured:
                print(f"   Trying screencapture -l...")
                temp_png = Path(f"/tmp/perplexity_temp_{timestamp}.png")
                result = subprocess.run(
                    ["screencapture", "-x", "-o", "-l", str(target_window_id), "-t", "png", str(temp_png)],
                    capture_output=True,
                    timeout=5
                )
                
                if result.returncode == 0 and temp_png.exists() and temp_png.stat().st_size > 1000:
                    # Convert to sharpened JPEG
                    if sharpen_image_and_save(temp_png, screenshot_path):
                        print(f"✓ Captured window: {target_app_name or 'unknown'}")
                        window_captured = True
                    temp_png.unlink(missing_ok=True)
                else:
                    if result.stderr:
                        print(f"   ⚠ screencapture -l failed: {result.stderr.decode().strip()}")
        
        # If no target window ID or capture failed, try to get current topmost window
        if not window_captured:
            print("   Retrying with current topmost window...")
            window_id, app_name = get_frontmost_window_id()
            
            if window_id:
                temp_png = Path(f"/tmp/perplexity_temp2_{timestamp}.png")
                result = subprocess.run(
                    ["screencapture", "-x", "-o", "-l", str(window_id), "-t", "png", str(temp_png)],
                    capture_output=True,
                    timeout=5
                )
                
                if result.returncode == 0 and temp_png.exists() and temp_png.stat().st_size > 1000:
                    if sharpen_image_and_save(temp_png, screenshot_path):
                        print(f"✓ Captured: {app_name}")
                        window_captured = True
                    temp_png.unlink(missing_ok=True)
        
        # If window capture didn't work, fall back to full screen
        if not window_captured:
            print(f"   📸 Falling back to full screen capture...")
            
            # Fallback to full screen
            temp_png = Path(f"/tmp/perplexity_temp3_{timestamp}.png")
            result = subprocess.run(
                ["screencapture", "-x", "-t", "png", str(temp_png)],
                capture_output=True,
                timeout=5
            )
            
            if result.returncode == 0 and temp_png.exists():
                sharpen_image_and_save(temp_png, screenshot_path)
                temp_png.unlink(missing_ok=True)
        
        # Verify file exists and has content
        if not screenshot_path.exists():
            print("✗ Screenshot file was not created")
            return None
        
        file_size = screenshot_path.stat().st_size
        if file_size < 1000:  # Less than 1KB is definitely wrong
            print(f"✗ Screenshot file too small: {file_size} bytes")
            screenshot_path.unlink()
            return None
        
        # Get image dimensions using sips (built-in macOS tool)
        try:
            sips_result = subprocess.run(
                ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(screenshot_path)],
                capture_output=True,
                text=True,
                timeout=3
            )
            if sips_result.returncode == 0:
                lines = sips_result.stdout.split('\n')
                width = height = None
                for line in lines:
                    if 'pixelWidth:' in line:
                        width = line.split(':')[1].strip()
                    elif 'pixelHeight:' in line:
                        height = line.split(':')[1].strip()
                
                if width and height:
                    print(f"  Dimensions: {width} x {height} pixels")
                    
                    # Calculate megapixels
                    try:
                        w = int(width)
                        h = int(height)
                        total_pixels = w * h
                        megapixels = total_pixels / 1_000_000
                        print(f"  Resolution: {megapixels:.2f} megapixels")
                    except:
                        pass
        except:
            pass
        
        # Convert to MB for display
        size_mb = file_size / (1024 * 1024)
        print(f"✓ Captured screenshot: {screenshot_path}")
        print(f"  File size: {size_mb:.2f} MB ({file_size:,} bytes)")
        
        return str(screenshot_path)
            
    except subprocess.TimeoutExpired:
        print("✗ Screenshot capture timed out")
        return None
    except Exception as e:
        print(f"✗ Screenshot capture failed: {e}")
        return None

# ============ MAIN PROCESSING FUNCTION ============
def send_to_perplexity(driver, wait, audio_path, screenshot_path=None):
    """Transcribe audio and send to Perplexity with optional screenshot."""
    
    try:
        console.print("\n[dim]" + "="*60 + "[/dim]")
        console.print("[bold cyan]🎯 PROCESSING...[/bold cyan]")
        console.print("[dim]" + "="*60 + "[/dim]")
        
        if not audio_path:
            console.print("[bold red]❌ No audio recorded, aborting...[/bold red]")
            return
        
        # Step 1: Transcribe audio
        message_text = transcribe_audio(audio_path)
        if not message_text:
            console.print("[bold red]❌ Transcription failed, aborting...[/bold red]")
            return
        
        # Step 2: Check if we have a screenshot (captured earlier)
        if screenshot_path:
            console.print(f"[cyan]📸 Using pre-captured screenshot:[/cyan] [dim]{screenshot_path}[/dim]")
        else:
            console.print("[yellow]⏭️  No screenshot (audio-only mode)[/yellow]")

        # Step 4: Find and switch to Perplexity tab
        global PERPLEXITY_WINDOW_HANDLE
        console.print("[bold]🔍 Looking for Perplexity tab...[/bold]")
        
        current_handle = driver.current_window_handle
        perplexity_handle = None
        
        # First, check if current window is already Perplexity (avoid switching)
        try:
            if 'perplexity.ai' in driver.current_url:
                perplexity_handle = current_handle
                PERPLEXITY_WINDOW_HANDLE = perplexity_handle
                console.print("[green]✓[/green] Already on Perplexity tab")
                
                # Still need to bring Chrome to front
                try:
                    subprocess.run([
                        "osascript", "-e",
                        'tell application "Google Chrome" to activate'
                    ], check=False, capture_output=True, timeout=2)
                    time.sleep(0.3)
                except:
                    pass
        except:
            pass
        
        # If not, check cached handle first
        if not perplexity_handle and PERPLEXITY_WINDOW_HANDLE:
            try:
                driver.switch_to.window(PERPLEXITY_WINDOW_HANDLE)
                if 'perplexity.ai' in driver.current_url:
                    perplexity_handle = PERPLEXITY_WINDOW_HANDLE
                    console.print("[green]✓[/green] Switched to cached Perplexity tab")
                    
                    # Bring Chrome to front
                    try:
                        subprocess.run([
                            "osascript", "-e",
                            'tell application "Google Chrome" to activate'
                        ], check=False, capture_output=True, timeout=2)
                        time.sleep(0.3)
                    except:
                        pass
            except:
                # Handle no longer valid, clear cache
                PERPLEXITY_WINDOW_HANDLE = None
                driver.switch_to.window(current_handle)
        
        # If still not found, search through all windows (Selenium requires switching to check URL)
        if not perplexity_handle:
            console.print("   [dim]Searching all tabs for perplexity.ai...[/dim]")
            original_handle = driver.current_window_handle
            
            for handle in driver.window_handles:
                try:
                    driver.switch_to.window(handle)
                    if 'perplexity.ai' in driver.current_url:
                        perplexity_handle = handle
                        PERPLEXITY_WINDOW_HANDLE = perplexity_handle
                        console.print(f"   [green]✓[/green] Found Perplexity tab")
                        break
                    else:
                        # Switch back immediately if not the right window
                        driver.switch_to.window(original_handle)
                except:
                    try:
                        driver.switch_to.window(original_handle)
                    except:
                        pass
                    continue
        
        if not perplexity_handle:
            console.print("[bold red]❌ Could not find Perplexity tab![/bold red]")
            console.print("   [yellow]→[/yellow] Please open [link]perplexity.ai[/link] in Chrome")
            console.print("   [dim]💡 Tip: Keep the Perplexity tab visible/active to avoid searching[/dim]")
            try:
                driver.switch_to.window(current_handle)
            except:
                pass
            return
        
        # Bring Chrome window to front at macOS level
        try:
            console.print("   [dim]Bringing Chrome to front...[/dim]")
            subprocess.run([
                "osascript", "-e",
                'tell application "Google Chrome" to activate'
            ], check=False, capture_output=True, timeout=2)
            time.sleep(0.5)  # Give time for window to come forward
            console.print("   [green]✓[/green] Chrome activated")
        except Exception as e:
            console.print(f"   [yellow]⚠[/yellow] Could not activate Chrome window: {e}")
        
        # Now find the chat input
        console.print("[bold]🔍 Looking for chat input...[/bold]")
        try:
            chat_input = wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true' and @role='textbox']"))
            )
            console.print("[green]✓[/green] Found chat input!")
        except Exception as e:
            console.print(f"[bold red]❌ Failed to find chat input:[/bold red] {e}")
            console.print(f"   [dim]Page title: {driver.title}[/dim]")
            return

        # Step 5: Type the transcribed message FIRST
        console.print(f"[bold]⌨️  Typing message:[/bold] [cyan]\"{message_text}\"[/cyan]")
        chat_input.click()
        time.sleep(0.5)
        chat_input.send_keys(message_text)
        console.print("[green]✓[/green] Message typed!")
        
        # Wait for any UI updates after typing
        time.sleep(1)

        # Step 6: Upload screenshot AFTER typing message
        if screenshot_path:
            print(f"📤 Preparing to upload file: {screenshot_path}")
            
            # Debug: Show current browser window info
            try:
                current_url = driver.current_url
                current_title = driver.title
                current_handle = driver.current_window_handle
                print(f"   Browser state:")
                print(f"   - URL: {current_url}")
                print(f"   - Title: {current_title}")
                print(f"   - Handle: {current_handle}")
            except Exception as e:
                print(f"   ⚠ Could not get window info: {e}")
            
            # Debug: Show macOS focused application
            try:
                import Cocoa
                frontmost_app = Cocoa.NSWorkspace.sharedWorkspace().frontmostApplication()
                app_name = frontmost_app.localizedName()
                app_pid = frontmost_app.processIdentifier()
                print(f"   - macOS focus: {app_name} (PID: {app_pid})")
            except Exception as e:
                print(f"   ⚠ Could not get macOS app info: {e}")
            
            # Ensure chat input still has focus and page is ready
            try:
                # Re-find chat input to ensure it's still valid
                chat_input = driver.find_element(By.XPATH, "//div[@contenteditable='true' and @role='textbox']")
                # Click it to ensure focus
                chat_input.click()
                time.sleep(0.3)
                print("   ✓ Chat input re-focused")
            except Exception as e:
                print(f"   ⚠ Could not re-focus chat input: {e}")
            
            # Verify file exists and is readable before uploading
            file_path = Path(screenshot_path)
            if not file_path.exists():
                print("✗ File doesn't exist, skipping upload")
            else:
                file_size = file_path.stat().st_size
                print(f"   File size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
                
                # Get absolute path - must be a single file, not a directory
                abs_path = str(file_path.resolve())
                
                # Double-check it's a file, not a directory
                if not file_path.is_file():
                    print(f"✗ ERROR: Path is not a file: {abs_path}")
                else:
                    print(f"   Attempting file upload: {abs_path}")
                    
                    # Find ALL file input elements
                    file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                    print(f"   Found {len(file_inputs)} file input(s)")
                    
                    if not file_inputs:
                        print("   ✗ ERROR: No file input found!")
                        print("   This may indicate the page structure has changed or page isn't ready")
                    else:
                        # Clear ALL file inputs to prevent accumulation from previous runs
                        print("   Clearing all file inputs...")
                        for idx, inp in enumerate(file_inputs):
                            try:
                                driver.execute_script("arguments[0].value = '';", inp)
                                print(f"   - Cleared input {idx}")
                            except Exception as e:
                                print(f"   - Could not clear input {idx}: {e}")
                        
                        time.sleep(0.5)  # Brief pause after clearing
                        
                        # Use the first file input
                        file_input = file_inputs[0]
                        
                        # Check if it accepts multiple files
                        multiple_attr = file_input.get_attribute('multiple')
                        accept_attr = file_input.get_attribute('accept')
                        print(f"   Input attributes: multiple={multiple_attr}, accept={accept_attr}")
                        
                        # Send ONLY this one file path to the first input
                        print(f"   Sending file path to input...")
                        file_input.send_keys(abs_path)
                        print("   ✓ File path sent to input!")
                        
                        # Verify the file was actually added
                        time.sleep(1)
                        try:
                            files_added = driver.execute_script("return arguments[0].files.length", file_input)
                            print(f"   Browser reports {files_added} file(s) in input")
                            if files_added == 0:
                                print("   ⚠ WARNING: No files in input! Upload may have failed.")
                            else:
                                # Get file info from browser
                                file_info = driver.execute_script("""
                                    const file = arguments[0].files[0];
                                    return file ? {
                                        name: file.name,
                                        size: file.size,
                                        type: file.type
                                    } : null;
                                """, file_input)
                                if file_info:
                                    print(f"   ✓ File in browser: {file_info['name']} ({file_info['size']} bytes)")
                        except Exception as e:
                            print(f"   ⚠ Could not verify file: {e}")
                
                # Wait for upload to actually complete with progress spinner
                upload_complete = False
                max_wait = 15  # Wait up to 15 seconds for upload
                
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[bold yellow]Uploading screenshot..."),
                    TimeElapsedColumn(),
                    console=console
                ) as progress:
                    task = progress.add_task("upload", total=max_wait)
                    
                    for i in range(max_wait):
                        try:
                            # Look for visual indicators that file was uploaded
                            # Check for image preview, thumbnail, or remove button
                            indicators = driver.find_elements(By.XPATH, 
                                "//img[contains(@src, 'blob:') or contains(@src, 'data:image')] | "
                                "//div[contains(@class, 'preview')] | "
                                "//button[contains(@aria-label, 'Remove')] | "
                                "*[contains(@class, 'file') or contains(@class, 'attachment')]"
                            )
                            
                            # Filter to only visible elements
                            visible_indicators = [ind for ind in indicators if ind.is_displayed()]
                            
                            if visible_indicators:
                                upload_complete = True
                                break
                            
                            progress.advance(task)
                            time.sleep(1)
                            
                        except Exception as e:
                            pass
                
                if upload_complete:
                    console.print("[green]✓ Upload complete![/green]")
                    time.sleep(1)
                else:
                    console.print(f"[yellow]⚠ No visual confirmation after {max_wait}s[/yellow]")
                    console.print("[dim]   Giving extra time for upload to complete...[/dim]")
                    time.sleep(5)
        
        # Wait a moment for any UI updates
        time.sleep(1)

        # Step 7: Verify we have content to send
        console.print("[green]✓[/green] Ready to send")
        time.sleep(1)

        # Step 8: Click send
        console.print("[bold]🔍 Looking for send button...[/bold]")
        try:
            send_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Submit']"))
            )
            console.print("[bold cyan]🚀 Clicking send...[/bold cyan]")
            
            # Scroll button into view first
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", send_button)
            time.sleep(0.3)
            
            # Try normal click first
            try:
                send_button.click()
                play_submit_beep()  # Audio feedback
                console.print("[green]✓[/green] Send button clicked!")
            except Exception as click_error:
                # Fallback to JavaScript click if normal click fails
                console.print(f"[yellow]⚠[/yellow] Normal click failed, using JavaScript: {click_error}")
                driver.execute_script("arguments[0].click();", send_button)
                play_submit_beep()  # Audio feedback
                console.print("[green]✓[/green] Send button clicked (via JavaScript)!")
            
            # Wait a bit to see if message was sent
            console.print("[dim]Waiting for message to send...[/dim]")
            time.sleep(3)
            
            console.print("[bold green]✅ Done![/bold green] Check the browser to see the response from Perplexity.")
            console.print("[dim]" + "="*60 + "[/dim]")
            console.print("[bold]🦶 Ready for next query[/bold] [dim](Left pedal = screenshot, Right pedal = audio only)...[/dim]\n")
            
        except Exception as button_error:
            console.print(f"[bold red]❌ Could not find/click send button:[/bold red] {button_error}")
            console.print("[yellow]💡 Tip:[/yellow] Make sure the Perplexity page is fully loaded")
            console.print("[dim]The text was typed but not sent. You can click send manually.[/dim]\n")
        
    except Exception as e:
        console.print(f"[bold red]❌ Error:[/bold red] {e}")
        console.print("[bold]🦶 Try again[/bold] [dim](Left pedal = screenshot, Right pedal = audio only)...[/dim]\n")
    
    finally:
        # Clean up temporary files
        if audio_path and Path(audio_path).exists():
            try:
                Path(audio_path).unlink()
                console.print("[dim]🗑️  Cleaned up audio file[/dim]")
            except Exception as e:
                console.print(f"[yellow]⚠[/yellow] Could not delete audio file: {e}")
        
        # Clean up screenshot
        if screenshot_path and Path(screenshot_path).exists():
            try:
                Path(screenshot_path).unlink()
                console.print("[dim]🗑️  Cleaned up screenshot file[/dim]")
            except Exception as e:
                console.print(f"[yellow]⚠[/yellow] Could not delete screenshot file: {e}")


# ============ KEYBOARD LISTENER ============
def get_trigger_key_map():
    """Map trigger key strings to pynput Key objects."""
    from pynput.keyboard import Key
    
    return {
        'cmd_r': Key.cmd_r,
        'cmd': Key.cmd,
        'shift_r': Key.shift_r,
        'shift': Key.shift,
        'alt_r': Key.alt_r,
        'alt': Key.alt,
        'ctrl_r': Key.ctrl_r,
        'ctrl': Key.ctrl,
    }

def check_key_match(key, trigger_key_str):
    """Check if a key matches a trigger key string."""
    try:
        trigger_map = get_trigger_key_map()
        
        # Check for mapped modifier keys
        if trigger_key_str.lower() in trigger_map:
            return key == trigger_map[trigger_key_str.lower()]
        
        # Check for function keys (f1-f12, etc.)
        if hasattr(key, 'name'):
            return key.name.lower() == trigger_key_str.lower()
        
        # Fallback for character keys
        if hasattr(key, 'char'):
            return key.char == trigger_key_str
    except:
        pass
    return False

def on_press(key, recorder):
    """Handle key press events - start recording."""
    global REGION_SELECTOR
    
    try:
        # Check for screenshot + audio trigger
        if check_key_match(key, TRIGGER_KEY_WITH_SCREENSHOT):
            if not recorder.is_recording:
                play_double_beep()  # Audio feedback
                recorder.capture_screenshot = True
                key_display = TRIGGER_KEY_WITH_SCREENSHOT.replace('_r', ' (Right)').replace('_', ' ').title()
                console.print("\n[dim]" + "="*60 + "[/dim]")
                console.print(f"[bold cyan]🦶 {key_display} PRESSED[/bold cyan] - Recording with screenshot...")
                console.print("[dim]" + "="*60 + "[/dim]")
                
                # Start region selector for optional drag-to-select
                REGION_SELECTOR = RegionSelector()
                REGION_SELECTOR.start()
                
                # Store current window info as fallback (in case no region is selected)
                window_id, app_name, bounds = get_frontmost_window_id()
                recorder.fallback_window_id = window_id
                recorder.fallback_app_name = app_name
                recorder.fallback_bounds = bounds
                
                # Start recording audio (no screenshot yet - will capture on release)
                recorder.start_recording(take_screenshot=False)
        
        # Check for audio-only trigger
        elif check_key_match(key, TRIGGER_KEY_AUDIO_ONLY):
            if not recorder.is_recording:
                play_start_beep()  # Audio feedback
                recorder.capture_screenshot = False
                key_display = TRIGGER_KEY_AUDIO_ONLY.replace('_r', ' (Right)').replace('_', ' ').title()
                console.print("\n[dim]" + "="*60 + "[/dim]")
                console.print(f"[bold yellow]🦶 {key_display} PRESSED[/bold yellow] - Recording audio only...")
                console.print("[dim]" + "="*60 + "[/dim]")
                recorder.start_recording(take_screenshot=False)
    except Exception as e:
        print(f"Error in key press handler: {e}")

def on_release(key, recorder, driver, wait):
    """Handle key release events - stop recording and process."""
    global REGION_SELECTOR
    
    try:
        # Check if either trigger key was released
        if check_key_match(key, TRIGGER_KEY_WITH_SCREENSHOT) or check_key_match(key, TRIGGER_KEY_AUDIO_ONLY):
            if recorder.is_recording:
                play_stop_beep()  # Audio feedback
                screenshot_path = None
                
                # Handle screenshot capture (only for screenshot mode)
                if recorder.capture_screenshot:
                    # Stop the region selector
                    if REGION_SELECTOR:
                        REGION_SELECTOR.stop()
                        region = REGION_SELECTOR.get_region()
                        REGION_SELECTOR = None
                        
                        if region:
                            # User selected a region - capture it
                            print(f"📸 Capturing selected region...")
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            screenshot_path = Path(f"/tmp/perplexity_screenshot_{timestamp}.png")
                            
                            if capture_region_screenshot(region, screenshot_path):
                                print(f"✓ Region screenshot captured!")
                            else:
                                print("⚠ Region capture failed, trying window fallback...")
                                screenshot_path = None
                        
                        # No region selected or region capture failed - use window fallback
                        if not screenshot_path:
                            print(f"📸 Capturing window: {getattr(recorder, 'fallback_app_name', 'unknown')}...")
                            screenshot_path = capture_screenshot_func(
                                getattr(recorder, 'fallback_window_id', None),
                                getattr(recorder, 'fallback_app_name', None),
                                getattr(recorder, 'fallback_bounds', None)
                            )
                            if screenshot_path:
                                print("✓ Window screenshot captured!")
                            else:
                                print("⚠ Screenshot capture failed")
                
                # Stop audio recording
                audio_path = recorder.stop_recording()
                
                if audio_path:
                    send_to_perplexity(driver, wait, audio_path, screenshot_path)
                    
    except Exception as e:
        print(f"Error in key release handler: {e}")
        # Clean up region selector if there was an error
        if REGION_SELECTOR:
            REGION_SELECTOR.stop()
            REGION_SELECTOR = None


# ============ CONNECT TO CHROME ============
# FIRST: Open Chrome with: /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome_dev_profile"
# Then navigate to perplexity.ai and log in
console.print(Panel.fit(
    "[bold cyan]🚀 macPerplex[/bold cyan]\n[dim]Voice AI for Perplexity[/dim]",
    border_style="cyan"
))

# Check if OpenAI API key is set
if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("your-"):
    console.print("\n[bold red]❌ ERROR: OpenAI API key not set![/bold red]")
    console.print("Please edit [cyan]config.py[/cyan] and set your OpenAI API key.")
    console.print("Get one from: [link]https://platform.openai.com/api-keys[/link]")
    exit(1)

# Check macOS permissions
check_permissions()

console.print("[bold]🔗 Checking for Chrome with remote debugging...[/bold]")

# First, check if Chrome is running in debug mode
def check_chrome_debug_mode():
    """Check if Chrome is running with remote debugging on port 9222."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('127.0.0.1', 9222))
    sock.close()
    return result == 0

if not check_chrome_debug_mode():
    console.print("\n[bold red]❌ ERROR: Chrome is not running in debug mode![/bold red]")
    console.print("\n[bold]📋 To start Chrome with remote debugging:[/bold]")
    console.print("   [dim]1.[/dim] Close all Chrome windows")
    console.print("   [dim]2.[/dim] Run this command:")
    console.print("      [cyan]/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222 --user-data-dir=\"/tmp/chrome_dev_profile\"[/cyan]")
    console.print("   [dim]3.[/dim] Navigate to [link]https://www.perplexity.ai[/link] and log in")
    console.print("   [dim]4.[/dim] Run macPerplex again")
    console.print("\n[bold yellow]💡 Tip:[/bold yellow] Keep that Chrome window open while using macPerplex")
    exit(1)

console.print("[green]✓[/green] Chrome debug port detected")
console.print("[bold]🔗 Connecting to Chrome...[/bold]")

chrome_options = Options()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

try:
    driver = webdriver.Chrome(options=chrome_options)
    console.print(f"[green]✓[/green] Connected! Current URL: [dim]{driver.current_url}[/dim]")
    wait = WebDriverWait(driver, 20)
    
    # Create audio recorder
    recorder = AudioRecorder()
    
    # Format the key names nicely for display
    key1_display = TRIGGER_KEY_WITH_SCREENSHOT.replace('_r', ' (Right)').replace('_', ' ').title()
    key2_display = TRIGGER_KEY_AUDIO_ONLY.replace('_r', ' (Right)').replace('_', ' ').title()
    
    ready_text = Text()
    ready_text.append("✅ READY! Two modes:\n\n", style="bold green")
    ready_text.append(f"   🖼️  {key1_display} - Audio + Screenshot\n", style="bold cyan")
    ready_text.append("      Hold, speak, release → captures window under cursor\n", style="dim")
    ready_text.append("      OR drag to select a region while speaking!\n\n", style="dim")
    ready_text.append(f"   🎤 {key2_display} - Audio Only\n", style="bold yellow")
    ready_text.append("      Hold, speak, release → sends without image\n\n", style="dim")
    ready_text.append("   💡 Tips:\n", style="italic yellow")
    ready_text.append("      • Drag to select = better OCR for small text\n", style="dim")
    ready_text.append("      • Keep Perplexity tab visible for faster switching\n", style="dim")
    ready_text.append("   Press Ctrl+C to exit", style="dim")
    
    console.print(Panel(ready_text, border_style="green", expand=False))
    
    # Set up keyboard listener with both press and release handlers
    with keyboard.Listener(
        on_press=lambda key: on_press(key, recorder),
        on_release=lambda key: on_release(key, recorder, driver, wait)
    ) as listener:
        listener.join()
        
except KeyboardInterrupt:
    console.print("\n\n[bold yellow]🛑 Shutting down...[/bold yellow]")
except Exception as e:
    console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
    console.print("\n[bold yellow]💡 Troubleshooting:[/bold yellow]")
    console.print("   [dim]- Make sure Chrome is still running[/dim]")
    console.print("   [dim]- Ensure you're on https://www.perplexity.ai[/dim]")
    console.print("   [dim]- Try restarting Chrome in debug mode[/dim]")
    console.print("\n[dim]See README.md for full setup instructions[/dim]")

