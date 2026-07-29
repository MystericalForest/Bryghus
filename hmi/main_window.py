from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from hmi.overview_tab import OverviewTab
from hmi.thermostat_tab import ThermostatTab
from models import SystemStatus
from serial_worker import SerialWorker, list_serial_ports

_THERMOSTAT_NAMES = ["Sparge-vand", "Kogekar", "Mæskegryde"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bryghus Termostat HMI")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 780)

        self._worker = SerialWorker(self)
        self._worker.data_received.connect(self._on_data)
        self._worker.connection_changed.connect(self._on_connection_changed)
        self._worker.error_occurred.connect(self._on_error)

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Connection bar (always visible at top)
        root.addWidget(self._build_connection_bar())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3c3c3c;")
        root.addWidget(sep)

        # Tabs
        self._tabs = QTabWidget()

        self._overview_tab = OverviewTab(_THERMOSTAT_NAMES)
        self._overview_tab.relay_toggled.connect(self._on_relay_toggled)
        self._overview_tab.override_toggled.connect(self._on_override_toggled)

        self._thermostat_tabs: list[ThermostatTab] = []
        for i, name in enumerate(_THERMOSTAT_NAMES):
            tab = ThermostatTab(i + 1, name)
            tab.command_requested.connect(self._worker.send_command)
            self._thermostat_tabs.append(tab)

        self._tabs.addTab(self._overview_tab, "  Oversigt  ")
        for name, tab in zip(_THERMOSTAT_NAMES, self._thermostat_tabs):
            self._tabs.addTab(tab, f"  {name}  ")

        root.addWidget(self._tabs, 1)

    def _build_connection_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        bar.setStyleSheet("background-color: #252525;")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(8)

        port_lbl = QLabel("COM-port:")
        port_lbl.setStyleSheet("background: transparent; font-weight: bold;")

        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(130)
        self._refresh_ports()

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(34)
        refresh_btn.setToolTip("Opdater liste over COM-porte")
        refresh_btn.clicked.connect(self._refresh_ports)

        self._connect_btn = QPushButton("Tilslut")
        self._connect_btn.setFixedWidth(110)
        self._connect_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._connect_btn.setStyleSheet(
            "background-color: #1b5e20; color: white; border-color: #2e7d32;"
        )
        self._connect_btn.clicked.connect(self._toggle_connection)

        self._status_lbl = QLabel("Ikke forbundet")
        self._status_lbl.setStyleSheet("color: #777777; background: transparent;")

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet("color: #f44336; background: transparent;")

        layout.addWidget(port_lbl)
        layout.addWidget(self._port_combo)
        layout.addWidget(refresh_btn)
        layout.addWidget(self._connect_btn)
        layout.addWidget(self._status_lbl)
        layout.addStretch()
        layout.addWidget(self._error_lbl)
        return bar

    # ------------------------------------------------------------------
    # Port management
    # ------------------------------------------------------------------

    def _refresh_ports(self):
        current = self._port_combo.currentText()
        self._port_combo.clear()
        ports = list_serial_ports()
        self._port_combo.addItems(ports)
        if current in ports:
            self._port_combo.setCurrentText(current)

    def _toggle_connection(self):
        if self._worker.isRunning():
            self._connect_btn.setEnabled(False)
            self._worker.disconnect_port()
        else:
            port = self._port_combo.currentText()
            if not port:
                self._error_lbl.setText("Vælg en COM-port")
                return
            self._error_lbl.setText("")
            self._worker.connect_port(port)

    # ------------------------------------------------------------------
    # Worker signals → UI
    # ------------------------------------------------------------------

    def _on_connection_changed(self, connected: bool):
        self._connect_btn.setEnabled(True)
        if connected:
            self._connect_btn.setText("Frakobl")
            self._connect_btn.setStyleSheet(
                "background-color: #b71c1c; color: white; border-color: #c62828;"
            )
            port = self._port_combo.currentText()
            self._status_lbl.setText(f"Forbundet  ·  {port}")
            self._status_lbl.setStyleSheet("color: #4caf50; background: transparent;")
            self._port_combo.setEnabled(False)
            self._error_lbl.setText("")
        else:
            self._connect_btn.setText("Tilslut")
            self._connect_btn.setStyleSheet(
                "background-color: #1b5e20; color: white; border-color: #2e7d32;"
            )
            self._status_lbl.setText("Ikke forbundet")
            self._status_lbl.setStyleSheet("color: #777777; background: transparent;")
            self._port_combo.setEnabled(True)

    def _on_data(self, data: dict):
        # Show Arduino-level errors (e.g. missing parameter, invalid value)
        if not data.get("success", True):
            self._error_lbl.setText(f"Arduino fejl: {data.get('error', 'Ukendt')}")
            return
        self._error_lbl.setText("")
        status = SystemStatus.from_dict(data)
        if status is None:
            return
        self._overview_tab.update_data(status)
        for i, tab in enumerate(self._thermostat_tabs):
            if i < len(status.thermostats):
                tab.update_data(status.thermostats[i])

    def _on_error(self, msg: str):
        self._error_lbl.setText(f"Fejl: {msg}")

    # ------------------------------------------------------------------
    # UI → worker commands
    # ------------------------------------------------------------------

    def _on_relay_toggled(self, relay: int, state: bool):
        self._worker.send_command({
            "command": "setRelay",
            "relay": relay,
            "state": state,
        })

    def _on_override_toggled(self, active: bool):
        self._worker.send_command({
            "command": "setOverride",
            "active": active,
        })

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._worker.disconnect_port()
        self._worker.wait(3000)
        event.accept()
