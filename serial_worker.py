import json
import queue
import time

import serial
import serial.tools.list_ports
from PyQt6.QtCore import QThread, pyqtSignal


def list_serial_ports() -> list:
    return sorted(p.device for p in serial.tools.list_ports.comports())


class SerialWorker(QThread):
    data_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)   # True = connected, False = disconnected
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._port = ""
        self._ser: serial.Serial | None = None
        self._cmd_queue: queue.Queue = queue.Queue()
        self._running = False

    def connect_port(self, port: str):
        if self.isRunning():
            return
        self._port = port
        self._running = True
        self.start()

    def disconnect_port(self):
        self._running = False

    def send_command(self, cmd: dict):
        self._cmd_queue.put(cmd)

    def run(self):
        try:
            self._ser = serial.Serial(self._port, 115200, timeout=2)
            # Arduino resets on DTR toggle — wait for boot sequence to finish
            time.sleep(2.5)
            self._ser.reset_input_buffer()
            # Send a bare newline to flush any leftover bytes in Arduino's
            # receive buffer.  Arduino will respond with {"success":false,...}
            # which we discard via a short sleep + buffer flush.
            self._ser.write(b"\n")
            time.sleep(0.3)
            self._ser.reset_input_buffer()
        except Exception as exc:
            self.error_occurred.emit(f"Kunne ikke åbne {self._port}: {exc}")
            self._running = False
            return

        # Discard commands queued before this connection (stale from previous session)
        while True:
            try:
                self._cmd_queue.get_nowait()
            except queue.Empty:
                break

        self.connection_changed.emit(True)
        last_poll = 0.0

        while self._running:
            now = time.monotonic()

            # Drain queued commands with priority
            cmd = None
            try:
                cmd = self._cmd_queue.get_nowait()
            except queue.Empty:
                pass

            # Fall back to periodic status poll
            if cmd is None:
                if now - last_poll >= 1.0:
                    cmd = {"command": "status"}
                    last_poll = now
                else:
                    time.sleep(0.02)
                    continue

            try:
                is_user_cmd = cmd.get("command") != "status"

                if is_user_cmd:
                    time.sleep(0.20)  # Let in-flight USB packets settle
                    print(f"[TX] {json.dumps(cmd, separators=(',', ':'))}", flush=True)

                line = json.dumps(cmd, separators=(',', ':')) + "\n"
                self._ser.write(line.encode())

                # Read response — up to 3 readline() attempts so that a
                # spurious non-JSON stale line from a previous partial read
                # doesn't consume the real response.  Also logs how many
                # bytes are buffered on timeout to help diagnose root cause.
                response = None
                for attempt in range(3):
                    raw = self._ser.readline()
                    if not raw:
                        if is_user_cmd:
                            waiting = self._ser.in_waiting
                            print(
                                f"[TIMEOUT attempt {attempt+1}/3] "
                                f"{waiting} bytes still in buffer",
                                flush=True,
                            )
                        break  # No \n received within timeout — give up

                    text = raw.decode("utf-8", errors="replace").strip()
                    if text.startswith('{'):
                        response = text
                        break
                    elif text and is_user_cmd:
                        # Non-JSON line — stale bytes from a previous partial read
                        print(f"[SKIP stale] {repr(text[:80])}", flush=True)
                    # Empty or stale line: try reading the next line

                if response is None:
                    continue

                try:
                    parsed = json.loads(response)
                except json.JSONDecodeError:
                    print(f"[BAD JSON from Arduino] {repr(response[:200])}", flush=True)
                    continue

                if not parsed.get("success", True) and is_user_cmd:
                    print(f"[ERR] {response}", flush=True)
                self.data_received.emit(parsed)

            except serial.SerialException as exc:
                self.error_occurred.emit(f"Seriel fejl: {exc}")
                self._running = False
                break
            except OSError as exc:
                self.error_occurred.emit(f"Port lukket: {exc}")
                self._running = False
                break

        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except Exception:
            pass

        self.connection_changed.emit(False)
