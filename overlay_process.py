#!/usr/bin/env python3
"""
PySide6 overlay for region selection.
Run as a subprocess from macPerplex.py.
Writes selected region to the file passed as first argument.

Creates separate overlay windows for each monitor to ensure proper coverage.
"""

import sys

def main():
    result_file = sys.argv[1] if len(sys.argv) > 1 else None
    
    try:
        from PySide6.QtWidgets import QApplication, QWidget, QLabel, QRubberBand
        from PySide6.QtCore import Qt, QRect, QPoint, QSize
        from PySide6.QtGui import QPainter, QColor, QCursor, QGuiApplication
    except ImportError:
        print("NO_PYSIDE6", file=sys.stderr)
        sys.exit(1)

    class OverlayWidget(QWidget):
        """Overlay for a single screen."""
        def __init__(self, screen, is_primary=False, coordinator=None):
            super().__init__()
            self.coordinator = coordinator
            self.is_primary = is_primary
            self.origin = QPoint()
            self.rubberBand = None
            self.screen_geometry = screen.geometry()
            
            # Window flags - frameless, on top, tool window
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            
            # Cover this screen
            self.setGeometry(self.screen_geometry)
            
            # Rubber band for selection
            self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
            
            # Set cursor
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            self.rubberBand.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            
            # Instructions (only on primary screen)
            if is_primary:
                self.label = QLabel("Drag to select region • ESC to cancel", self)
                self.label.setStyleSheet(
                    "color: white; font-size: 18px; background: rgba(0,0,0,0.8); "
                    "padding: 12px 20px; border-radius: 8px;"
                )
                self.label.adjustSize()
                self.label.move(self.width() // 2 - self.label.width() // 2, 40)
                self.label.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        
        def paintEvent(self, event):
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        
        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self.origin = event.position().toPoint()
                self.rubberBand.setGeometry(QRect(self.origin, QSize()))
                self.rubberBand.show()
                # Tell coordinator this screen is active
                if self.coordinator:
                    self.coordinator.set_active_overlay(self)
        
        def mouseMoveEvent(self, event):
            QApplication.changeOverrideCursor(QCursor(Qt.CursorShape.CrossCursor))
            
            if self.rubberBand and self.rubberBand.isVisible():
                self.rubberBand.setGeometry(
                    QRect(self.origin, event.position().toPoint()).normalized()
                )
        
        def mouseReleaseEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton and self.rubberBand:
                self.rubberBand.hide()
                
                rect = QRect(self.origin, event.position().toPoint()).normalized()
                # Convert to global screen coordinates
                global_origin = self.mapToGlobal(rect.topLeft())
                x, y = global_origin.x(), global_origin.y()
                w, h = rect.width(), rect.height()
                
                if self.coordinator:
                    self.coordinator.finish_selection(x, y, w, h)
        
        def keyPressEvent(self, event):
            if event.key() == Qt.Key.Key_Escape:
                if self.coordinator:
                    self.coordinator.cancel()

    class OverlayCoordinator:
        """Coordinates multiple overlay windows across screens."""
        def __init__(self, result_file):
            self.result_file = result_file
            self.overlays = []
            self.active_overlay = None
            
        def create_overlays(self):
            screens = QGuiApplication.screens()
            primary = QGuiApplication.primaryScreen()
            
            for screen in screens:
                is_primary = (screen == primary)
                overlay = OverlayWidget(screen, is_primary=is_primary, coordinator=self)
                self.overlays.append(overlay)
                overlay.show()
                overlay.activateWindow()
                overlay.raise_()
            
            # Don't grab mouse - let each overlay receive its own events
        
        def set_active_overlay(self, overlay):
            self.active_overlay = overlay
        
        def finish_selection(self, x, y, w, h):
            # Write result if selection is large enough
            if w >= 50 and h >= 50 and self.result_file:
                try:
                    with open(self.result_file, "w") as f:
                        f.write(f"{x},{y},{w},{h}")
                except:
                    pass
            
            self.close_all()
        
        def cancel(self):
            self.close_all()
        
        def close_all(self):
            for o in self.overlays:
                o.close()
            QApplication.quit()

    app = QApplication(sys.argv)
    app.setOverrideCursor(QCursor(Qt.CursorShape.CrossCursor))
    
    coordinator = OverlayCoordinator(result_file)
    coordinator.create_overlays()
    
    app.exec()
    app.restoreOverrideCursor()


if __name__ == "__main__":
    main()
