from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtWidgets import QWidget


class StatusLamp(QWidget):
    """Colored circle indicator with blinking support for thermostat states."""

    _COLORS = {
        "Run":        "#4caf50",
        "Opvarmning": "#4caf50",
        "Advarsel":   "#ffc107",
        "Alarm":      "#f44336",
        "HW Alarm":   "#f44336",
    }
    _OFF_COLOR = "#444444"
    _DARK_COLOR = "#2a2a2a"
    _BLINKING = frozenset({"Opvarmning", "HW Alarm"})

    def __init__(self, diameter: int = 16, parent=None):
        super().__init__(parent)
        self._state = ""
        self._blink_on = True
        self._diameter = diameter
        size = diameter + 6
        self.setFixedSize(size, size)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)

    def setState(self, state: str):
        if self._state == state:
            return
        self._state = state
        if state not in self._BLINKING:
            self._blink_on = True
        self.update()

    def _tick(self):
        try:
            if self._state in self._BLINKING:
                self._blink_on = not self._blink_on
                self.update()
        except RuntimeError:
            # C++ widget already destroyed during shutdown — stop the timer
            self._timer.stop()
        except (KeyboardInterrupt, SystemExit):
            self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._state in self._BLINKING and not self._blink_on:
            fill = QColor(self._DARK_COLOR)
        else:
            fill = QColor(self._COLORS.get(self._state, self._OFF_COLOR))

        margin = 3
        painter.setBrush(fill)
        painter.setPen(QPen(QColor("#555555"), 1))
        painter.drawEllipse(margin, margin, self._diameter, self._diameter)
        painter.end()
