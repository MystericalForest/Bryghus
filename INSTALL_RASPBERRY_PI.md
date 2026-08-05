# Installation på Raspberry Pi (Raspberry Pi OS)

Denne guide installerer Bryghus HMI på en Raspberry Pi med Raspberry Pi OS (Bookworm/Bullseye) med desktop.

## 1. Forudsætninger

- Raspberry Pi OS med desktop (GUI)
- Internetforbindelse
- Arduino/controller tilsluttet via USB
- Bruger med sudo-rettigheder

## 2. Opdater systemet

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

Efter reboot:

```bash
sudo apt update
```

## 3. Installer systempakker

Installer Python, pip, venv og Qt-relaterede pakker som PyQt6 typisk kræver:

```bash
sudo apt install -y \
  git \
  python3 \
  python3-pip \
  python3-venv \
  python3-dev \
  libgl1 \
  libegl1 \
  libxkbcommon0 \
  libdbus-1-3 \
  libfontconfig1 \
  libx11-xcb1
```

## 4. Hent projektet

```bash
git clone https://github.com/MystericalForest/Bryghus.git
cd Bryghus
```

## 5. Opret virtuelt miljø og installer Python-pakker

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Hvis installation af `PyQt6` fejler på din Pi, prøv:

```bash
sudo apt install -y python3-pyqt6
pip install pyserial pyqtgraph numpy
```

Bemærk: Hvis du bruger systemets `python3-pyqt6`, kan det være nødvendigt at køre appen uden venv, eller oprette venv med `--system-site-packages`.

## 6. Giv adgang til serial-port

Tilføj din bruger til `dialout` gruppen:

```bash
sudo usermod -aG dialout $USER
```

Log ud og ind igen (eller reboot), så gruppeændringen træder i kraft.

Kontroller porten:

```bash
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
```

## 7. Kør applikationen

Fra projektmappen:

```bash
source .venv/bin/activate
python main.py
```

I appen:

1. Vælg korrekt serial-port (typisk `/dev/ttyACM0` eller `/dev/ttyUSB0`)
2. Klik Tilslut

## 8. Vigtig drift-note

Applikationen ignorerer bevidst `SIGINT` (`Ctrl+C`) for at undgå hård nedlukning midt i Qt/serial-kommunikation.

- Luk appen via vinduets luk-knap.

## 9. Fejlfinding

### A. `Could not load the Qt platform plugin "xcb"`

Installer flere XCB-pakker:

```bash
sudo apt install -y libxcb-cursor0 libxcb-xinerama0 libxcb-render0 libxcb-shape0 libxcb-randr0
```

### B. Ingen serial-port vises

- Tjek USB-kabel og strøm
- Kør `dmesg | tail -n 50`
- Bekræft `dialout` medlemskab:

```bash
groups
```

### C. Permission denied på `/dev/ttyACM0`

- Bekræft `dialout` medlemskab
- Reboot og prøv igen

### D. Sort skærm / ingen GUI

- Sørg for at du kører Raspberry Pi OS med desktop
- Hvis du kører via SSH, brug X-forwarding eller kør lokalt på Pi

## 10. Auto-start (valgfrit)

Hvis appen skal starte automatisk ved login, kan du bruge en `.desktop` autostart-fil i:

`~/.config/autostart/`

Sig til hvis du vil have en færdig autostart-konfiguration genereret til dette projekt.
