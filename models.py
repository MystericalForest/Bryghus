from dataclasses import dataclass
from typing import Optional


@dataclass
class ThermostatData:
    temperature: Optional[float]
    setpoint: float
    heater: bool
    state: str
    fault: bool
    fault_code: int
    kp: float
    ki: float
    kd: float
    alarm_limit: float
    warning_limit: float
    window_size: int
    manual_mode: str
    manual_percent: float
    heat_percent: float

    @staticmethod
    def from_dict(d: dict) -> "ThermostatData":
        return ThermostatData(
            temperature=d.get("temperature"),  # None when Arduino sends JSON null
            setpoint=float(d.get("setpoint", 25.0)),
            heater=bool(d.get("heater", False)),
            state=str(d.get("state", "Opvarmning")),
            fault=bool(d.get("fault", False)),
            fault_code=int(d.get("faultCode", 0)),
            kp=float(d.get("kp", 2.0)),
            ki=float(d.get("ki", 5.0)),
            kd=float(d.get("kd", 1.0)),
            alarm_limit=float(d.get("alarmLimit", 5.0)),
            warning_limit=float(d.get("warningLimit", 2.0)),
            window_size=int(d.get("windowSize", 5000)),
            manual_mode=str(d.get("manualMode", "pid")),
            manual_percent=float(d.get("manualPercent", 0.0)),
            heat_percent=float(d.get("heatPercent", 0.0)),
        )


@dataclass
class Sensor4Data:
    temperature: Optional[float]
    fault: bool
    fault_code: int

    @staticmethod
    def from_dict(d: dict) -> "Sensor4Data":
        return Sensor4Data(
            temperature=d.get("temperature"),
            fault=bool(d.get("fault", False)),
            fault_code=int(d.get("faultCode", 0)),
        )


@dataclass
class SystemStatus:
    uptime: int
    selected_sensor: int
    relays: list
    thermostats: list  # list[ThermostatData], length 3
    sensor4: Sensor4Data
    override: bool

    @staticmethod
    def from_dict(d: dict) -> Optional["SystemStatus"]:
        if not d.get("success"):
            return None
        status = d.get("status", {})
        thermostats = []
        for key in ("thermostat1", "thermostat2", "thermostat3"):
            if key in d:
                thermostats.append(ThermostatData.from_dict(d[key]))
        return SystemStatus(
            uptime=int(status.get("uptime", 0)),
            selected_sensor=int(status.get("selectedSensor", 1)),
            relays=[bool(r) for r in d.get("relays", [False] * 4)],
            thermostats=thermostats,
            sensor4=Sensor4Data.from_dict(d.get("sensor4", {})),
            override=bool(d.get("override", False)),
        )
