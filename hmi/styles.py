DARK_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #1e1e1e;
}

QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}

QTabWidget::pane {
    border: 1px solid #3c3c3c;
    background-color: #1e1e1e;
}

QTabBar::tab {
    background-color: #2d2d2d;
    color: #aaaaaa;
    padding: 8px 22px;
    border: 1px solid #3c3c3c;
    border-bottom: none;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #1e1e1e;
    color: #ffffff;
    border-bottom-color: #1e1e1e;
}

QTabBar::tab:hover:!selected {
    background-color: #383838;
    color: #cccccc;
}

QGroupBox {
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    margin-top: 16px;
    padding-top: 8px;
    background-color: #1e1e1e;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: #888888;
    font-size: 8pt;
    text-transform: uppercase;
}

QPushButton {
    background-color: #3c3c3c;
    color: #e0e0e0;
    border: 1px solid #555555;
    padding: 6px 14px;
    border-radius: 4px;
    min-height: 28px;
}

QPushButton:hover {
    background-color: #4a4a4a;
    border-color: #666666;
}

QPushButton:pressed {
    background-color: #2a2a2a;
}

QPushButton:checked {
    background-color: #1b5e20;
    color: #ffffff;
    border-color: #2e7d32;
}

QPushButton:disabled {
    background-color: #2a2a2a;
    color: #666666;
    border-color: #3c3c3c;
}

QSpinBox, QDoubleSpinBox {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 3px 6px;
    min-height: 24px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #0078d4;
}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #3c3c3c;
    border: none;
    width: 18px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #4a4a4a;
}

QComboBox {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 3px 8px;
    min-height: 28px;
}

QComboBox:focus {
    border-color: #0078d4;
}

QComboBox::drop-down {
    border: none;
    width: 22px;
}

QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #555555;
    selection-background-color: #0078d4;
    outline: none;
}

QProgressBar {
    border: 1px solid #555555;
    border-radius: 3px;
    background-color: #2d2d2d;
    color: #e0e0e0;
    text-align: center;
    font-size: 8pt;
}

QProgressBar::chunk {
    background-color: #0078d4;
    border-radius: 2px;
}

QRadioButton {
    color: #e0e0e0;
    spacing: 6px;
}

QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 2px solid #555555;
    background-color: #2d2d2d;
}

QRadioButton::indicator:checked {
    background-color: #0078d4;
    border-color: #0078d4;
}

QScrollArea {
    background-color: #1e1e1e;
    border: none;
}

QScrollBar:vertical {
    background-color: #2d2d2d;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #555555;
    min-height: 20px;
    border-radius: 4px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #666666;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

QSplitter::handle {
    background-color: #3c3c3c;
    width: 2px;
}

QLabel {
    background-color: transparent;
}
"""
