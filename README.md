# Bryghus

Kontrolsoftware til bryganlæg med:

- PyQt6 HMI (Windows desktop)
- Arduino-baseret termostatcontroller over serial JSON
- 3 termostater + 4. sensor (ambient)
- CSV-logning pr. termostat

## Krav

- Python 3.12+
- Installer dependencies fra requirements.txt
- Arduino firmware fra interface/interface.ino

## Start applikationen

1. Opret og aktivér virtuelt miljø.
2. Installer pakker:

	pip install -r requirements.txt

3. Start HMI:

	python main.py

## Vigtigt om lukning (seneste rettelse)

Applikationen ignorerer bevidst SIGINT (Ctrl+C), så den ikke afsluttes hårdt midt i Qt event-loop eller seriel kommunikation.

- Luk appen normalt via vinduets luk-knap.
- Der håndteres også KeyboardInterrupt/SystemExit defensivt i QApplication.notify().

## CSV-logning pr. termostat

Hver termostatfane har en knap til logning:

- Start logning: opretter en ny CSV-fil
- Stop og gem: lukker filen sikkert

Filer gemmes i mappen logs/ i projektets rodmappe.

Der logges hvert 5. sekund med følgende kolonner:

- timestamp
- thermostat_navn
- temperature
- setpoint
- reguleringstype
- state
- heater
- heat_percent

CSV-filer skrives med ; som separator og , som decimalseparator.

## Dokumentation

- API: interface/termostat_api.html
- Fysisk betjening: interface/betjeningsvejledning.html
- Tuningnoter: tune.md
- Raspberry Pi installation: INSTALL_RASPBERRY_PI.md
