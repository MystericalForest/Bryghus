import time
import csv
import re
from collections import deque
from datetime import datetime
from pathlib import Path

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QRadioButton, QScrollArea, QSplitter,
    QSpinBox, QVBoxLayout, QWidget,
)

from hmi.widgets import StatusLamp
from models import ThermostatData

_STATE_COLORS = {
    "Run":        "#4caf50",
    "Opvarmning": "#4caf50",
    "Advarsel":   "#ffc107",
    "Alarm":      "#f44336",
    "HW Alarm":   "#f44336",
}


class ThermostatTab(QWidget):
    command_requested = pyqtSignal(dict)

    @staticmethod
    def _format_decimal(value: float) -> str:
        return f"{value:.3f}".replace(".", ",")

    def __init__(self, thermostat_index: int, name: str, parent=None):
        super().__init__(parent)
        self._index = thermostat_index  # 1-based
        self._name = name
        self._start_time = time.monotonic()
        self._time_buf: deque = deque(maxlen=1800)
        self._temp_buf: deque = deque(maxlen=1800)
        self._log_interval_s = 5.0
        self._is_logging = False
        self._last_log_ts = 0.0
        self._log_file = None
        self._log_writer = None
        self._log_path = ""
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # ---- LEFT: monitoring ----
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(6)

        # Status row
        status_row = QHBoxLayout()
        self.lamp = StatusLamp(20)

        self.temp_label = QLabel("--.- °C")
        self.temp_label.setFont(QFont("Segoe UI", 34, QFont.Weight.Bold))

        self.state_label = QLabel("—")
        self.state_label.setFont(QFont("Segoe UI", 13))
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        status_row.addWidget(self.lamp)
        status_row.addWidget(self.temp_label)
        status_row.addStretch()
        status_row.addWidget(self.state_label)

        # Heater row
        heater_row = QHBoxLayout()
        self.heater_label = QLabel("Varme: FRA")
        self.heater_label.setFixedWidth(100)

        self.heat_bar = QProgressBar()
        self.heat_bar.setRange(0, 100)
        self.heat_bar.setFormat("  %v %")
        self.heat_bar.setFixedHeight(20)

        heater_row.addWidget(self.heater_label)
        heater_row.addWidget(self.heat_bar, 1)

        # HW Alarm reset button
        self.hw_alarm_btn = QPushButton("Nulstil HW Alarm")
        self.hw_alarm_btn.setStyleSheet(
            "background-color: #c62828; color: white; font-weight: bold;"
        )
        self.hw_alarm_btn.setVisible(False)
        self.hw_alarm_btn.clicked.connect(self._on_hw_alarm_reset)

        # CSV logging controls
        log_row = QHBoxLayout()
        self._log_btn = QPushButton("Start logning")
        self._log_btn.setStyleSheet("background-color: #1565c0; color: white;")
        self._log_btn.clicked.connect(self._on_toggle_logging)

        self._log_status = QLabel("Logning: stoppet")
        self._log_status.setStyleSheet("color: #9e9e9e;")

        log_row.addWidget(self._log_btn)
        log_row.addWidget(self._log_status, 1)

        # Temperature graph
        self.graph = pg.PlotWidget()
        self.graph.setBackground("#1e1e1e")
        self.graph.showGrid(x=True, y=True, alpha=0.25)
        self.graph.setLabel("left", "Temperatur (°C)")
        self.graph.setLabel("bottom", "Minutter siden nu")
        self.graph.setXRange(-30, 0, padding=0)

        self._temp_curve = self.graph.plot(
            pen=pg.mkPen("#4caf50", width=2), name="Temperatur"
        )
        self._sp_line = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen("#0078d4", width=1.5, style=Qt.PenStyle.DashLine),
        )
        self._warn_upper = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen("#ffc107", width=1, style=Qt.PenStyle.DashLine),
        )
        self._warn_lower = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen("#ffc107", width=1, style=Qt.PenStyle.DashLine),
        )
        self._alarm_upper = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen("#f44336", width=1, style=Qt.PenStyle.DashLine),
        )
        for item in (self._sp_line, self._warn_upper, self._warn_lower, self._alarm_upper):
            self.graph.addItem(item)

        left_layout.addLayout(status_row)
        left_layout.addLayout(heater_row)
        left_layout.addWidget(self.hw_alarm_btn)
        left_layout.addLayout(log_row)
        left_layout.addWidget(self.graph, 1)

        # ---- RIGHT: control panels in scroll area ----
        right_inner = QWidget()
        right_inner.setMinimumWidth(260)
        right_vbox = QVBoxLayout(right_inner)
        right_vbox.setContentsMargins(8, 0, 0, 0)
        right_vbox.setSpacing(10)

        right_vbox.addWidget(self._build_pid_group())
        right_vbox.addWidget(self._build_limits_group())
        right_vbox.addWidget(self._build_manual_group())
        right_vbox.addWidget(self._build_auto_group())
        right_vbox.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(right_inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(280)
        scroll.setMaximumWidth(340)

        splitter.addWidget(left)
        splitter.addWidget(scroll)
        splitter.setSizes([720, 300])

        root.addWidget(splitter)

    def _build_pid_group(self) -> QGroupBox:
        group = QGroupBox("PID Konfiguration")
        form = QFormLayout(group)
        form.setSpacing(8)

        self.sp_spin = QDoubleSpinBox()
        self.sp_spin.setRange(-30.0, 150.0)
        self.sp_spin.setSingleStep(0.5)
        self.sp_spin.setDecimals(1)
        self.sp_spin.setSuffix("  °C")

        self.kp_spin = QDoubleSpinBox()
        self.kp_spin.setRange(0.0, 100.0)
        self.kp_spin.setSingleStep(0.1)
        self.kp_spin.setDecimals(3)

        self.ki_spin = QDoubleSpinBox()
        self.ki_spin.setRange(0.0, 100.0)
        self.ki_spin.setSingleStep(0.1)
        self.ki_spin.setDecimals(3)

        self.kd_spin = QDoubleSpinBox()
        self.kd_spin.setRange(0.0, 100.0)
        self.kd_spin.setSingleStep(0.1)
        self.kd_spin.setDecimals(3)

        self.window_spin = QSpinBox()
        self.window_spin.setRange(1000, 30000)
        self.window_spin.setSingleStep(500)
        self.window_spin.setSuffix("  ms")

        self._pid_btn = QPushButton("Send PID")
        self._pid_btn.setStyleSheet("background-color: #0d47a1; color: white;")
        self._pid_btn.clicked.connect(self._on_send_pid)

        form.addRow("Setpunkt:", self.sp_spin)
        form.addRow("Kp:", self.kp_spin)
        form.addRow("Ki:", self.ki_spin)
        form.addRow("Kd:", self.kd_spin)
        form.addRow("PWM-vindue:", self.window_spin)
        form.addRow("", self._pid_btn)
        return group

    def _build_limits_group(self) -> QGroupBox:
        group = QGroupBox("Grænseværdier")
        form = QFormLayout(group)
        form.setSpacing(8)

        self.warning_spin = QDoubleSpinBox()
        self.warning_spin.setRange(0.1, 20.0)
        self.warning_spin.setSingleStep(0.5)
        self.warning_spin.setDecimals(1)
        self.warning_spin.setSuffix("  °C")

        self.alarm_spin = QDoubleSpinBox()
        self.alarm_spin.setRange(0.1, 20.0)
        self.alarm_spin.setSingleStep(0.5)
        self.alarm_spin.setDecimals(1)
        self.alarm_spin.setSuffix("  °C")

        self._limits_btn = QPushButton("Send grænser")
        self._limits_btn.setStyleSheet("background-color: #0d47a1; color: white;")
        self._limits_btn.clicked.connect(self._on_send_limits)

        form.addRow("Advarsel ±:", self.warning_spin)
        form.addRow("Alarm +:", self.alarm_spin)
        form.addRow("", self._limits_btn)
        return group

    def _build_manual_group(self) -> QGroupBox:
        group = QGroupBox("Manuel overstyring")
        vbox = QVBoxLayout(group)
        vbox.setSpacing(8)

        self.rb_pid     = QRadioButton("PID")
        self.rb_off     = QRadioButton("Off")
        self.rb_on      = QRadioButton("Fuld On")
        self.rb_percent = QRadioButton("Procent")
        self.rb_auto    = QRadioButton("Auto")
        self.rb_pid.setChecked(True)

        radio_row1 = QHBoxLayout()
        radio_row1.addWidget(self.rb_pid)
        radio_row1.addWidget(self.rb_off)

        radio_row2 = QHBoxLayout()
        radio_row2.addWidget(self.rb_on)
        radio_row2.addWidget(self.rb_percent)

        radio_row3 = QHBoxLayout()
        radio_row3.addWidget(self.rb_auto)
        radio_row3.addStretch()

        pct_row = QHBoxLayout()
        pct_lbl = QLabel("Procent:")
        self.pct_spin = QDoubleSpinBox()
        self.pct_spin.setRange(0.0, 100.0)
        self.pct_spin.setSingleStep(5.0)
        self.pct_spin.setDecimals(1)
        self.pct_spin.setSuffix("  %")
        self.pct_spin.setEnabled(False)
        pct_row.addWidget(pct_lbl)
        pct_row.addWidget(self.pct_spin)

        self.rb_percent.toggled.connect(self.pct_spin.setEnabled)

        self._manual_btn = QPushButton("Aktiver")
        self._manual_btn.setStyleSheet("background-color: #0d47a1; color: white;")
        self._manual_btn.clicked.connect(self._on_send_manual)

        vbox.addLayout(radio_row1)
        vbox.addLayout(radio_row2)
        vbox.addLayout(radio_row3)
        vbox.addLayout(pct_row)
        vbox.addWidget(self._manual_btn)
        return group

    def _build_auto_group(self) -> QGroupBox:
        group = QGroupBox("Auto-regulering")
        form = QFormLayout(group)
        form.setSpacing(8)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 150.0)
        self.threshold_spin.setSingleStep(0.5)
        self.threshold_spin.setDecimals(1)
        self.threshold_spin.setSuffix("  °C")

        note = QLabel("Fuld varme når temp\xa0<\xa0(setpunkt\xa0−\xa0grænse).\nSetpunkt hentes fra PID-gruppe.")
        note.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        note.setWordWrap(True)

        self._auto_btn = QPushButton("Send Auto")
        self._auto_btn.setStyleSheet("background-color: #0d47a1; color: white;")
        self._auto_btn.clicked.connect(self._on_send_auto)

        form.addRow("Grænse Δ under sp.:", self.threshold_spin)
        form.addRow(note)
        form.addRow("", self._auto_btn)
        return group

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Button flash feedback
    # ------------------------------------------------------------------

    def _flash_ok(self, btn: QPushButton):
        """Briefly flash a button green to confirm the command was queued."""
        original = btn.styleSheet()
        btn.setText("✓  " + btn.text())
        btn.setStyleSheet("background-color: #1b5e20; color: white;")
        QTimer.singleShot(
            800,
            lambda: (btn.setStyleSheet(original), btn.setText(btn.text().replace("✓  ", "", 1))),
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @staticmethod
    def _n(v: float) -> "int | float":
        """Return int when v is a whole number to save JSON bytes.
        e.g. 25.0 → 25  (saves 2 chars),  2.5 → 2.5 (unchanged).
        """
        iv = int(v)
        return iv if v == iv else v

    def _on_hw_alarm_reset(self):
        self.command_requested.emit({
            "command": "setState",
            "thermostat": self._index,
            "state": "clear",
        })

    def _on_send_pid(self):
        # Sænd setpunkt som selvstændig, kort kommando (cmd1).
        # Efterfølgende kommandoer sender kun én PID-parameter ad gangen
        # og IKKE setpoint igen — dermed holdes alle kommandoer under
        # Arduino'ens hardware UART RX-buffer-grænse på 64 bytes.
        t = self._index
        sp = self._n(self.sp_spin.value())

        # 1. Setpoint
        self.command_requested.emit({"command": "setPID", "thermostat": t, "setpoint": sp})

        # 2–4. Én PID-parameter pr. kommando (uden setpoint)
        self.command_requested.emit({"command": "setPID", "thermostat": t,
                                     "kp": self._n(self.kp_spin.value())})
        self.command_requested.emit({"command": "setPID", "thermostat": t,
                                     "ki": self._n(self.ki_spin.value())})
        self.command_requested.emit({"command": "setPID", "thermostat": t,
                                     "kd": self._n(self.kd_spin.value())})

        # 5. windowSize (uden setpoint)
        self.command_requested.emit({"command": "setPID", "thermostat": t,
                                     "windowSize": self.window_spin.value()})

        self._flash_ok(self._pid_btn)

    def _on_send_limits(self):
        # Split into two short commands (~49 chars each) to avoid Arduino crash.
        t = self._index
        self.command_requested.emit({"command": "setLimits", "thermostat": t,
                                     "warning": self._n(self.warning_spin.value())})
        self.command_requested.emit({"command": "setLimits", "thermostat": t,
                                     "alarm": self._n(self.alarm_spin.value())})
        self._flash_ok(self._limits_btn)

    def _on_send_auto(self):
        # setAuto med både threshold OG setpoint overstiger 64 bytes (+\n),
        # som er Arduino'ens hardware UART RX-buffer-grænse.
        # Løsning: send setpunktet først via setPID (kort kommando),
        # derefter setAuto med kun threshold (også kort).
        t = self._index
        sp = self._n(self.sp_spin.value())
        threshold = self._n(self.threshold_spin.value())

        self.command_requested.emit({"command": "setPID", "thermostat": t, "setpoint": sp})
        self.command_requested.emit({"command": "setAuto", "thermostat": t,
                                     "threshold": threshold})
        self._flash_ok(self._auto_btn)

    def _on_send_manual(self):
        if self.rb_pid.isChecked():
            mode = "pid"
        elif self.rb_off.isChecked():
            mode = "off"
        elif self.rb_on.isChecked():
            mode = "on"
        elif self.rb_auto.isChecked():
            mode = "auto"
        else:
            mode = "percent"

        cmd: dict = {
            "command": "setManual",
            "thermostat": self._index,
            "mode": mode,
        }
        if mode == "percent":
            cmd["percent"] = self.pct_spin.value()
        self.command_requested.emit(cmd)
        self._flash_ok(self._manual_btn)

    def _on_toggle_logging(self):
        if self._is_logging:
            self._stop_logging()
        else:
            self._start_logging()

    def _start_logging(self):
        if self._is_logging:
            return

        try:
            logs_dir = Path(__file__).resolve().parent.parent / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)

            safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", self._name).strip("_")
            if not safe_name:
                safe_name = f"thermostat_{self._index}"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = logs_dir / f"{safe_name}_{ts}.csv"

            self._log_file = path.open("w", newline="", encoding="utf-8")
            self._log_writer = csv.writer(self._log_file, delimiter=";")
            self._log_writer.writerow([
                "timestamp",
                "thermostat_navn",
                "temperature",
                "setpoint",
                "reguleringstype",
                "state",
                "heater",
                "heat_percent",
            ])
            self._log_file.flush()

            self._is_logging = True
            self._last_log_ts = 0.0
            self._log_path = str(path)
            self._log_btn.setText("Stop og gem")
            self._log_btn.setStyleSheet("background-color: #b71c1c; color: white;")
            self._log_status.setText(f"Logger: {path.name}")
            self._log_status.setStyleSheet("color: #4caf50;")
        except OSError as exc:
            self._is_logging = False
            self._log_writer = None
            if self._log_file:
                try:
                    self._log_file.close()
                except OSError:
                    pass
            self._log_file = None
            self._log_path = ""
            self._log_status.setText(f"Log fejl: {exc}")
            self._log_status.setStyleSheet("color: #f44336;")

    def _stop_logging(self, announce_saved: bool = True):
        if not self._is_logging and self._log_file is None:
            return

        path = self._log_path
        if self._log_file:
            try:
                self._log_file.flush()
                self._log_file.close()
            except OSError as exc:
                self._log_status.setText(f"Log fejl ved lukning: {exc}")
                self._log_status.setStyleSheet("color: #f44336;")

        self._is_logging = False
        self._log_file = None
        self._log_writer = None
        self._log_path = ""
        self._last_log_ts = 0.0
        self._log_btn.setText("Start logning")
        self._log_btn.setStyleSheet("background-color: #1565c0; color: white;")
        if path and announce_saved:
            self._log_status.setText(f"Gemt: {Path(path).name}")
            self._log_status.setStyleSheet("color: #9e9e9e;")
        elif announce_saved:
            self._log_status.setText("Logning: stoppet")
            self._log_status.setStyleSheet("color: #9e9e9e;")

    def _write_log_row(self, data: ThermostatData, now_monotonic: float):
        if not self._is_logging or self._log_writer is None:
            return
        if data.temperature is None:
            return
        if now_monotonic - self._last_log_ts < self._log_interval_s:
            return

        try:
            self._log_writer.writerow([
                datetime.now().isoformat(timespec="seconds"),
                self._name,
                self._format_decimal(data.temperature),
                self._format_decimal(data.setpoint),
                data.manual_mode,
                data.state,
                int(data.heater),
                self._format_decimal(data.heat_percent),
            ])
            if self._log_file:
                self._log_file.flush()
            self._last_log_ts = now_monotonic
        except OSError as exc:
            self._log_status.setText(f"Log fejl: {exc}")
            self._log_status.setStyleSheet("color: #f44336;")
            self._stop_logging(announce_saved=False)

    # ------------------------------------------------------------------
    # Data update
    # ------------------------------------------------------------------

    def update_data(self, data: ThermostatData):
        # --- Temperature display ---
        if data.temperature is not None:
            self.temp_label.setText(f"{data.temperature:.1f} °C")
        else:
            self.temp_label.setText("-- °C")

        # --- Status ---
        self.lamp.setState(data.state)
        self.state_label.setText(data.state)
        color = _STATE_COLORS.get(data.state, "#e0e0e0")
        self.state_label.setStyleSheet(f"color: {color}; font-weight: bold;")

        # --- Heater ---
        if data.heater:
            self.heater_label.setText("Varme: TIL")
            self.heater_label.setStyleSheet("color: #ef9a9a; font-weight: bold;")
        else:
            self.heater_label.setText("Varme: FRA")
            self.heater_label.setStyleSheet("color: #777777;")
        self.heat_bar.setValue(int(data.heat_percent))

        # --- HW Alarm button ---
        self.hw_alarm_btn.setVisible(data.state == "HW Alarm")

        # --- Graph ---
        elapsed = time.monotonic() - self._start_time
        if data.temperature is not None:
            self._time_buf.append(elapsed)
            self._temp_buf.append(data.temperature)

        if self._time_buf:
            xs = list(self._time_buf)
            ys = list(self._temp_buf)
            t_now = xs[-1]
            x_rel = [(t - t_now) / 60.0 for t in xs]
            self._temp_curve.setData(x_rel, ys)
        self.graph.setXRange(-30, 0, padding=0)

        # CSV logging at fixed sampling interval from incoming status updates.
        self._write_log_row(data, time.monotonic())

        # --- Limit lines ---
        sp = data.setpoint
        self._sp_line.setValue(sp)
        self._warn_upper.setValue(sp + data.warning_limit)
        self._warn_lower.setValue(sp - data.warning_limit)
        self._alarm_upper.setValue(sp + data.alarm_limit)

        # --- Sync control widgets with Arduino's confirmed values.
        # Skip any widget that currently has keyboard focus (user is editing it). ---
        self._sync_controls(data)

    def closeEvent(self, event):
        self._stop_logging()
        super().closeEvent(event)

    def _sync_spin(self, spin, value: float):
        """Update a spinbox from Arduino data unless the user is currently editing it."""
        if not spin.hasFocus():
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def _sync_controls(self, data: ThermostatData):
        self._sync_spin(self.sp_spin,        data.setpoint)
        self._sync_spin(self.kp_spin,         data.kp)
        self._sync_spin(self.ki_spin,         data.ki)
        self._sync_spin(self.kd_spin,         data.kd)
        self._sync_spin(self.window_spin,     data.window_size)
        self._sync_spin(self.warning_spin,    data.warning_limit)
        self._sync_spin(self.alarm_spin,      data.alarm_limit)
        self._sync_spin(self.pct_spin,        data.manual_percent)
        self._sync_spin(self.threshold_spin,  data.auto_threshold)

        # Sync manual mode radio buttons (only if none of them have focus)
        radios = (self.rb_pid, self.rb_off, self.rb_on, self.rb_percent, self.rb_auto)
        if not any(r.hasFocus() for r in radios):
            mode_map = {
                "pid":     self.rb_pid,
                "off":     self.rb_off,
                "on":      self.rb_on,
                "percent": self.rb_percent,
                "auto":    self.rb_auto,
            }
            target = mode_map.get(data.manual_mode, self.rb_pid)
            if not target.isChecked():
                target.blockSignals(True)
                target.setChecked(True)
                target.blockSignals(False)
