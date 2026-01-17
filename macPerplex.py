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
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime
from pynput import keyboard
import socket
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Import audio processing module
from audio_processor import (
    AudioProcessor,
    play_double_beep,
    play_start_beep,
    play_stop_beep,
    play_submit_beep
)

# Optional: prompt cleanup (Groq)
try:
    from prompt_cleanup import CleanupConfig, cleanup_prompt_via_groq
except Exception:
    CleanupConfig = None  # type: ignore
    cleanup_prompt_via_groq = None  # type: ignore

# Rich console for beautiful output
console = Console()

# Import configuration
try:
    from config import (
        OPENAI_API_KEY,
        ENABLE_EMOTION_ANALYSIS,
        TRIGGER_KEY_WITH_SCREENSHOT,
        TRIGGER_KEY_AUDIO_ONLY
    )
except ImportError:
    print("❌ Error: config.py not found!")
    print("Please create config.py with your settings.")
    print("See config.py.example for reference.")
    exit(1)

# Optional config for Groq prompt cleanup (keep backwards compatible)
try:
    import config as _cfg

    ENABLE_PROMPT_CLEANUP = bool(getattr(_cfg, "ENABLE_PROMPT_CLEANUP", False))
    GROQ_API_KEY = str(getattr(_cfg, "GROQ_API_KEY", "") or "")
    GROQ_BASE_URL = str(getattr(_cfg, "GROQ_BASE_URL", "https://api.groq.com/openai/v1") or "https://api.groq.com/openai/v1")
    GROQ_CLEANUP_MODEL = str(getattr(_cfg, "GROQ_CLEANUP_MODEL", "llama3-8b-8192") or "llama3-8b-8192")
    GROQ_TIMEOUT_S = float(getattr(_cfg, "GROQ_TIMEOUT_S", 2.5) or 2.5)

    ENABLE_RESPONSE_FORMAT_HINT = bool(getattr(_cfg, "ENABLE_RESPONSE_FORMAT_HINT", False))
    RESPONSE_FORMAT_APPEND_TEXT = str(getattr(_cfg, "RESPONSE_FORMAT_APPEND_TEXT", "") or "")
except Exception:
    ENABLE_PROMPT_CLEANUP = False
    GROQ_API_KEY = ""
    GROQ_BASE_URL = "https://api.groq.com/openai/v1"
    GROQ_CLEANUP_MODEL = "llama3-8b-8192"
    GROQ_TIMEOUT_S = 2.5
    ENABLE_RESPONSE_FORMAT_HINT = False
    RESPONSE_FORMAT_APPEND_TEXT = ""

# Cache for Perplexity window handle (so we don't search every time)
PERPLEXITY_WINDOW_HANDLE = None

# Global region selector instance
REGION_SELECTOR = None


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
    
    def __del__(self):
        """Cleanup subprocess if RegionSelector is garbage collected."""
        self._cleanup_process()
        
    def start(self):
        """Start the overlay via subprocess."""
        import tempfile
        import os
        
        self.start_point = None
        self.end_point = None
        self.is_selecting = False
        self.selection_complete = False
        
        # Create temp file for result (using mkstemp for security)
        fd, self._result_file = tempfile.mkstemp(suffix='.txt', prefix='region_')
        os.close(fd)  # Close file descriptor, overlay will write to it
        
        # Find overlay_process.py (same directory as this script)
        script_dir = Path(__file__).parent
        overlay_script = script_dir / "overlay_process.py"
        
        if not overlay_script.exists():
            console.print(f"   [yellow]⚠[/yellow] Overlay script not found: {overlay_script}")
            self._start_pynput_fallback()
            return
        
        # Run as subprocess - use pythonw if available for better GUI behavior
        python_exe = sys.executable
        
        try:
            # Start subprocess - keep it simple, don't capture output so GUI can work
            self._process = subprocess.Popen(
                [python_exe, str(overlay_script), self._result_file]
            )
            console.print("   [cyan]📐 REGION SELECT:[/cyan] [dim]Drag to select, ESC to cancel[/dim]")
            console.print("   [dim]📐 (Or just release pedal for window under cursor)[/dim]")
            
        except Exception as e:
            console.print(f"   [yellow]⚠[/yellow] Could not start overlay: {e}")
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
                console.print(f"   [green]✓[/green] Selection started at ({x}, {y})")
            else:
                if self.is_selecting:
                    self.end_point = (x, y)
                    self.is_selecting = False
                    self.selection_complete = True
                    region = self.get_region()
                    if region:
                        console.print(f"   [green]✓[/green] Region selected: {region[2]}x{region[3]} pixels")
        
        def on_move(x, y):
            if self.is_selecting:
                self.end_point = (x, y)
        
        self._mouse_listener = mouse.Listener(on_click=on_click, on_move=on_move)
        self._mouse_listener.start()
        console.print("   [dim]📐 (No visual overlay - using mouse tracking)[/dim]")
    
    def _cleanup_process(self):
        """Internal method to clean up subprocess."""
        if self._process:
            try:
                # Check if process is still running
                if self._process.poll() is None:
                    # Process still running, try graceful termination
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        # Force kill if terminate didn't work
                        self._process.kill()
                        self._process.wait()  # Reap zombie
            except Exception:
                pass  # Process already dead or other error
            finally:
                self._process = None
    
    def stop(self):
        """Stop the overlay and read result."""
        import os
        
        # Clean up subprocess
        self._cleanup_process()
        
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
                            console.print(f"   [green]✓[/green] Region: {w}x{h} at ({x}, {y})")
                    os.unlink(self._result_file)
            except (OSError, ValueError):
                pass  # File I/O or parsing errors
        
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
                    
                console.print(f"   [green]✓[/green] SELECTED: {owner_name} (window {window_id})")
                return window_id, owner_name, (x, y, width, height)
        
        console.print("   [yellow]⚠[/yellow] No window found under mouse cursor")
        return None, None, None
        
    except Exception as e:
        import traceback
        console.print(f"   [yellow]⚠[/yellow] Error getting window under mouse: {e}")
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
    console.print("   [dim]Falling back to front-to-back scan...[/dim]")
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
            
            console.print(f"   [dim]Found: {owner_name} (window {window_id})[/dim]")
            return window_id, owner_name, (x, y, width, height)
        
        console.print("   [yellow]⚠[/yellow] No suitable window found")
        return None, None, None
        
    except Exception as e:
        console.print(f"   [yellow]⚠[/yellow] Error: {e}")
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
        console.print(f"   [green]✓[/green] Sharpened and saved as lossless PNG")
        return True
    except Exception as e:
        console.print(f"   [yellow]⚠[/yellow] Sharpening failed: {e}")
        # Fallback: just copy the file
        try:
            import shutil
            shutil.copy(input_path, output_path)
            return True
        except (OSError, IOError):
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
                    console.print(f"[green]✓ Captured window via Quartz:[/green] {target_app_name or 'unknown'}")
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
                        console.print(f"[green]✓ Captured window:[/green] {target_app_name or 'unknown'}")
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
                        console.print(f"[green]✓ Captured:[/green] {app_name}")
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
            console.print("[red]✗ Screenshot file was not created[/red]")
            return None
        
        file_size = screenshot_path.stat().st_size
        if file_size < 1000:  # Less than 1KB is definitely wrong
            console.print(f"[red]✗ Screenshot file too small:[/red] {file_size} bytes")
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
                    except (ValueError, TypeError):
                        pass  # Parsing errors
        except (subprocess.SubprocessError, OSError):
            pass  # sips command failures
        
        # Convert to MB for display
        size_mb = file_size / (1024 * 1024)
        console.print(f"[green]✓ Captured screenshot:[/green] [dim]{screenshot_path}[/dim]")
        console.print(f"[dim]  File size: {size_mb:.2f} MB ({file_size:,} bytes)[/dim]")
        
        return str(screenshot_path)
            
    except subprocess.TimeoutExpired:
        console.print("[red]✗ Screenshot capture timed out[/red]")
        return None
    except Exception as e:
        console.print(f"[red]✗ Screenshot capture failed:[/red] {e}")
        return None

# ============ MAIN PROCESSING FUNCTION ============
def send_to_perplexity(driver, wait, result, screenshot_path=None):
    """Send transcribed audio and optional screenshot to Perplexity with emotion context.
    
    Args:
        result: Dict from AudioProcessor with transcript, emotions, etc.
        screenshot_path: Optional path to screenshot
    """
    
    try:
        console.print("\n[dim]" + "="*60 + "[/dim]")
        console.print("[bold cyan]🎯 PROCESSING...[/bold cyan]")
        console.print("[dim]" + "="*60 + "[/dim]")
        
        if not result:
            console.print("[bold red]❌ No audio data, aborting...[/bold red]")
            return
        
        # Step 1: Get transcript and emotion data from result
        raw_transcript = result['transcript']
        message_text = raw_transcript
        emotions = result.get('emotions')
        emotion_scores = result.get('emotion_scores')
        audio_path = result.get('audio_path')

        # Optional: cleanup transcript via Groq before sending
        if ENABLE_PROMPT_CLEANUP:
            if not GROQ_API_KEY or GROQ_API_KEY.startswith("your-"):
                console.print("[yellow]⚠ Prompt cleanup enabled, but GROQ_API_KEY is not set. Sending raw transcript.[/yellow]")
            elif not cleanup_prompt_via_groq or not CleanupConfig:
                console.print("[yellow]⚠ Prompt cleanup module unavailable. Sending raw transcript.[/yellow]")
            else:
                console.print("[cyan]🧹 Cleaning up transcript (Groq)...[/cyan]")
                cleaned = cleanup_prompt_via_groq(
                    raw_transcript,
                    CleanupConfig(
                        api_key=GROQ_API_KEY,
                        base_url=GROQ_BASE_URL,
                        model=GROQ_CLEANUP_MODEL,
                        timeout_s=GROQ_TIMEOUT_S,
                    ),
                )
                if cleaned and cleaned.strip():
                    message_text = cleaned
                    if message_text != raw_transcript:
                        console.print("[green]✓[/green] Transcript cleaned")
                        console.print(f"[dim]   Before: {raw_transcript}[/dim]")
                        console.print(f"[dim]   After:  {message_text}[/dim]")
                else:
                    console.print("[yellow]⚠ Prompt cleanup failed/timeout. Sending raw transcript.[/yellow]")
        
        # Add emotion context to message if emotions detected (structured JSON format)
        if emotions and emotion_scores and ENABLE_EMOTION_ANALYSIS:
            import json
            # Build structured emotion metadata with scores nested
            emotion_data = {
                'source': 'hume_prosody',
                'scores': emotion_scores
            }
            
            # Add metadata if available
            if result.get('emotion_metadata'):
                metadata = result['emotion_metadata']
                # Add all metadata fields
                for key, value in metadata.items():
                    emotion_data[key] = value
            
            emotion_json = json.dumps(emotion_data, separators=(',', ':'))
            emotion_context = f"[voice_affect: {emotion_json}] "
            message_with_context = emotion_context + message_text
            
            emotions_display = ', '.join([f"{e}({emotion_scores[e]:.2f})" for e in emotions])
            console.print(f"[magenta]🎭 Adding emotion context:[/magenta] [dim]{emotions_display}[/dim]")
            console.print(f"[dim]   Full message to send: {message_with_context[:100]}...[/dim]")
        else:
            message_with_context = message_text
            console.print(f"[dim]   No emotion context (emotions={emotions}, scores={emotion_scores}, enabled={ENABLE_EMOTION_ANALYSIS})[/dim]")

        # Optional: append response formatting hint (avoid newlines to prevent accidental submits)
        if ENABLE_RESPONSE_FORMAT_HINT and RESPONSE_FORMAT_APPEND_TEXT:
            append_text = " ".join(RESPONSE_FORMAT_APPEND_TEXT.strip().split())
            if append_text:
                joiner = " " if not message_with_context.endswith((" ", "\t")) else ""
                message_with_context = f"{message_with_context}{joiner}{append_text}"
                console.print("[dim]   🧾 Appended response format hint (TL;DR + full answer)[/dim]")
        
        # Step 2: Check if we have a screenshot (captured earlier)
        if screenshot_path:
            console.print(f"[cyan]📸 Using pre-captured screenshot:[/cyan] [dim]{screenshot_path}[/dim]")
        else:
            console.print("[yellow]⏭️  No screenshot (audio-only mode)[/yellow]")

        # Step 3: Check if user wants Deep Research mode (check original transcript, not emotion context)
        # Use *raw transcript* for mode switching decisions (avoid any chance a model alters keywords)
        wants_deep_research = "research" in raw_transcript.lower()
        if wants_deep_research:
            console.print("[bold magenta]🔬 'research' detected - will enable Deep Research mode[/bold magenta]")

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
                except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                    pass  # Chrome activation not critical
        except Exception:
            pass  # URL check failed
        
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
                    except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                        pass  # Chrome activation not critical
            except Exception:
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
                except Exception:
                    # Switching failed, try to recover
                    try:
                        driver.switch_to.window(original_handle)
                    except Exception:
                        pass  # Can't recover, continue to next window
                    continue
        
        if not perplexity_handle:
            console.print("[bold red]❌ Could not find Perplexity tab![/bold red]")
            console.print("   [yellow]→[/yellow] Please open [link]perplexity.ai[/link] in Chrome")
            console.print("   [dim]💡 Tip: Keep the Perplexity tab visible/active to avoid searching[/dim]")
            try:
                driver.switch_to.window(current_handle)
            except Exception:
                pass  # Can't switch back, continue anyway
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

        # Step 5: Set search mode (Search vs Research) for this query
        # It's a segmented control: click "Search" for normal, "Research" for deep research
        try:
            # Check which mode is currently active
            research_button = driver.find_element(By.XPATH, "//button[@aria-label='Research' and @role='radio']")
            is_research_on = (research_button.get_attribute("data-state") == "checked")
            
            console.print(f"[dim]   Mode currently: {'RESEARCH' if is_research_on else 'SEARCH'}[/dim]")
            console.print(f"[dim]   This query wants: {'RESEARCH' if wants_deep_research else 'SEARCH'}[/dim]")
            
            # Click the appropriate button if we need to change modes
            if wants_deep_research and not is_research_on:
                # Switch to Research mode
                console.print("[magenta]   → Clicking Research button...[/magenta]")
                research_button.click()
                time.sleep(0.5)
                console.print("[green]   ✓[/green] Deep Research mode enabled")
                
            elif not wants_deep_research and is_research_on:
                # Switch back to Search mode - click the Search button
                console.print("[magenta]   → Clicking Search button (normal mode)...[/magenta]")
                search_button = driver.find_element(By.XPATH, "//button[@aria-label='Search' and @role='radio']")
                search_button.click()
                time.sleep(0.5)
                console.print("[green]   ✓[/green] Normal Search mode enabled")
            else:
                console.print(f"[dim]   ✓ Already in correct mode[/dim]")
                
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Could not set search mode: {e}")
            console.print("[dim]   Continuing with current mode...[/dim]")

        # Step 6: Type the transcribed message (with emotion context if available)
        console.print(f"[bold]⌨️  Typing message:[/bold] [cyan]\"{message_with_context}\"[/cyan]")
        chat_input.click()
        chat_input.send_keys(message_with_context)
        console.print("[green]✓[/green] Message typed!")

        # Step 6: Upload screenshot AFTER typing message
        if screenshot_path:
            console.print(f"[bold]📤 Preparing to upload file:[/bold] [dim]{screenshot_path}[/dim]")
            
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
                console.print("[red]✗ File doesn't exist, skipping upload[/red]")
            else:
                file_size = file_path.stat().st_size
                print(f"   File size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
                
                # Get absolute path - must be a single file, not a directory
                abs_path = str(file_path.resolve())
                
                # Double-check it's a file, not a directory
                if not file_path.is_file():
                    console.print(f"[red]✗ ERROR: Path is not a file:[/red] {abs_path}")
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
                            except (StaleElementReferenceException, Exception) as e:
                                print(f"   - Could not clear input {idx}: {e}")
                        
                        time.sleep(0.5)  # Brief pause after clearing
                        
                        # Re-query file inputs after clearing (prevents stale element if page re-rendered)
                        file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                        if not file_inputs:
                            print("   ✗ ERROR: File inputs disappeared after clearing!")
                            print("   Skipping upload...")
                        else:
                            print(f"   Re-queried: found {len(file_inputs)} file input(s)")
                            
                            # Use the first file input (freshly queried)
                            file_input = file_inputs[0]
                            
                            # Check if it accepts multiple files
                            try:
                                multiple_attr = file_input.get_attribute('multiple')
                                accept_attr = file_input.get_attribute('accept')
                                print(f"   Input attributes: multiple={multiple_attr}, accept={accept_attr}")
                            except StaleElementReferenceException:
                                print("   ⚠ File input went stale, re-querying one more time...")
                                file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                                if not file_inputs:
                                    print("   ✗ ERROR: Cannot find file inputs!")
                                    raise
                                file_input = file_inputs[0]
                                multiple_attr = file_input.get_attribute('multiple')
                                accept_attr = file_input.get_attribute('accept')
                                print(f"   Input attributes: multiple={multiple_attr}, accept={accept_attr}")
                            
                            # Send ONLY this one file path to the first input
                            print(f"   Sending file path to input...")
                            try:
                                file_input.send_keys(abs_path)
                                print("   ✓ File path sent to input!")
                            except StaleElementReferenceException:
                                print("   ⚠ File input went stale during send, re-querying and retrying...")
                                file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                                if file_inputs:
                                    file_input = file_inputs[0]
                                    file_input.send_keys(abs_path)
                                    print("   ✓ File path sent to input (after retry)!")
                                else:
                                    raise Exception("File inputs disappeared")
                            
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
                            except StaleElementReferenceException as e:
                                print(f"   ⚠ Could not verify file (element stale): {e}")
                            except Exception as e:
                                print(f"   ⚠ Could not verify file: {e}")
                
                # Wait for upload to complete by watching for remove button
                console.print("[bold yellow]📤 Waiting for upload to complete...[/bold yellow]")
                try:
                    # Wait for the remove button to appear (indicates upload complete)
                    # This returns immediately when found, no arbitrary delays!
                    remove_button = wait.until(
                        EC.presence_of_element_located((By.XPATH, "//button[@data-testid='remove-uploaded-file']"))
                    )
                    console.print("[green]✓ Upload complete![/green]")
                    
                except TimeoutException:
                    # Fallback: try the old broad selector as backup
                    console.print("[dim]   Remove button not found, trying fallback detection...[/dim]")
                    try:
                        # Look for any upload indicator as backup
                        wait.until(
                            EC.presence_of_element_located((By.XPATH, 
                                "//img[contains(@src, 'blob:')] | "
                                "//div[contains(@class, 'preview')] | "
                                "//button[contains(@aria-label, 'Remove')]"
                            ))
                        )
                        console.print("[green]✓ Upload detected (fallback method)![/green]")
                    except TimeoutException:
                        console.print(f"[yellow]⚠ No upload indicator after 20s[/yellow]")
                        console.print("[dim]   Upload may have failed. Continuing anyway...[/dim]")

        # Step 7: Click send (no delays needed for audio-only)
        console.print("[bold]🔍 Looking for send button...[/bold]")
        try:
            send_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Submit']"))
            )
            console.print("[bold cyan]🚀 Clicking send...[/bold cyan]")
            
            # Scroll button into view first
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", send_button)
            
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
    except (AttributeError, TypeError):
        pass  # Key object doesn't have expected attributes
    return False

def on_press(key, audio_processor):
    """Handle key press events - start recording."""
    global REGION_SELECTOR
    
    try:
        # Check for screenshot + audio trigger
        if check_key_match(key, TRIGGER_KEY_WITH_SCREENSHOT):
            if not audio_processor.recorder.is_recording:
                play_double_beep()  # Audio feedback
                audio_processor.recorder.capture_screenshot = True
                key_display = TRIGGER_KEY_WITH_SCREENSHOT.replace('_r', ' (Right)').replace('_', ' ').title()
                console.print("\n[dim]" + "="*60 + "[/dim]")
                console.print(f"[bold cyan]🦶 {key_display} PRESSED[/bold cyan] - Recording with screenshot...")
                console.print("[dim]" + "="*60 + "[/dim]")
                
                # Start region selector for optional drag-to-select
                REGION_SELECTOR = RegionSelector()
                REGION_SELECTOR.start()
                
                # Store current window info as fallback (in case no region is selected)
                window_id, app_name, bounds = get_frontmost_window_id()
                audio_processor.recorder.fallback_window_id = window_id
                audio_processor.recorder.fallback_app_name = app_name
                audio_processor.recorder.fallback_bounds = bounds
                
                # Start recording audio (no screenshot yet - will capture on release)
                audio_processor.start_recording(take_screenshot=False)
        
        # Check for audio-only trigger
        elif check_key_match(key, TRIGGER_KEY_AUDIO_ONLY):
            if not audio_processor.recorder.is_recording:
                play_start_beep()  # Audio feedback
                audio_processor.recorder.capture_screenshot = False
                key_display = TRIGGER_KEY_AUDIO_ONLY.replace('_r', ' (Right)').replace('_', ' ').title()
                console.print("\n[dim]" + "="*60 + "[/dim]")
                console.print(f"[bold yellow]🦶 {key_display} PRESSED[/bold yellow] - Recording audio only...")
                console.print("[dim]" + "="*60 + "[/dim]")
                audio_processor.start_recording(take_screenshot=False)
    except Exception as e:
        print(f"Error in key press handler: {e}")

def on_release(key, audio_processor, driver, wait):
    """Handle key release events - stop recording and process."""
    global REGION_SELECTOR
    
    try:
        # Check if either trigger key was released
        if check_key_match(key, TRIGGER_KEY_WITH_SCREENSHOT) or check_key_match(key, TRIGGER_KEY_AUDIO_ONLY):
            if audio_processor.recorder.is_recording:
                play_stop_beep()  # Audio feedback
                screenshot_path = None
                
                # Handle screenshot capture (only for screenshot mode)
                try:
                    if audio_processor.recorder.capture_screenshot:
                        # Stop the region selector
                        if REGION_SELECTOR:
                            REGION_SELECTOR.stop()
                            region = REGION_SELECTOR.get_region()
                            REGION_SELECTOR = None
                            
                            if region:
                                # User selected a region - capture it
                                console.print("[cyan]📸 Capturing selected region...[/cyan]")
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                screenshot_path = Path(f"/tmp/perplexity_screenshot_{timestamp}.png")
                                
                                if capture_region_screenshot(region, screenshot_path):
                                    console.print("[green]✓ Region screenshot captured![/green]")
                                else:
                                    console.print("[yellow]⚠ Region capture failed, trying window fallback...[/yellow]")
                                    screenshot_path = None
                            
                            # No region selected or region capture failed - use window fallback
                            if not screenshot_path:
                                console.print(f"[cyan]📸 Capturing window:[/cyan] {getattr(audio_processor.recorder, 'fallback_app_name', 'unknown')}...")
                                screenshot_path = capture_screenshot_func(
                                    getattr(audio_processor.recorder, 'fallback_window_id', None),
                                    getattr(audio_processor.recorder, 'fallback_app_name', None),
                                    getattr(audio_processor.recorder, 'fallback_bounds', None)
                                )
                                if screenshot_path:
                                    console.print("[green]✓ Window screenshot captured![/green]")
                                else:
                                    console.print("[yellow]⚠ Screenshot capture failed[/yellow]")
                    
                    # Stop audio recording and process (transcription + emotion)
                    result = audio_processor.stop_recording_and_process()
                    
                    if result:
                        send_to_perplexity(driver, wait, result, screenshot_path)
                        
                finally:
                    # Ensure region selector is cleaned up even if exception occurred
                    if REGION_SELECTOR:
                        try:
                            REGION_SELECTOR.stop()
                        except Exception:
                            pass
                        REGION_SELECTOR = None
                    
    except Exception as e:
        print(f"Error in key release handler: {e}")
        # Clean up region selector if there was an error
        if REGION_SELECTOR:
            REGION_SELECTOR.stop()
            REGION_SELECTOR = None


# ============ STARTUP CLEANUP ============
def cleanup_orphaned_temp_files():
    """Clean up any orphaned temp files from previous runs/crashes."""
    import glob
    import os
    
    try:
        # Find all macPerplex temp files
        patterns = [
            "/tmp/perplexity_screenshot_*.png",
            "/tmp/perplexity_audio_*.wav",
            "/tmp/perplexity_temp*.png",
            "/tmp/region_*.txt"
        ]
        
        cleaned = 0
        for pattern in patterns:
            for filepath in glob.glob(pattern):
                try:
                    # Delete files older than 1 hour
                    if time.time() - os.path.getmtime(filepath) > 3600:
                        os.unlink(filepath)
                        cleaned += 1
                except Exception:
                    pass  # File might be in use or already deleted
        
        if cleaned > 0:
            console.print(f"[dim]🗑️  Cleaned up {cleaned} orphaned temp file(s)[/dim]")
    except Exception:
        pass  # Cleanup failures shouldn't prevent app from starting


# ============ CONNECT TO CHROME ============
# FIRST: Open Chrome with: /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome_dev_profile"
# Then navigate to perplexity.ai and log in
console.print(Panel.fit(
    "[bold cyan]🚀 macPerplex[/bold cyan]\n[dim]Voice AI for Perplexity[/dim]",
    border_style="cyan"
))

# Clean up any orphaned files from previous crashes
cleanup_orphaned_temp_files()

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
    """
    Check if *Chrome DevTools* is reachable on port 9222.

    Note: A plain TCP connect can yield false-positives if some other process is
    listening on 9222. We verify by querying the DevTools HTTP endpoint.
    """
    # 1) Fast TCP check
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        result = sock.connect_ex(("127.0.0.1", 9222))
        sock.close()
        if result != 0:
            return False
    except OSError:
        return False

    # 2) Verify it's actually Chrome DevTools
    try:
        import json
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1.5) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read().decode("utf-8"))

        # Typical keys: "Browser", "webSocketDebuggerUrl"
        browser = (data.get("Browser") or "").lower()
        ws_url = data.get("webSocketDebuggerUrl") or ""
        if "chrome" not in browser:
            return False
        if not ws_url.startswith("ws://"):
            return False
        return True
    except Exception:
        # Anything unexpected -> treat as "not in debug mode" so we show the
        # startup instructions instead of failing later with webdriver attach.
        return False

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
    
    # Create audio processor
    audio_processor = AudioProcessor()
    
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
        on_press=lambda key: on_press(key, audio_processor),
        on_release=lambda key: on_release(key, audio_processor, driver, wait)
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

