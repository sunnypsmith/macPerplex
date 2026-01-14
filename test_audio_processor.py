#!/usr/bin/env python3
"""
Test script for audio_processor module.

Tests audio recording, transcription, and emotion analysis in isolation
before integrating into main macPerplex application.

Usage:
    python3 test_audio_processor.py

The script will:
1. Record 5 seconds of audio
2. Transcribe with Whisper
3. Analyze emotion with Hume.ai (if enabled)
4. Display results
"""

import time
from audio_processor import AudioProcessor, play_double_beep, play_stop_beep
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pynput import keyboard

console = Console()

# Global flag for recording control
is_recording = False
recording_started = False

def test_audio_recording():
    """Test audio recording and processing."""
    
    console.print(Panel.fit(
        "[bold cyan]🧪 Audio Processor Test[/bold cyan]\n[dim]Testing recording, transcription & emotion analysis[/dim]",
        border_style="cyan"
    ))
    
    # Create processor
    processor = AudioProcessor()
    
    # Test 1: Quick beep test
    console.print("\n[bold]Test 1: Audio Feedback Beeps[/bold]")
    console.print("[dim]Playing double beep...[/dim]")
    play_double_beep()
    time.sleep(0.5)
    console.print("[dim]Playing stop beep...[/dim]")
    play_stop_beep()
    console.print("[green]✓ Beeps work![/green]")
    
    # Test 2: Recording with keyboard control
    console.print("\n[bold]Test 2: Audio Recording[/bold]")
    console.print("\n[bold yellow]📋 Instructions:[/bold yellow]")
    console.print("  [cyan]Press and HOLD SPACE[/cyan] to start recording")
    console.print("  [cyan]Release SPACE[/cyan] to stop recording and process")
    console.print("  [dim]Say something with emotion (frustrated, excited, confused, etc.)[/dim]")
    console.print("\n[bold]Ready when you are...[/bold]\n")
    
    global is_recording, recording_started
    result = None
    
    def on_press(key):
        global is_recording, recording_started
        try:
            if key == keyboard.Key.space and not is_recording:
                is_recording = True
                recording_started = True
                console.print("\n[bold green]🎤 RECORDING...[/bold green] [dim](release SPACE to stop)[/dim]")
                play_double_beep()
                processor.start_recording(take_screenshot=False)
        except:
            pass
    
    def on_release(key):
        global is_recording
        try:
            if key == keyboard.Key.space and is_recording:
                is_recording = False
                play_stop_beep()
                console.print("\n[bold]⏸️  Processing audio...[/bold]")
                return False  # Stop listener
            elif key == keyboard.Key.esc:
                console.print("\n[yellow]Test cancelled[/yellow]")
                return False  # Stop listener
        except:
            pass
    
    # Start keyboard listener
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
    
    # Process if recording was done
    if recording_started:
        result = processor.stop_recording_and_process()
    else:
        console.print("[yellow]No recording made[/yellow]")
        return
    
    # Display results
    if result:
        console.print("\n" + "="*60)
        console.print("[bold green]✅ SUCCESS![/bold green]")
        console.print("="*60)
        
        # Create results table
        table = Table(title="Audio Processing Results", show_header=True, header_style="bold magenta")
        table.add_column("Field", style="cyan", width=20)
        table.add_column("Value", style="white", width=50)
        
        table.add_row("Audio File", result['audio_path'])
        table.add_row("Transcript", f'"{result["transcript"]}"')
        
        if result['emotions']:
            emotions_str = ', '.join(result['emotions'])
            table.add_row("Top Emotions", emotions_str)
            
            if result['emotion_scores']:
                scores_str = '\n'.join([f"{k}: {v:.2f}" for k, v in result['emotion_scores'].items()])
                table.add_row("Emotion Scores", scores_str)
        else:
            table.add_row("Emotions", "[dim]Not analyzed or disabled[/dim]")
        
        console.print(table)
        
        # Show what would be sent to Perplexity
        console.print("\n[bold]📝 What Would Be Sent to Perplexity:[/bold]")
        
        if result['emotions']:
            emotion_context = f"[User emotion: {', '.join(result['emotions'])}] "
            full_message = emotion_context + result['transcript']
            console.print(Panel(full_message, border_style="green", title="With Emotion Context"))
        else:
            console.print(Panel(result['transcript'], border_style="blue", title="Without Emotion Context"))
        
        # Cleanup
        try:
            import os
            os.unlink(result['audio_path'])
            console.print("\n[dim]🗑️  Cleaned up test audio file[/dim]")
        except:
            pass
    else:
        console.print("\n[bold red]❌ FAILED[/bold red]")
        console.print("Check errors above for details")
    
    console.print("\n" + "="*60)
    console.print("[bold]Test complete![/bold]")
    console.print("="*60)
    console.print("\nIf emotion analysis failed:")
    console.print("  - Check HUME_API_KEY in config.py")
    console.print("  - Verify ENABLE_EMOTION_ANALYSIS = True")
    console.print("  - Check Hume.ai API status/credits")
    console.print("\nIf transcription failed:")
    console.print("  - Check OPENAI_API_KEY in config.py")
    console.print("  - Verify microphone permissions")


if __name__ == "__main__":
    try:
        test_audio_recording()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Test cancelled[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Test error:[/bold red] {e}")
        import traceback
        traceback.print_exc()
