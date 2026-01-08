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
    print("\n🔐 Checking macOS permissions...")
    
    all_ok = True
    
    # Check Accessibility
    accessibility = check_accessibility_permission()
    if accessibility is True:
        print("   ✓ Accessibility: Granted")
    elif accessibility is False:
        print("   ❌ Accessibility: NOT GRANTED")
        print("      → System Settings → Privacy & Security → Accessibility")
        print("      → Add and enable Terminal (or your terminal app)")
        all_ok = False
    else:
        print("   ? Accessibility: Could not check")
    
    # Check Screen Recording
    screen_recording = check_screen_recording_permission()
    if screen_recording is True:
        print("   ✓ Screen Recording: Granted")
    elif screen_recording is False:
        print("   ❌ Screen Recording: NOT GRANTED")
        print("      → System Settings → Privacy & Security → Screen Recording")
        print("      → Add and enable Terminal (or your terminal app)")
        all_ok = False
    else:
        print("   ? Screen Recording: Could not check")
    
    # Input Monitoring is usually bundled with Accessibility on modern macOS
    print("   ℹ️  Input Monitoring: Usually shares Accessibility permission")
    
    # Check Microphone
    microphone = check_microphone_permission()
    if microphone is True:
        print("   ✓ Microphone: Available")
    elif microphone is False:
        print("   ❌ Microphone: NOT AVAILABLE")
        print("      → System Settings → Privacy & Security → Microphone")
        print("      → Add and enable Terminal (or your terminal app)")
        all_ok = False
    else:
        print("   ? Microphone: Could not check")
    
    if not all_ok:
        print("\n⚠️  Some permissions missing! The app may not work correctly.")
        print("   After granting permissions, RESTART Terminal completely (Cmd+Q).\n")
    else:
        print("   ✓ All permissions OK!\n")
    
    return all_ok

# ============ AUDIO RECORDING ============
class AudioRecorder:
    """Simple push-to-talk audio recorder."""
    def __init__(self):
        self.is_recording = False
        self.audio_chunks = []
        self.stream = None
        self.capture_screenshot = True  # Track whether to capture screenshot
        self.screenshot_path = None  # Store screenshot taken at start
    
    def start_recording(self, take_screenshot=False, window_id=None, app_name=None, window_bounds=None):
        """Start recording audio. Optionally capture screenshot of specified window."""
        if self.is_recording:
            return
        
        self.is_recording = True
        self.audio_chunks = []
        self.screenshot_path = None
        
        # Capture screenshot using the pre-captured window ID and bounds
        if take_screenshot:
            print(f"📸 Capturing screenshot of {app_name or 'window'}...")
            self.screenshot_path = capture_screenshot_func(window_id, app_name, window_bounds)
            if self.screenshot_path:
                print("✓ Screenshot captured!")
            else:
                print("⚠ Screenshot failed, continuing with audio only")
        
        mode = "with screenshot" if self.capture_screenshot else "audio only"
        print(f"🎤 Recording {mode}... (release pedal to stop)")
        print("   Audio levels: ", end="", flush=True)
        
        def audio_callback(indata, frames, time_info, status):
            if status:
                print(f"\nStatus: {status}")
            
            # Calculate RMS (volume level)
            rms = np.sqrt(np.mean(indata**2))
            
            # Store audio data
            self.audio_chunks.append(indata.copy())
            
            # Visual feedback
            if rms > 0.02:
                print("█", end="", flush=True)
            elif rms > 0.01:
                print("▓", end="", flush=True)
            else:
                print(".", end="", flush=True)
        
        try:
            self.stream = sd.InputStream(
                samplerate=AUDIO_SAMPLE_RATE,
                channels=AUDIO_CHANNELS,
                dtype='float32',
                blocksize=1024,
                callback=audio_callback
            )
            self.stream.start()
        except Exception as e:
            print(f"\n❌ Error starting recording: {e}")
            self.is_recording = False
    
    def stop_recording(self):
        """Stop recording and save audio file."""
        if not self.is_recording:
            return None
        
        self.is_recording = False
        
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            
            print("\n✓ Recording stopped")
            
            if not self.audio_chunks:
                print("⚠ No audio recorded")
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
            print(f"✓ Audio saved: {audio_path} ({duration:.1f} seconds)")
            return str(audio_path)
            
        except Exception as e:
            print(f"❌ Error stopping recording: {e}")
            return None


def transcribe_audio(audio_path):
    """Transcribe audio using OpenAI Whisper API."""
    try:
        print("🔄 Transcribing audio...")
        
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model=OPENAI_STT_MODEL,
                file=audio_file,
                response_format="text"
            )
        
        print(f"✓ Transcription: \"{transcript}\"")
        return transcript.strip()
        
    except Exception as e:
        print(f"❌ Error transcribing audio: {e}")
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
        print(f"   Mouse position: ({mouse_x:.0f}, {mouse_y:.0f})")
        
        # Show all screens for debugging
        screens = NSScreen.screens()
        print(f"   Monitors detected: {len(screens)}")
        for i, screen in enumerate(screens):
            frame = screen.frame()
            print(f"   - Monitor {i}: origin=({frame.origin.x:.0f}, {frame.origin.y:.0f}) size=({frame.size.width:.0f}x{frame.size.height:.0f})")
        
        # Get all windows
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID
        )
        
        # Debug: show first few windows
        print(f"   Total windows: {len(window_list)}")
        shown = 0
        for window in window_list:
            owner_name = window.get('kCGWindowOwnerName', '')
            layer = window.get('kCGWindowLayer', -1)
            if layer != 0:
                continue
            bounds = window.get('kCGWindowBounds', {})
            x = bounds.get('X', 0)
            y = bounds.get('Y', 0)
            width = bounds.get('Width', 0)
            height = bounds.get('Height', 0)
            window_id = window.get('kCGWindowNumber')
            
            if width < 100 or height < 100:
                continue
                
            contains_mouse = x <= mouse_x <= x + width and y <= mouse_y <= y + height
            marker = "👆" if contains_mouse else "  "
            skip_marker = " [SKIP]" if owner_name in SKIP_APPS else ""
            print(f"   {marker} {owner_name}: pos=({x:.0f},{y:.0f}) size=({width:.0f}x{height:.0f}) id={window_id}{skip_marker}")
            shown += 1
            if shown >= 8:
                print(f"   ... and {len([w for w in window_list if w.get('kCGWindowLayer') == 0])} more layer-0 windows")
                break
        
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
    print("   Looking for window under mouse cursor...")
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


def capture_window_with_quartz(window_id, screenshot_path):
    """Capture a window using CGWindowListCreateImage (works better on multi-monitor)."""
    try:
        from Quartz import (
            CGWindowListCreateImage,
            CGRectNull,
            kCGWindowListOptionIncludingWindow,
            kCGWindowImageBoundsIgnoreFraming,
            kCGWindowImageNominalResolution,
        )
        from Quartz import CGImageDestinationCreateWithURL, CGImageDestinationAddImage, CGImageDestinationFinalize
        from CoreFoundation import CFURLCreateFromFileSystemRepresentation, kCFAllocatorDefault
        import os
        
        # Capture the specific window
        image = CGWindowListCreateImage(
            CGRectNull,  # Capture the window's natural bounds
            kCGWindowListOptionIncludingWindow,
            window_id,
            kCGWindowImageBoundsIgnoreFraming | kCGWindowImageNominalResolution
        )
        
        if image is None:
            print(f"   ⚠ CGWindowListCreateImage returned None")
            return False
        
        # Save to file
        url = CFURLCreateFromFileSystemRepresentation(
            kCFAllocatorDefault,
            str(screenshot_path).encode('utf-8'),
            len(str(screenshot_path)),
            False
        )
        
        # Create PNG destination
        from Quartz import kUTTypePNG
        destination = CGImageDestinationCreateWithURL(url, kUTTypePNG, 1, None)
        if destination is None:
            print(f"   ⚠ Could not create image destination")
            return False
        
        CGImageDestinationAddImage(destination, image, None)
        
        if CGImageDestinationFinalize(destination):
            return True
        else:
            print(f"   ⚠ Failed to finalize image")
            return False
            
    except Exception as e:
        print(f"   ⚠ Quartz capture error: {e}")
        return False


def capture_screenshot_func(target_window_id=None, target_app_name=None, window_bounds=None):
    """Capture a specific window by ID or bounds, or fall back to full screen."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Use /tmp for temporary screenshots
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
                result = subprocess.run(
                    ["screencapture", "-x", "-o", "-l", str(target_window_id), "-t", "png", str(screenshot_path)],
                    capture_output=True,
                    timeout=5
                )
                
                if result.returncode == 0 and screenshot_path.exists() and screenshot_path.stat().st_size > 1000:
                    print(f"✓ Captured window: {target_app_name or 'unknown'}")
                    window_captured = True
                else:
                    if result.stderr:
                        print(f"   ⚠ screencapture -l failed: {result.stderr.decode().strip()}")
        
        # If no target window ID or capture failed, try to get current topmost window
        if not window_captured:
            print("   Retrying with current topmost window...")
            window_id, app_name = get_frontmost_window_id()
            
            if window_id:
                result = subprocess.run(
                    ["screencapture", "-x", "-o", "-l", str(window_id), "-t", "png", str(screenshot_path)],
                    capture_output=True,
                    timeout=5
                )
                
                if result.returncode == 0 and screenshot_path.exists() and screenshot_path.stat().st_size > 1000:
                    print(f"✓ Captured: {app_name}")
                    window_captured = True
        
        # If window capture didn't work, fall back to full screen
        if not window_captured:
            print(f"   📸 Falling back to full screen capture...")
            
            # Fallback to full screen
            result = subprocess.run(
                ["screencapture", "-x", "-t", "png", str(screenshot_path)],
                capture_output=True,
                timeout=5
            )
        
        if result.returncode != 0:
            print(f"⚠ screencapture returned code {result.returncode}")
            if result.stderr:
                print(f"   Error: {result.stderr.decode()}")
            return None
        
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
        print("\n" + "="*60)
        print("🎯 PROCESSING...")
        print("="*60)
        
        if not audio_path:
            print("❌ No audio recorded, aborting...")
            return
        
        # Step 1: Transcribe audio
        message_text = transcribe_audio(audio_path)
        if not message_text:
            print("❌ Transcription failed, aborting...")
            return
        
        # Step 2: Check if we have a screenshot (captured earlier)
        if screenshot_path:
            print(f"📸 Using pre-captured screenshot: {screenshot_path}")
        else:
            print("⏭️  No screenshot (audio-only mode)")

        # Step 4: Find and switch to Perplexity tab
        global PERPLEXITY_WINDOW_HANDLE
        print("🔍 Looking for Perplexity tab...")
        
        current_handle = driver.current_window_handle
        perplexity_handle = None
        
        # First, check if current window is already Perplexity (avoid switching)
        try:
            if 'perplexity.ai' in driver.current_url:
                perplexity_handle = current_handle
                PERPLEXITY_WINDOW_HANDLE = perplexity_handle
                print(f"✓ Already on Perplexity tab")
                
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
                    print(f"✓ Switched to cached Perplexity tab")
                    
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
        
        # If still not found, search through all windows (this will activate them)
        if not perplexity_handle:
            print("   Searching all tabs (may briefly show other windows)...")
            for handle in driver.window_handles:
                try:
                    driver.switch_to.window(handle)
                    if 'perplexity.ai' in driver.current_url:
                        perplexity_handle = handle
                        PERPLEXITY_WINDOW_HANDLE = perplexity_handle
                        print(f"✓ Found Perplexity tab: {driver.current_url}")
                        break
                except:
                    continue
        
        if not perplexity_handle:
            print("❌ Could not find Perplexity tab!")
            print("   Please open perplexity.ai in Chrome")
            driver.switch_to.window(current_handle)
            return
        
        # Bring Chrome window to front at macOS level
        try:
            print("   Bringing Chrome to front...")
            subprocess.run([
                "osascript", "-e",
                'tell application "Google Chrome" to activate'
            ], check=False, capture_output=True, timeout=2)
            time.sleep(0.5)  # Give time for window to come forward
            print("   ✓ Chrome activated")
        except Exception as e:
            print(f"   ⚠ Could not activate Chrome window: {e}")
        
        # Now find the chat input
        print("🔍 Looking for chat input...")
        try:
            chat_input = wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true' and @role='textbox']"))
            )
            print("✓ Found chat input!")
        except Exception as e:
            print(f"❌ Failed to find chat input: {e}")
            print(f"   Page title: {driver.title}")
            return

        # Step 5: Type the transcribed message FIRST
        print(f"⌨️  Typing message: \"{message_text}\"")
        chat_input.click()
        time.sleep(0.5)
        chat_input.send_keys(message_text)
        print("✓ Message typed!")
        
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
                
                # Wait for upload to actually complete
                print("   Waiting for upload to complete...")
                
                upload_complete = False
                max_wait = 15  # Wait up to 15 seconds for upload
                
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
                            print(f"✓ Upload complete! Found visual indicator")
                            upload_complete = True
                            break
                        
                        # Show progress every 3 seconds
                        if i > 0 and i % 3 == 0:
                            print(f"   Still uploading... {i}s")
                        
                        time.sleep(1)
                        
                    except Exception as e:
                        pass
                
                if not upload_complete:
                    print(f"⚠ No visual confirmation after {max_wait}s")
                    print("   Giving extra time for upload to complete...")
                    # Wait extra time to be safe with large files
                    time.sleep(5)
                else:
                    # Extra second after confirmation
                    time.sleep(2)
                
                print("✓ Upload complete, proceeding with send...")
        
        # Wait a moment for any UI updates
        time.sleep(1)

        # Step 7: Verify we have content to send
        print("✓ Ready to send")
        time.sleep(1)

        # Step 8: Click send
        print("🔍 Looking for send button...")
        send_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Submit']"))
        )
        print("🚀 Clicking send...")
        time.sleep(0.5)  # Brief pause before clicking
        send_button.click()
        print("✓ Send button clicked!")

        # Wait a bit
        print("✓ Message sent! Waiting 3 seconds...")
        time.sleep(3)

        print("✅ Done! Check the browser to see the response from Perplexity.")
        print("="*60)
        print(f"🦶 Ready for next query (Left pedal = screenshot, Right pedal = audio only)...\n")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"🦶 Try again (Left pedal = screenshot, Right pedal = audio only)...\n")
    
    finally:
        # Clean up temporary files
        if audio_path and Path(audio_path).exists():
            try:
                Path(audio_path).unlink()
                print(f"🗑️  Cleaned up audio file")
            except Exception as e:
                print(f"⚠ Could not delete audio file: {e}")
        
        # Clean up screenshot
        if screenshot_path and Path(screenshot_path).exists():
            try:
                Path(screenshot_path).unlink()
                print(f"🗑️  Cleaned up screenshot file")
            except Exception as e:
                print(f"⚠ Could not delete screenshot file: {e}")


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
    try:
        # Check for screenshot + audio trigger
        if check_key_match(key, TRIGGER_KEY_WITH_SCREENSHOT):
            if not recorder.is_recording:
                # IMMEDIATELY capture window ID and bounds before anything else!
                window_id, app_name, bounds = get_frontmost_window_id()
                
                recorder.capture_screenshot = True
                key_display = TRIGGER_KEY_WITH_SCREENSHOT.replace('_r', ' (Right)').replace('_', ' ').title()
                print("\n" + "="*60)
                print(f"🦶 {key_display} PRESSED - Capturing {app_name or 'window'} + recording...")
                print("="*60)
                # Pass the pre-captured window ID and bounds
                recorder.start_recording(take_screenshot=True, window_id=window_id, app_name=app_name, window_bounds=bounds)
        
        # Check for audio-only trigger
        elif check_key_match(key, TRIGGER_KEY_AUDIO_ONLY):
            if not recorder.is_recording:
                recorder.capture_screenshot = False
                key_display = TRIGGER_KEY_AUDIO_ONLY.replace('_r', ' (Right)').replace('_', ' ').title()
                print("\n" + "="*60)
                print(f"🦶 {key_display} PRESSED - Recording audio only...")
                print("="*60)
                recorder.start_recording(take_screenshot=False)
    except Exception as e:
        print(f"Error in key press handler: {e}")

def on_release(key, recorder, driver, wait):
    """Handle key release events - stop recording and process."""
    try:
        # Check if either trigger key was released
        if check_key_match(key, TRIGGER_KEY_WITH_SCREENSHOT) or check_key_match(key, TRIGGER_KEY_AUDIO_ONLY):
            if recorder.is_recording:
                # Get the pre-captured screenshot path (may be None)
                screenshot_path = recorder.screenshot_path
                audio_path = recorder.stop_recording()
                if audio_path:
                    send_to_perplexity(driver, wait, audio_path, screenshot_path)
    except Exception as e:
        print(f"Error in key release handler: {e}")


# ============ CONNECT TO CHROME ============
# FIRST: Open Chrome with: /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome_dev_profile"
# Then navigate to perplexity.ai and log in
print("="*60)
print("🚀 macPerplex - Voice AI for Perplexity")
print("="*60)

# Check if OpenAI API key is set
if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("your-"):
    print("\n❌ ERROR: OpenAI API key not set!")
    print("Please edit config.py and set your OpenAI API key.")
    print("Get one from: https://platform.openai.com/api-keys")
    exit(1)

# Check macOS permissions
check_permissions()

print("🔗 Checking for Chrome with remote debugging...")

# First, check if Chrome is running in debug mode
def check_chrome_debug_mode():
    """Check if Chrome is running with remote debugging on port 9222."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('127.0.0.1', 9222))
    sock.close()
    return result == 0

if not check_chrome_debug_mode():
    print("\n❌ ERROR: Chrome is not running in debug mode!")
    print("\n📋 To start Chrome with remote debugging:")
    print("   1. Close all Chrome windows")
    print("   2. Run this command:")
    print("      /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222 --user-data-dir=\"/tmp/chrome_dev_profile\"")
    print("   3. Navigate to https://www.perplexity.ai and log in")
    print("   4. Run macPerplex again")
    print("\n💡 Tip: Keep that Chrome window open while using macPerplex")
    exit(1)

print("✓ Chrome debug port detected")
print("🔗 Connecting to Chrome...")

chrome_options = Options()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

try:
    driver = webdriver.Chrome(options=chrome_options)
    print(f"✓ Connected! Current URL: {driver.current_url}")
    wait = WebDriverWait(driver, 20)
    
    # Create audio recorder
    recorder = AudioRecorder()
    
    # Format the key names nicely for display
    key1_display = TRIGGER_KEY_WITH_SCREENSHOT.replace('_r', ' (Right)').replace('_', ' ').title()
    key2_display = TRIGGER_KEY_AUDIO_ONLY.replace('_r', ' (Right)').replace('_', ' ').title()
    
    print("\n" + "="*60)
    print("✅ READY! Two modes:")
    print("")
    print(f"   🖼️  {key1_display} - Audio + Screenshot")
    print("      Hold, speak, release → sends with image")
    print("")
    print(f"   🎤 {key2_display} - Audio Only")
    print("      Hold, speak, release → sends without image")
    print("")
    print("   💡 Using modifier keys or F-keys prevents beeping!")
    print("   Press Ctrl+C to exit")
    print("="*60 + "\n")
    
    # Set up keyboard listener with both press and release handlers
    with keyboard.Listener(
        on_press=lambda key: on_press(key, recorder),
        on_release=lambda key: on_release(key, recorder, driver, wait)
    ) as listener:
        listener.join()
        
except KeyboardInterrupt:
    print("\n\n🛑 Shutting down...")
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\n💡 Troubleshooting:")
    print("   - Make sure Chrome is still running")
    print("   - Ensure you're on https://www.perplexity.ai")
    print("   - Try restarting Chrome in debug mode")
    print("\nSee README.md for full setup instructions")

