#!/usr/bin/env python3
"""
PySide6 overlay for region selection.
Run as a subprocess from macPerplex.py.
Writes selected region to the file passed as first argument.
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
        def __init__(self):
            super().__init__()
            self.origin = QPoint()
            self.rubberBand = None
            self.result_file = result_file
            
            # Window flags - frameless, on top, tool window
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
                self.setGeometry(min_x, min_y, max_x - min_x, max_y - min_y)
            
            # Rubber band for selection
            self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
            
            # Show and activate
            self.show()
            self.activateWindow()
            self.raise_()
            self.grabMouse()
            
            # Set cursor
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            self.rubberBand.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            
            # Instructions
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
                self.releaseMouse()
                
                rect = QRect(self.origin, event.position().toPoint()).normalized()
                global_origin = self.mapToGlobal(rect.topLeft())
                x, y = global_origin.x(), global_origin.y()
                w, h = rect.width(), rect.height()
                
                # Write result if selection is large enough
                if w >= 50 and h >= 50 and self.result_file:
                    try:
                        with open(self.result_file, "w") as f:
                            f.write(f"{x},{y},{w},{h}")
                    except:
                        pass
                
                self.close()
                QApplication.quit()
        
        def keyPressEvent(self, event):
            if event.key() == Qt.Key.Key_Escape:
                self.releaseMouse()
                self.close()
                QApplication.quit()

    app = QApplication(sys.argv)
    app.setOverrideCursor(QCursor(Qt.CursorShape.CrossCursor))
    overlay = OverlayWidget()
    app.exec()
    app.restoreOverrideCursor()


if __name__ == "__main__":
    main()

