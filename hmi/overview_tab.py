from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QGroupBox, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

from hmi.widgets import StatusLamp
from models import SystemStatus, ThermostatData, Sensor4Data

_STATE_COLORS = {
    "Run":        "#4caf50",
    "Opvarmning": "#4caf50",
    "Advarsel":   "#ffc107",
    "Alarm":      "#f44336",
    "HW Alarm":   "#f44336",
}


class TempCard(QFrame):
    """Card widget showing temperature, status and optionally heat %."""

    def __init__(self, name: str, show_heat: bool = True, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { border: 1px solid #3c3c3c; border-radius: 6px;"
            " background-color: #252525; }"
        )
        self.setMinimumWidth(180)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(10, 8, 10, 8)

        name_lbl = QLabel(name)
        name_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet("border: none; background: transparent;")

        status_row = QHBoxLayout()
        self.lamp = StatusLamp(14)
        self.state_lbl = QLabel("")
        self.state_lbl.setStyleSheet(
            "font-size: 10pt; border: none; background: transparent;"
        )
        status_row.addWidget(self.lamp)
        status_row.addWidget(self.state_lbl)
        status_row.addStretch()

        self.temp_lbl = QLabel("--.- °C")
        self.temp_lbl.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.temp_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.temp_lbl.setStyleSheet("border: none; background: transparent;")

        self.heat_bar = QProgressBar()
        self.heat_bar.setRange(0, 100)
        self.heat_bar.setFormat("  %v %")
        self.heat_bar.setFixedHeight(14)
        self.heat_bar.setVisible(show_heat)

        layout.addWidget(name_lbl)
        layout.addLayout(status_row)
        layout.addWidget(self.temp_lbl)
        layout.addWidget(self.heat_bar)

    def update_thermostat(self, data: ThermostatData):
        if data.temperature is not None:
            self.temp_lbl.setText(f"{data.temperature:.1f} °C")
        else:
            self.temp_lbl.setText("-- °C")
        self.lamp.setState(data.state)
        color = _STATE_COLORS.get(data.state, "#e0e0e0")
        self.state_lbl.setText(data.state)
        self.state_lbl.setStyleSheet(
            f"color: {color}; font-size: 10pt; border: none; background: transparent;"
        )
        self.heat_bar.setValue(int(data.heat_percent))

    def update_sensor(self, data: Sensor4Data):
        if data.temperature is not None:
            self.temp_lbl.setText(f"{data.temperature:.1f} °C")
        else:
            self.temp_lbl.setText("-- °C")


class OverviewTab(QWidget):
    relay_toggled = pyqtSignal(int, bool)   # relay number (1–4), desired state
    override_toggled = pyqtSignal(bool)     # True = activate

    def __init__(self, thermostat_names: list, parent=None):
        super().__init__(parent)
        self._thermostat_names = thermostat_names
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        # ---- Temperature cards ----
        temps_group = QGroupBox("Temperaturer & Status")
        cards_row = QHBoxLayout(temps_group)
        cards_row.setSpacing(10)

        self._cards: list[TempCard] = []
        for name in self._thermostat_names:
            card = TempCard(name, show_heat=True)
            cards_row.addWidget(card)
            self._cards.append(card)

        ambient_card = TempCard("Ambient (sensor 4)", show_heat=False)
        cards_row.addWidget(ambient_card)
        self._cards.append(ambient_card)

        # ---- Relays ----
        relays_group = QGroupBox("Relæer")
        relays_row = QHBoxLayout(relays_group)
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

        # ---- Override ----
        override_group = QGroupBox("Manuel overstyring (fuld varme)")
        override_vbox = QVBoxLayout(override_group)

        self._override_btn = QPushButton("FULD VARME PÅ")
        self._override_btn.setCheckable(True)
        self._override_btn.setMinimumHeight(50)
        self._override_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._override_btn.toggled.connect(self._on_override_toggled)

        self._override_warning = QLabel(
            "⚠  Manuel overstyring aktiv — alle termostater kører med fuld varme!"
        )
        self._override_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._override_warning.setStyleSheet(
            "color: #f44336; font-weight: bold; font-size: 11pt;"
            " background: transparent;"
        )
        self._override_warning.setVisible(False)

        override_vbox.addWidget(self._override_btn)
        override_vbox.addWidget(self._override_warning)

        root.addWidget(temps_group)
        root.addWidget(relays_group)
        root.addWidget(override_group)
        root.addStretch()

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_relay_toggled(self, relay_number: int, checked: bool):
        self.relay_toggled.emit(relay_number, checked)

    def _on_override_toggled(self, checked: bool):
        self._apply_override_visual(checked)
        self.override_toggled.emit(checked)

    def _apply_override_visual(self, active: bool):
        if active:
            self._override_btn.setText("DEAKTIVER OVERSTYRING")
            self._override_btn.setStyleSheet(
                "background-color: #b71c1c; color: white; font-weight: bold;"
            )
            self._override_warning.setVisible(True)
        else:
            self._override_btn.setText("FULD VARME PÅ")
            self._override_btn.setStyleSheet("")
            self._override_warning.setVisible(False)

    # ------------------------------------------------------------------
    # Data update
    # ------------------------------------------------------------------

    def update_data(self, status: SystemStatus):
        # Thermostat cards (index 0–2)
        for i, t in enumerate(status.thermostats):
            self._cards[i].update_thermostat(t)

        # Ambient card (index 3)
        self._cards[3].update_sensor(status.sensor4)

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

        # Override
        self._override_btn.blockSignals(True)
        self._override_btn.setChecked(status.override)
        self._apply_override_visual(status.override)
        self._override_btn.blockSignals(False)
