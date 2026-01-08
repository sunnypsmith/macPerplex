#!/usr/bin/env python3
"""
Test script to experiment with screen overlay approaches on macOS.
Run this standalone to test different overlay methods.
"""

import sys
import time

def test_pyside6_overlay():
    """Test PySide6 overlay - runs as main application."""
    print("\n=== Testing PySide6 Overlay ===")
    try:
        from PySide6.QtWidgets import QApplication, QWidget, QLabel, QRubberBand
        from PySide6.QtCore import Qt, QRect, QPoint, QSize
        from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QGuiApplication
        
        class OverlayWidget(QWidget):
            def __init__(self):
                super().__init__()
                self.origin = QPoint()
                self.rubberBand = None
                self.final_rect = None
                
                # Window flags
                self.setWindowFlags(
                    Qt.WindowType.FramelessWindowHint |
                    Qt.WindowType.WindowStaysOnTopHint |
                    Qt.WindowType.Tool
                )
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                
                # Cover all screens
                screens = QGuiApplication.screens()
                if screens:
                    min_x = min(s.geometry().x() for s in screens)
                    min_y = min(s.geometry().y() for s in screens)
                    max_x = max(s.geometry().x() + s.geometry().width() for s in screens)
                    max_y = max(s.geometry().y() + s.geometry().height() for s in screens)
                    
                    print(f"   Screens: {len(screens)}")
                    for i, s in enumerate(screens):
                        g = s.geometry()
                        print(f"     Screen {i}: {g.x()}, {g.y()}, {g.width()}x{g.height()}")
                    print(f"   Combined: {min_x}, {min_y}, {max_x - min_x}x{max_y - min_y}")
                    
                    self.setGeometry(min_x, min_y, max_x - min_x, max_y - min_y)
                    self.screen_offset = QPoint(min_x, min_y)
                
                # Create rubber band for selection rectangle
                self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
                
                self.show()
                self.activateWindow()
                self.raise_()
                self.grabMouse()  # Grab all mouse events
                
                # Instructions label
                self.label = QLabel("Click and drag to select • ESC to close", self)
                self.label.setStyleSheet(
                    "color: white; font-size: 20px; background: rgba(0,0,0,0.8); "
                    "padding: 15px; border-radius: 8px;"
                )
                self.label.adjustSize()
                self.label.move(self.width() // 2 - self.label.width() // 2, 50)
                self.label.setCursor(QCursor(Qt.CursorShape.CrossCursor))
                
                # Set cursor on self too
                self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
                
                # Also set on rubberband
                self.rubberBand.setCursor(QCursor(Qt.CursorShape.CrossCursor))
                
                print("   ✓ Overlay window created")
            
            def enterEvent(self, event):
                # Force crosshair when entering widget
                QApplication.setOverrideCursor(QCursor(Qt.CursorShape.CrossCursor))
            
            def leaveEvent(self, event):
                # Keep crosshair even when "leaving" (shouldn't happen with grabMouse)
                QApplication.setOverrideCursor(QCursor(Qt.CursorShape.CrossCursor))
            
            def paintEvent(self, event):
                painter = QPainter(self)
                # Dark semi-transparent overlay
                painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
            
            def mousePressEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton:
                    self.origin = event.position().toPoint()
                    self.rubberBand.setGeometry(QRect(self.origin, QSize()))
                    self.rubberBand.show()
                    global_pos = event.globalPosition().toPoint()
                    print(f"   Mouse down at: {global_pos.x()}, {global_pos.y()}")
            
            def mouseMoveEvent(self, event):
                # Keep forcing crosshair cursor
                QApplication.changeOverrideCursor(QCursor(Qt.CursorShape.CrossCursor))
                
                if self.rubberBand and self.rubberBand.isVisible():
                    self.rubberBand.setGeometry(
                        QRect(self.origin, event.position().toPoint()).normalized()
                    )
            
            def mouseReleaseEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton and self.rubberBand:
                    self.rubberBand.hide()
                    self.releaseMouse()  # Release mouse grab
                    
                    # Get final rectangle in screen coordinates
                    rect = QRect(self.origin, event.position().toPoint()).normalized()
                    
                    # Convert to global screen coordinates
                    global_origin = self.mapToGlobal(rect.topLeft())
                    x, y = global_origin.x(), global_origin.y()
                    w, h = rect.width(), rect.height()
                    
                    self.final_rect = (x, y, w, h)
                    print(f"   ✓ Selected region: {x}, {y}, {w}x{h}")
                    
                    self.close()
                    QApplication.quit()
            
            def keyPressEvent(self, event):
                if event.key() == Qt.Key.Key_Escape:
                    print("   ESC pressed, closing")
                    self.releaseMouse()  # Release mouse grab
                    self.close()
                    QApplication.quit()
        
        print("   Starting Qt application...")
        app = QApplication(sys.argv)
        
        # Set application-wide cursor
        app.setOverrideCursor(QCursor(Qt.CursorShape.CrossCursor))
        
        overlay = OverlayWidget()
        result = app.exec()
        
        # Restore cursor
        app.restoreOverrideCursor()
        
        print(f"   Qt app finished with code: {result}")
        return True
        
    except ImportError as e:
        print(f"   ✗ PySide6 not installed: {e}")
        return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tkinter_overlay():
    """Test Tkinter overlay."""
    print("\n=== Testing Tkinter Overlay ===")
    try:
        import tkinter as tk
        
        print("   Creating Tk root...")
        root = tk.Tk()
        
        # Get screen size
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        print(f"   Screen: {screen_width}x{screen_height}")
        
        # Configure window
        root.overrideredirect(True)  # Remove window decorations
        root.attributes('-topmost', True)
        root.attributes('-alpha', 0.3)
        root.geometry(f"{screen_width}x{screen_height}+0+0")
        root.configure(bg='black')
        root.config(cursor='cross')
        
        # Selection variables
        start_x = start_y = 0
        rect_id = None
        
        canvas = tk.Canvas(root, width=screen_width, height=screen_height, 
                          bg='black', highlightthickness=0)
        canvas.pack()
        
        # Instructions
        canvas.create_text(screen_width//2, 50, 
                          text="Click and drag to select • ESC to close",
                          fill='white', font=('Helvetica', 20))
        
        def on_press(event):
            nonlocal start_x, start_y, rect_id
            start_x, start_y = event.x, event.y
            print(f"   Mouse down at: {start_x}, {start_y}")
            if rect_id:
                canvas.delete(rect_id)
            rect_id = canvas.create_rectangle(start_x, start_y, start_x, start_y,
                                             outline='#00AAFF', width=3)
        
        def on_drag(event):
            nonlocal rect_id
            if rect_id:
                canvas.coords(rect_id, start_x, start_y, event.x, event.y)
        
        def on_release(event):
            x1, y1 = min(start_x, event.x), min(start_y, event.y)
            w, h = abs(event.x - start_x), abs(event.y - start_y)
            print(f"   ✓ Selected region: {x1}, {y1}, {w}x{h}")
            root.destroy()
        
        def on_escape(event):
            print("   ESC pressed, closing")
            root.destroy()
        
        canvas.bind('<Button-1>', on_press)
        canvas.bind('<B1-Motion>', on_drag)
        canvas.bind('<ButtonRelease-1>', on_release)
        root.bind('<Escape>', on_escape)
        
        print("   ✓ Tkinter window created, starting mainloop...")
        root.mainloop()
        print("   Tkinter finished")
        return True
        
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_native_screencapture():
    """Test using macOS native screencapture -i (interactive)."""
    print("\n=== Testing Native screencapture -i ===")
    import subprocess
    import tempfile
    
    output_file = tempfile.mktemp(suffix='.png')
    print(f"   Output file: {output_file}")
    print("   Running screencapture -i (select a region)...")
    
    try:
        result = subprocess.run(
            ['screencapture', '-i', output_file],
            timeout=30
        )
        
        import os
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            size = os.path.getsize(output_file)
            print(f"   ✓ Screenshot saved! Size: {size} bytes")
            os.unlink(output_file)
            return True
        else:
            print("   ✗ No screenshot (cancelled?)")
            return False
            
    except subprocess.TimeoutExpired:
        print("   ✗ Timeout")
        return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("macOS Overlay Test Script")
    print("=" * 60)
    print("\nChoose a test:")
    print("  1. PySide6 overlay (Qt)")
    print("  2. Tkinter overlay")
    print("  3. Native screencapture -i")
    print("  4. Run all tests")
    print()
    
    choice = input("Enter choice (1-4): ").strip()
    
    if choice == '1':
        test_pyside6_overlay()
    elif choice == '2':
        test_tkinter_overlay()
    elif choice == '3':
        test_native_screencapture()
    elif choice == '4':
        test_pyside6_overlay()
        time.sleep(1)
        test_tkinter_overlay()
        time.sleep(1)
        test_native_screencapture()
    else:
        print("Invalid choice")

