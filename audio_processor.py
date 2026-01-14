"""
Audio processing module for macPerplex.

Handles:
- Audio recording with live visualization
- Audio normalization
- Speech-to-text transcription (OpenAI Whisper)
- Emotion analysis (Hume.ai)
- Audio feedback beeps

Uses asyncio for parallel API calls to minimize latency.
"""

import time
import asyncio
import numpy as np
import sounddevice as sd
import wave
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn

# Import configuration
from config import (
    OPENAI_API_KEY,
    OPENAI_STT_MODEL,
    TRANSCRIPTION_LANGUAGE,
    HUME_API_KEY,
    ENABLE_EMOTION_ANALYSIS,
    EMOTION_TOP_N,
    EMOTION_MIN_SCORE,
    AUDIO_SAMPLE_RATE,
    AUDIO_CHANNELS,
    MAX_RECORDING_DURATION
)

console = Console()


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
    except Exception:
        pass  # Don't let beep failures break the app


def play_double_beep():
    """Play double beep for screenshot + audio mode."""
    try:
        play_beep(800, 0.08, 0.25)
        time.sleep(0.05)
        play_beep(1000, 0.08, 0.25)
    except Exception:
        pass


def play_start_beep():
    """Play single beep for audio-only mode start."""
    play_beep(900, 0.1, 0.3)


def play_stop_beep():
    """Play beep when recording stops."""
    play_beep(700, 0.12, 0.3)


def play_submit_beep():
    """Play beep when message is submitted."""
    play_beep(1200, 0.15, 0.25)


# ============ AUDIO RECORDING ============

class AudioRecorder:
    """Push-to-talk audio recorder with live visualization."""
    
    def __init__(self):
        self.is_recording = False
        self.audio_chunks = []
        self.stream = None
        self.capture_screenshot = True
        self.screenshot_path = None
        self.live_display = None
        self.start_time = None
    
    def start_recording(self, take_screenshot=False, window_id=None, app_name=None, window_bounds=None):
        """Start recording audio. Optionally capture screenshot of specified window."""
        if self.is_recording:
            return
        
        self.is_recording = True
        self.audio_chunks = []
        self.screenshot_path = None
        
        # Screenshot capture handled externally now
        if take_screenshot:
            console.print(f"[cyan]📸 Capturing screenshot of {app_name or 'window'}...[/cyan]")
            # Import here to avoid circular dependency
            from macPerplex import capture_screenshot_func
            self.screenshot_path = capture_screenshot_func(window_id, app_name, window_bounds)
            if self.screenshot_path:
                console.print("[green]✓ Screenshot captured![/green]")
            else:
                console.print("[yellow]⚠ Screenshot failed, continuing with audio only[/yellow]")
        
        mode = "with screenshot" if self.capture_screenshot else "audio only"
        console.print(f"[bold]🎤 Recording {mode}...[/bold] [dim](release pedal to stop)[/dim]")
        
        self.start_time = time.time()
        
        def audio_callback(indata, frames, time_info, status):
            # Check if max recording duration exceeded
            if self.start_time and (time.time() - self.start_time) > MAX_RECORDING_DURATION:
                console.print(f"\n[yellow]⚠ Max recording duration ({MAX_RECORDING_DURATION}s) reached, stopping...[/yellow]")
                raise sd.CallbackAbort()
            
            # Calculate RMS (volume level)
            rms = np.sqrt(np.mean(indata**2))
            
            # Store audio data
            self.audio_chunks.append(indata.copy())
            
            # Update live display with audio visualization
            if self.live_display and self.start_time:
                elapsed = time.time() - self.start_time
                
                # Create visual bar based on audio level
                bar_length = int(rms * 50)
                bar_length = min(bar_length, 40)
                
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
                except Exception:
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
            
            # Clean up live display
            if self.live_display:
                try:
                    self.live_display.stop()
                except Exception:
                    pass
                self.live_display = None
            
            # Clean up stream if it was created but failed to start
            if self.stream:
                try:
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
    
    def stop_recording(self):
        """Stop recording and save audio file. Returns audio file path or None."""
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
            
            # Normalize audio for better Whisper transcription
            peak = np.max(np.abs(audio_data))
            if peak > 0:
                if peak > 0.05:
                    scaling_factor = 0.9 / peak
                    scaling_factor = min(scaling_factor, 10.0)
                    audio_data = audio_data * scaling_factor
                    console.print(f"[dim]   🔊 Normalized audio (boost: {scaling_factor:.1f}x, peak: {peak:.2f})[/dim]")
                else:
                    console.print(f"[dim]   🔇 Audio too quiet to normalize (peak: {peak:.2f})[/dim]")
            
            # Save to WAV file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_path = Path(f"/tmp/perplexity_audio_{timestamp}.wav")
            
            # Convert to int16 for WAV
            audio_int16 = (audio_data * 32767).astype(np.int16)
            
            with wave.open(str(audio_path), 'wb') as wf:
                wf.setnchannels(AUDIO_CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(AUDIO_SAMPLE_RATE)
                wf.writeframes(audio_int16.tobytes())
            
            duration = len(audio_data) / AUDIO_SAMPLE_RATE
            console.print(f"[green]✓ Audio saved:[/green] [dim]{audio_path}[/dim] [cyan]({duration:.1f} seconds)[/cyan]")
            return str(audio_path)
            
        except Exception as e:
            console.print(f"[bold red]❌ Error stopping recording:[/bold red] {e}")
            return None


# ============ SPEECH-TO-TEXT ============

async def transcribe_audio_async(audio_path):
    """Transcribe audio using OpenAI Whisper API (async)."""
    try:
        # Run in thread pool since OpenAI client is synchronous
        loop = asyncio.get_event_loop()
        
        def _transcribe():
            client = OpenAI(api_key=OPENAI_API_KEY)
            with open(audio_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model=OPENAI_STT_MODEL,
                    file=audio_file,
                    language=TRANSCRIPTION_LANGUAGE,
                    response_format="text"
                )
            return transcript.strip()
        
        transcript = await loop.run_in_executor(None, _transcribe)
        return transcript
        
    except Exception as e:
        console.print(f"[bold red]❌ Error transcribing audio:[/bold red] {e}")
        return None


def transcribe_audio(audio_path):
    """Transcribe audio using OpenAI Whisper API (synchronous wrapper)."""
    return asyncio.run(transcribe_audio_async(audio_path))


# ============ EMOTION ANALYSIS ============

async def analyze_emotion_async(audio_path):
    """
    Analyze voice emotion using Hume.ai Prosody model (async).
    
    Returns dict with top emotions or None if disabled/failed:
    {
        'top_emotions': ['frustrated', 'confused', 'focused'],
        'scores': {'frustrated': 0.82, 'confused': 0.61, 'focused': 0.45}
    }
    """
    if not ENABLE_EMOTION_ANALYSIS:
        return None
    
    if not HUME_API_KEY or HUME_API_KEY.startswith("your-"):
        return None
    
    try:
        # Hume.ai API integration (run in thread pool since requests is synchronous)
        import requests
        loop = asyncio.get_event_loop()
        
        def _submit_job():
            with open(audio_path, 'rb') as audio_file:
                files = {'file': audio_file}
                json_data = {
                    'models': {
                        'prosody': {}
                    }
                }
                
                response = requests.post(
                    'https://api.hume.ai/v0/batch/jobs',
                    headers={'X-Hume-Api-Key': HUME_API_KEY},
                    files=files,
                    data={'json': str(json_data).replace("'", '"')}
                )
                
                if response.status_code != 200:
                    return None
                
                return response.json()['job_id']
        
        def _poll_results(job_id):
            max_wait = 10
            for i in range(max_wait):
                time.sleep(0.5)
                
                status_response = requests.get(
                    f'https://api.hume.ai/v0/batch/jobs/{job_id}',
                    headers={'X-Hume-Api-Key': HUME_API_KEY}
                )
                
                if status_response.status_code == 200:
                    job_status = status_response.json()['state']['status']
                    
                    if job_status == 'COMPLETED':
                        pred_response = requests.get(
                            f'https://api.hume.ai/v0/batch/jobs/{job_id}/predictions',
                            headers={'X-Hume-Api-Key': HUME_API_KEY}
                        )
                        
                        if pred_response.status_code == 200:
                            predictions = pred_response.json()
                            
                            if predictions and len(predictions) > 0:
                                prosody_predictions = predictions[0]['results']['predictions'][0]['models']['prosody']['grouped_predictions'][0]['predictions'][0]['emotions']
                                sorted_emotions = sorted(prosody_predictions, key=lambda x: x['score'], reverse=True)
                                
                                top_emotions = []
                                scores = {}
                                
                                for emotion in sorted_emotions:
                                    if len(top_emotions) >= EMOTION_TOP_N:
                                        break
                                    if emotion['score'] >= EMOTION_MIN_SCORE:
                                        emotion_name = emotion['name']
                                        emotion_score = emotion['score']
                                        top_emotions.append(emotion_name)
                                        scores[emotion_name] = emotion_score
                                
                                if top_emotions:
                                    return {
                                        'top_emotions': top_emotions,
                                        'scores': scores
                                    }
                        return None
                    
                    elif job_status == 'FAILED':
                        return None
            
            return None
        
        # Submit job (blocking I/O, run in executor)
        job_id = await loop.run_in_executor(None, _submit_job)
        if not job_id:
            return None
        
        # Poll for results (blocking I/O, run in executor)
        result = await loop.run_in_executor(None, _poll_results, job_id)
        
        if result and result.get('top_emotions'):
            emotion_str = ', '.join(result['top_emotions'])
            console.print(f"[magenta]🎭 Detected emotions:[/magenta] [dim]{emotion_str}[/dim]")
        
        return result
            
    except Exception as e:
        console.print(f"[dim]⚠ Emotion analysis error: {e}[/dim]")
        return None


def analyze_emotion(audio_path):
    """Analyze emotion (synchronous wrapper)."""
    return asyncio.run(analyze_emotion_async(audio_path))


# ============ AUDIO PROCESSOR ============

class AudioProcessor:
    """
    High-level audio processing orchestrator.
    
    Handles recording, transcription, and optional emotion analysis.
    Returns combined results for use in main application.
    """
    
    def __init__(self):
        self.recorder = AudioRecorder()
    
    def start_recording(self, take_screenshot=False, window_id=None, app_name=None, window_bounds=None):
        """Start audio recording."""
        self.recorder.start_recording(take_screenshot, window_id, app_name, window_bounds)
    
    def stop_recording_and_process(self):
        """
        Stop recording and process audio (transcription + optional emotion analysis).
        
        Returns dict:
        {
            'audio_path': '/tmp/...',
            'transcript': 'what is this error',
            'emotions': ['frustrated', 'confused'],  # or None
            'emotion_scores': {'frustrated': 0.8}    # or None
        }
        """
        # Stop recording and get audio file
        audio_path = self.recorder.stop_recording()
        
        if not audio_path:
            return None
        
        # Run transcription and emotion analysis in parallel (future optimization)
        # For now, run sequentially
        
        transcript = transcribe_audio(audio_path)
        if not transcript:
            return None
        
        # Analyze emotion if enabled
        emotion_data = None
        if ENABLE_EMOTION_ANALYSIS:
            emotion_data = analyze_emotion(audio_path)
        
        return {
            'audio_path': audio_path,
            'transcript': transcript,
            'emotions': emotion_data['top_emotions'] if emotion_data else None,
            'emotion_scores': emotion_data['scores'] if emotion_data else None
        }
