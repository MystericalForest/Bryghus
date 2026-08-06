import time
from collections import deque
from math import cos, radians, sin

import pyqtgraph as pg
from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSpinBox,
)

from models import SystemStatus, ThermostatData


class TempCard(QFrame):
    """Card widget with circular gauge, setpoint marker and HW fault badge."""

    _GAP_DEG = 28.0
    _SWEEP_DEG = 360.0 - _GAP_DEG
    _START_DEG = 90.0 + (_GAP_DEG / 2.0)

    def __init__(
        self,
        name: str,
        parent=None,
    ):
        super().__init__(parent)
        self._name = name
        self._temperature = None
        self._setpoint = 25.0
        self._warning_limit = 2.0
        self._alarm_limit = 5.0
        self._state = ""
        self._fault = False

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { border: 1px solid #3c3c3c; border-radius: 6px;"
            " background-color: #252525; }"
        )
        self.setMinimumWidth(170)
        self.setMinimumHeight(220)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(10, 8, 10, 8)

        name_lbl = QLabel(name)
        name_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet("border: none; background: transparent;")
        self._name_lbl = name_lbl

        self._badge_lbl = QLabel("")
        self._badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge_lbl.setVisible(False)

        layout.addWidget(name_lbl)
        layout.addWidget(self._badge_lbl)
        layout.addStretch()

    @staticmethod
    def _state_color(state: str, fault: bool) -> str:
        if fault or state == "HW Alarm":
            return "#f44336"
        if state == "Alarm":
            return "#f44336"
        if state == "Advarsel":
            return "#ffc107"
        if state in {"Run", "Opvarmning"}:
            return "#4caf50"
        return "#e0e0e0"

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def _value_to_angle(self, value: float) -> float:
        # Near-full circle with a bottom gap so start/end are unambiguous.
        normalized = (value / 120.0)
        return self._START_DEG + normalized * self._SWEEP_DEG

    def _zone_color(self, value: float) -> str:
        setpoint = self._setpoint
        warning = max(0.0, self._warning_limit)
        alarm = max(warning, self._alarm_limit)
        distance = abs(value - setpoint)
        if distance <= warning:
            return "#4caf50"
        if distance <= alarm:
            return "#ffc107"
        return "#f44336"

    def update_thermostat(self, data: ThermostatData):
        self._temperature = data.temperature
        self._setpoint = self._clamp(data.setpoint, 0.0, 120.0)
        self._warning_limit = data.warning_limit
        self._alarm_limit = data.alarm_limit
        self._state = data.state
        self._fault = bool(data.fault)

        # Top badge is intentionally unused; all state badges are rendered at gauge bottom.
        self._badge_lbl.setVisible(False)

        self.update()

    def sync_setpoint(self, value: float):
        clamped = self._clamp(value, 0.0, 120.0)
        if abs(self._setpoint - clamped) > 1e-9:
            self._setpoint = clamped
            self.update()

    def _is_hw_fault(self) -> bool:
        return self._fault or self._state == "HW Alarm"

    def _bottom_badge(self):
        if self._is_hw_fault():
            return ("HW-FEJL", "#f44336", "#b71c1c", "#ffffff")
        if self._state == "Alarm":
            return ("ALARM", "#f44336", "#b71c1c", "#ffffff")
        if self._state == "Advarsel":
            return ("ADVARSEL", "#ffc107", "#c79100", "#202020")
        return None

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        header_height = 52
        footer_height = 18
        content = self.rect().adjusted(12, header_height, -12, -footer_height)
        size = min(content.width(), content.height())
        if size < 80:
            painter.end()
            return

        cx = float(content.center().x())
        cy = float(content.center().y())
        outer = (size / 2) - 2
        ring_width = max(10.0, size * 0.06)
        inner = outer - ring_width
        tick_outer = outer + max(4.0, size * 0.025)
        tick_inner = inner - max(2.0, size * 0.015)

        # Ring colors follow setpoint warning/alarm limits on a shared 0-120 scale.
        span_rect = QRectF(cx - outer, cy - outer, outer * 2, outer * 2)
        steps = 220
        for i in range(steps):
            value = (i / steps) * 120.0
            color = self._zone_color(value)
            start = self._START_DEG + (i / steps) * self._SWEEP_DEG
            end = self._START_DEG + ((i + 1) / steps) * self._SWEEP_DEG
            painter.setPen(QPen(QColor(color), ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            painter.drawArc(span_rect, int(-start * 16), int(-(end - start) * 16))

        # Tick marks every 20°C.
        painter.setPen(QPen(QColor("#d0d0d0"), max(1.0, size * 0.006)))
        for value in range(0, 121, 20):
            angle = self._value_to_angle(float(value))
            a = radians(angle)
            x1 = cx + cos(a) * tick_inner
            y1 = cy + sin(a) * tick_inner
            x2 = cx + cos(a) * tick_outer
            y2 = cy + sin(a) * tick_outer
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Setpoint marker is always visible.
        sp_angle = radians(self._value_to_angle(self._setpoint))
        marker_outer = outer + max(6.0, size * 0.035)
        marker_inner = outer - max(8.0, size * 0.04)
        painter.setPen(QPen(QColor("#9be7ff"), max(2.0, size * 0.012), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(
            int(cx + cos(sp_angle) * marker_inner),
            int(cy + sin(sp_angle) * marker_inner),
            int(cx + cos(sp_angle) * marker_outer),
            int(cy + sin(sp_angle) * marker_outer),
        )

        # Temperature pointer hidden when sensor data is invalid.
        if (self._temperature is not None) and (not self._is_hw_fault()):
            temp = self._clamp(self._temperature, 0.0, 120.0)
            angle = radians(self._value_to_angle(temp))
            painter.setPen(QPen(QColor("#f5f5f5"), max(2.0, size * 0.012), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(
                int(cx),
                int(cy),
                int(cx + cos(angle) * (outer + max(2.0, size * 0.02))),
                int(cy + sin(angle) * (outer + max(2.0, size * 0.02))),
            )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1f1f1f"))
        center_radius = max(24.0, inner - size * 0.12)
        painter.drawEllipse(
            int(cx - center_radius),
            int(cy - center_radius),
            int(center_radius * 2),
            int(center_radius * 2),
        )

        if self._is_hw_fault():
            temp_text = "----"
            temp_color = QColor("#f44336")
            sp_color = QColor("#888888")
        else:
            temp_text = "--.-" if self._temperature is None else f"{self._temperature:.1f}"
            temp_color = QColor(self._state_color(self._state, False))
            sp_color = QColor("#bdbdbd")

        temp_font = QFont("Segoe UI", max(16, int(size * 0.12)), QFont.Weight.Bold)
        painter.setFont(temp_font)
        painter.setPen(QPen(temp_color))
        temp_rect = QRectF(cx - size * 0.34, cy - size * 0.17, size * 0.68, size * 0.20)
        painter.drawText(temp_rect, Qt.AlignmentFlag.AlignCenter, temp_text)

        sp_font = QFont("Segoe UI", max(9, int(size * 0.05)), QFont.Weight.Medium)
        painter.setFont(sp_font)
        painter.setPen(QPen(sp_color))
        sp_rect = QRectF(cx - size * 0.38, cy + size * 0.03, size * 0.76, size * 0.12)
        painter.drawText(sp_rect, Qt.AlignmentFlag.AlignCenter, f"SP {self._setpoint:.1f} °C")

        badge = self._bottom_badge()
        if badge is not None:
            badge_font = QFont("Segoe UI", max(8, int(size * 0.04)), QFont.Weight.Bold)
            painter.setFont(badge_font)
            badge_text, badge_bg, badge_border, badge_fg = badge
            badge_w = max(82, int(size * 0.42))
            badge_h = max(20, int(size * 0.11))
            bx = int(cx - badge_w / 2)
            by = int(cy + center_radius - (badge_h * 0.2))
            painter.setPen(QPen(QColor(badge_border), 1))
            painter.setBrush(QColor(badge_bg))
            painter.drawRoundedRect(bx, by, badge_w, badge_h, 6, 6)
            painter.setPen(QPen(QColor(badge_fg)))
            painter.drawText(bx, by, badge_w, badge_h, Qt.AlignmentFlag.AlignCenter, badge_text)

        painter.end()
class CountdownFace(QWidget):
    """Paints a subdued circular face behind the countdown text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._remaining_secs = 30 * 60
        self._total_secs = 30 * 60
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setMinimumHeight(90)

    def set_time_state(self, remaining_secs: int, total_secs: int):
        self._remaining_secs = remaining_secs
        self._total_secs = max(60, total_secs)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(6, 6, -6, -6)
        diameter = min(rect.width(), rect.height())
        if diameter < 40:
            painter.end()
            return

        cx = rect.center().x()
        cy = rect.center().y()
        radius = (diameter / 2) - 2
        ring_width = max(8.0, diameter * 0.055)
        gap_deg = 28.0
        sweep_deg = 360.0 - gap_deg
        start_deg = 90.0 + (gap_deg / 2.0)
        arc_rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        painter.setPen(QPen(QColor("#2d2d2d"), ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawArc(arc_rect, int(-start_deg * 16), int(-sweep_deg * 16))

        painter.setPen(QPen(QColor("#3d3d3d"), max(1.0, diameter * 0.006)))
        for step in range(0, 121, 20):
            angle = radians(start_deg + (step / 120.0) * sweep_deg)
            tick_outer = radius + max(3.0, diameter * 0.02)
            tick_inner = radius - ring_width - max(3.0, diameter * 0.02)
            x1 = cx + cos(angle) * tick_inner
            y1 = cy + sin(angle) * tick_inner
            x2 = cx + cos(angle) * tick_outer
            y2 = cy + sin(angle) * tick_outer
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Soft progress accent using the same muted language as the gauges.
        total = self._total_secs
        progress = 0.0 if total <= 0 else max(0.0, min(1.0, self._remaining_secs / total))
        accent_color = QColor("#4f6f83")
        if self._remaining_secs == 0:
            accent_color = QColor("#7b3a3a")
        elif self._remaining_secs <= 5 * 60:
            accent_color = QColor("#7a6840")
        painter.setPen(QPen(accent_color, ring_width * 0.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(
            arc_rect.adjusted(ring_width * 0.45, ring_width * 0.45, -ring_width * 0.45, -ring_width * 0.45),
            int(-start_deg * 16),
            int(-(sweep_deg * progress) * 16),
        )

        painter.setBrush(QColor("#232323"))
        painter.setPen(Qt.PenStyle.NoPen)
        center_radius = radius - ring_width - max(10.0, diameter * 0.08)
        painter.drawEllipse(
            int(cx - center_radius),
            int(cy - center_radius),
            int(center_radius * 2),
            int(center_radius * 2),
        )
        painter.end()


class CountdownPanel(QGroupBox):
    """Simple brew timer with presets and manual adjustment."""

    def __init__(self, parent=None):
        super().__init__("Nedtællingsur", parent)
        self._remaining_secs = 30 * 60
        self._full_scale_secs = 30 * 60
        self._running = False
        self._alarm_blinking = False
        self._blink_visible = True

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_blink)

        self._build_ui()
        self._refresh_display()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        time_host = QWidget()
        time_host_layout = QVBoxLayout(time_host)
        time_host_layout.setContentsMargins(0, 0, 0, 0)
        time_host_layout.setSpacing(0)

        self._time_face = CountdownFace(self)
        face_layout = QVBoxLayout(self._time_face)
        face_layout.setContentsMargins(0, 0, 0, 0)

        self._time_lbl = QLabel("30:00")
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_lbl.setFont(QFont("Segoe UI", 48, QFont.Weight.Bold))
        self._time_lbl.setMinimumHeight(90)
        self._time_lbl.setStyleSheet("background: transparent;")

        face_layout.addWidget(self._time_lbl, 1, Qt.AlignmentFlag.AlignCenter)
        time_host_layout.addWidget(self._time_face, 1)

        self._start_pause_btn = QPushButton("Start")
        self._start_pause_btn.setMinimumHeight(48)
        self._start_pause_btn.clicked.connect(self._toggle_running)

        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setMinimumHeight(48)
        self._reset_btn.clicked.connect(self._on_reset)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setMinimumHeight(48)
        self._stop_btn.clicked.connect(self._on_stop)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)
        btn_col.addWidget(self._start_pause_btn)
        btn_col.addWidget(self._reset_btn)
        btn_col.addWidget(self._stop_btn)
        btn_col.addStretch()

        top_row.addWidget(time_host, 1)
        top_row.addLayout(btn_col)

        minute_row = QHBoxLayout()
        minute_row.setSpacing(6)
        minute_row.addWidget(QLabel("Tid (min):"))
        self._minutes_spin = QSpinBox()
        self._minutes_spin.setRange(1, 240)
        self._minutes_spin.setValue(30)
        self._minutes_spin.valueChanged.connect(self._minutes_changed)
        minute_row.addWidget(self._minutes_spin)
        minute_row.addStretch()

        layout.addLayout(top_row)
        layout.addLayout(minute_row)
        self._apply_time_style()

    def _format_secs(self) -> str:
        minutes = self._remaining_secs // 60
        seconds = self._remaining_secs % 60
        return f"{minutes:02d}:{seconds:02d}"

    def _refresh_display(self):
        self._time_lbl.setText(self._format_secs())
        self._time_face.set_time_state(self._remaining_secs, self._full_scale_secs)
        self._apply_time_style()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_time_style()

    def _apply_time_style(self):
        available_width = max(160, self._time_lbl.width())
        available_height = max(70, self._time_lbl.height())
        font_px = max(28, min(int(available_width * 0.28), int(available_height * 0.70)))
        if self._remaining_secs == 0:
            color = "#f44336" if self._blink_visible else "transparent"
            self._time_lbl.setStyleSheet(
                f"font-size: {font_px}px; font-weight: 700; color: {color};"
            )
        elif self._remaining_secs <= 5 * 60:
            self._time_lbl.setStyleSheet(
                f"font-size: {font_px}px; font-weight: 700; color: #ffc107;"
            )
        else:
            self._time_lbl.setStyleSheet(
                f"font-size: {font_px}px; font-weight: 700; color: #e0e0e0;"
            )

    def _toggle_running(self):
        self._running = not self._running
        if self._running:
            self._stop_alarm_blink()
            if self._remaining_secs == 0:
                self._remaining_secs = max(60, self._minutes_spin.value() * 60)
                self._full_scale_secs = self._remaining_secs
            self._timer.start()
            self._start_pause_btn.setText("Pause")
        else:
            self._timer.stop()
            self._start_pause_btn.setText("Start")

    def _on_reset(self):
        self._running = False
        self._timer.stop()
        self._stop_alarm_blink()
        self._start_pause_btn.setText("Start")
        self._remaining_secs = self._minutes_spin.value() * 60
        self._full_scale_secs = self._remaining_secs
        self._refresh_display()

    def _on_stop(self):
        # Stop pauses countdown without resetting remaining time.
        self._running = False
        self._timer.stop()
        self._stop_alarm_blink()
        self._start_pause_btn.setText("Start")

    def _minutes_changed(self, value: int):
        if not self._running:
            self._stop_alarm_blink()
            self._remaining_secs = value * 60
            self._full_scale_secs = self._remaining_secs
            self._refresh_display()

    def _toggle_blink(self):
        self._blink_visible = not self._blink_visible
        self._apply_time_style()

    def _start_alarm_blink(self):
        self._alarm_blinking = True
        self._blink_visible = False
        self._blink_timer.start()
        self._apply_time_style()

    def _stop_alarm_blink(self):
        self._alarm_blinking = False
        self._blink_visible = True
        self._blink_timer.stop()

    def _tick(self):
        if self._remaining_secs > 0:
            self._remaining_secs -= 1
            self._refresh_display()
            if self._remaining_secs == 0:
                self._running = False
                self._timer.stop()
                self._start_pause_btn.setText("Start")
                self._start_alarm_blink()
            return
        self._running = False
        self._timer.stop()
        self._start_pause_btn.setText("Start")


class OverviewTab(QWidget):
    relay_toggled = pyqtSignal(int, bool)   # relay number (1–4), desired state
    setpoint_requested = pyqtSignal(int, float)  # thermostat (1-3), setpoint

    def __init__(self, thermostat_names: list, parent=None):
        super().__init__(parent)
        self._thermostat_names = thermostat_names[:3]
        self._mash_index = 1
        for i, name in enumerate(self._thermostat_names[:3]):
            if "mæskegryde" in name.lower():
                self._mash_index = i
                break

        self._graph_time_buf: deque[float] = deque(maxlen=1800)
        self._graph_temp_buf: deque[float] = deque(maxlen=1800)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        # ---- Temperature cards ----
        temps_group = QGroupBox("Temperatur")
        cards_row = QHBoxLayout(temps_group)
        cards_row.setSpacing(10)

        self._cards: list[TempCard] = []
        for i, name in enumerate(self._thermostat_names):
            card = TempCard(name)
            cards_row.addWidget(card)
            self._cards.append(card)

        # ---- Relays ----
        relays_group = QGroupBox("Relæer")
        relays_vbox = QVBoxLayout(relays_group)
        relays_vbox.setSpacing(8)

        relays_row = QHBoxLayout()
        relays_row.setSpacing(10)

        self._relay_btns: list[QPushButton] = []
        for i in range(4):
            btn = QPushButton(f"Relæ {i + 1}  —  OFF")
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            # Use a lambda with default arg to capture i
            btn.toggled.connect(
                lambda checked, idx=i + 1: self._on_relay_toggled(idx, checked)
            )
            relays_row.addWidget(btn)
            self._relay_btns.append(btn)

        relays_vbox.addLayout(relays_row)

        # ---- Middle split: task list + mash tun graph ----
        middle_group = QGroupBox("Brygforløb")
        middle_row = QHBoxLayout(middle_group)
        middle_row.setSpacing(10)

        left_column = QWidget()
        left_column_layout = QVBoxLayout(left_column)
        left_column_layout.setContentsMargins(0, 0, 0, 0)
        left_column_layout.setSpacing(10)

        tasks_group = QGroupBox("Opgaveliste")
        tasks_layout = QVBoxLayout(tasks_group)
        self._task_list_text = QPlainTextEdit()
        self._task_list_text.setPlaceholderText("Skriv opgaver for brygprocessen her")
        self._task_list_text.setPlainText(
            "1. Start opvarmning\n"
            "2. Kontroller mæsketemperatur\n"
            "3. Tilføj humle ved kog"
        )
        tasks_layout.addWidget(self._task_list_text)

        self._countdown_panel = CountdownPanel()
        left_column_layout.addWidget(tasks_group, 3)
        left_column_layout.addWidget(self._countdown_panel, 2)

        graph_group = QGroupBox("Mæskegryde temperatur")
        graph_layout = QVBoxLayout(graph_group)
        self._mash_graph = pg.PlotWidget()
        self._mash_graph.setBackground("#1e1e1e")
        self._mash_graph.showGrid(x=True, y=True, alpha=0.25)
        self._mash_graph.setLabel("left", "Temperatur (°C)")
        self._mash_graph.setLabel("bottom", "Minutter siden nu")
        self._mash_graph.setXRange(-30, 0, padding=0)
        self._mash_curve = self._mash_graph.plot(pen=pg.mkPen("#4caf50", width=2))
        graph_layout.addWidget(self._mash_graph)

        middle_row.addWidget(left_column, 1)
        middle_row.addWidget(graph_group, 1)

        root.addWidget(temps_group)
        root.addWidget(middle_group, 1)
        root.addWidget(relays_group)
        root.addStretch()

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_relay_toggled(self, relay_number: int, checked: bool):
        self.relay_toggled.emit(relay_number, checked)

    # ------------------------------------------------------------------
    # Data update
    # ------------------------------------------------------------------

    def update_data(self, status: SystemStatus):
        # Thermostat cards (index 0–2)
        for i, t in enumerate(status.thermostats):
            if i >= len(self._cards):
                break
            self._cards[i].update_thermostat(t)

        # Mæskegryde trend graph
        if self._mash_index < len(status.thermostats):
            mash_temp = status.thermostats[self._mash_index].temperature
            if mash_temp is not None:
                now = time.monotonic()
                self._graph_time_buf.append(now)
                self._graph_temp_buf.append(float(mash_temp))
                t0 = self._graph_time_buf[-1]
                x = [(ts - t0) / 60.0 for ts in self._graph_time_buf]
                self._mash_curve.setData(x, list(self._graph_temp_buf))

        # Relay buttons — block signals to avoid re-emitting during update
        for i, btn in enumerate(self._relay_btns):
            if i >= len(status.relays):
                break
            btn.blockSignals(True)
            state = status.relays[i]
            btn.setChecked(state)
            btn.setText(f"Relæ {i + 1}  —  {'ON' if state else 'OFF'}")
            if state:
                btn.setStyleSheet(
                    "background-color: #1b5e20; color: white; font-weight: bold;"
                )
            else:
                btn.setStyleSheet("")
            btn.blockSignals(False)

        # Keep per-thermostat setpoint controls in sync.
        for i, t in enumerate(status.thermostats):
            if i >= len(self._cards):
                break
            self._cards[i].sync_setpoint(t.setpoint)
