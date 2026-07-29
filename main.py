# Install SIGINT ignore before ANY other code runs.
import signal
signal.signal(signal.SIGINT, signal.SIG_IGN)

import sys

import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication

from hmi.main_window import MainWindow
from hmi.styles import DARK_STYLESHEET

# Re-install after imports — some modules (pyqtgraph, PyQt6) may reset the handler.
signal.signal(signal.SIGINT, signal.SIG_IGN)


class BrewhouseApp(QApplication):
    """QApplication that keeps SIGINT ignored and guards notify() against BaseException.

    QApplication.__init__() installs its own SIGINT handler which overrides signal.SIG_IGN.
    We re-apply SIG_IGN immediately after super().__init__() to undo that.
    The notify() override is a second safety net for any BaseException that
    escapes through PyQt6\'s C++ slot dispatch layer.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Qt installs its own SIGINT handler during __init__ — override it.
        signal.signal(signal.SIGINT, signal.SIG_IGN)

    def notify(self, receiver, event):
        try:
            return super().notify(receiver, event)
        except (KeyboardInterrupt, SystemExit):
            self.quit()
            return False


def main():
    app = BrewhouseApp(sys.argv)
    # Final defensive re-apply after full Qt initialisation.
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    app.setStyle("Fusion")

    # Configure pyqtgraph theming BEFORE any PlotWidget is created
    pg.setConfigOption("background", "#1e1e1e")
    pg.setConfigOption("foreground", "#e0e0e0")

    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
