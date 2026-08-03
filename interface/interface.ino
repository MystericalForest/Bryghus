// =============================================================================
// Termostat Controller
// -----------------------------------------------------------------------------
// Hardware:
//   - 4x relæer med knapper og LED-indikatorer
//   - 3x PID-varmestyring med relæudgange
//   - 4x PT100 temperatursensorer via MAX31865 (SPI)
//       Sensor 1-3: bruges til PID-regulering og alarm/advarsel
//       Sensor 4:   ekstra/ambient — kun overvågning og JSON-output
//   - TM1637 4-cifret display
//   - 4x sensor-LED'er + 1 sensorvælger-knap
//   - 3x status-LED-grupper (Rød/Gul/Grøn) — én gruppe pr. termostat
//   - 3x varme-LED'er — viser om varmerelæet er aktivt
//
// Kommunikation:
//   - Serial JSON API, 115200 baud, newline-termineret (\n)
//   - Se sendStatus() for svarstruktur
//
// Konfiguration:
//   - Alle pins, standardværdier og grænser findes i config.h
//
// Afhængigheder (installer via Library Manager):
//   - Adafruit MAX31865 library  (Adafruit_MAX31865.h)
//   - PID_v1                     (PID_v1.h)
//   - TM1637Display              (TM1637Display.h)
//   - ArduinoJson                (ArduinoJson.h)
// =============================================================================

#include <Arduino.h>
#include <avr/wdt.h>        // Hardware watchdog — genstarter ved hang
#include <SPI.h>
#include <Adafruit_MAX31865.h>
#include <PID_v1.h>
#include <TM1637Display.h>
#include <ArduinoJson.h>
#include "config.h"         // Hardware-konfiguration og standardindstillinger


// =============================================================================
// PIN-ARRAYS
// Udfoldes fra config.h — rediger ikke her, kun i config.h
// =============================================================================

// --- Almindelige relæer ---
const int relayPins[NUM_RELAYS]    = RELAY_PINS;
const int relayButtons[NUM_RELAYS] = RELAY_BUTTONS;
const int relayLEDs[NUM_RELAYS]    = RELAY_LEDS;

// --- PID varmestyring ---
const int heatRelayPins[NUM_THERMOSTATS] = HEAT_RELAY_PINS;

// --- Termostat status-LED'er ---
const int statusLedRed[NUM_THERMOSTATS]    = STATUS_LED_RED;
const int statusLedYellow[NUM_THERMOSTATS] = STATUS_LED_YELLOW;
const int statusLedGreen[NUM_THERMOSTATS]  = STATUS_LED_GREEN;

// --- Varme-LED'er ---
const int heatLedPins[NUM_THERMOSTATS] = HEAT_LED_PINS;

// --- Sensorvælger og LED'er ---
const int sensorButton          = SENSOR_BUTTON_PIN;
const int sensorLEDs[NUM_TEMPS] = SENSOR_LED_PINS;

// --- Manuel overstyring ---
const int overrideButton = OVERRIDE_BUTTON_PIN;
const int overrideLed    = OVERRIDE_LED_PIN;

// --- MAX31865 CS-pins ---
const int max31865CsPins[NUM_TEMPS] = MAX31865_CS_PINS;


// =============================================================================
// MAX31865 SENSOR-OBJEKTER
// =============================================================================

// Adafruit_MAX31865 tager CS-pin som argument; SPI-bus deles automatisk.
Adafruit_MAX31865 sensors[NUM_TEMPS] = {
  Adafruit_MAX31865(max31865CsPins[0]),
  Adafruit_MAX31865(max31865CsPins[1]),
  Adafruit_MAX31865(max31865CsPins[2]),
  Adafruit_MAX31865(max31865CsPins[3])
};

// Fejlflag pr. sensor — sættes ved MAX31865 fault, nulstilles ved næste
// vellykkede aflæsning. Sætter "HW Alarm" på tilhørende termostat (sensor 1-3).
// Sensor 4 HW-fejl vises kun i JSON (sensor4.fault = true).
bool sensorFault[NUM_TEMPS] = {false, false, false, false};

// Sidst registrerede fault-kode fra MAX31865 (til diagnostik via JSON)
uint8_t sensorFaultCode[NUM_TEMPS] = {0, 0, 0, 0};

// Timer til periodisk sensor-aflæsning
unsigned long lastTempRead = 0;


// =============================================================================
// TILSTANDSVARIABLER
// =============================================================================

// --- Relætilstande ---
bool relayState[NUM_RELAYS];

// --- Varmerelætilstande ---
bool heatRelayState[NUM_THERMOSTATS];

// --- Temperaturer ---
// NaN bruges som sentinel-værdi når sensor er i fejltilstand
float temps[NUM_TEMPS];

// --- PID ---
double pidInput[NUM_THERMOSTATS];
double pidOutput[NUM_THERMOSTATS];
double setpoint[NUM_THERMOSTATS]  = PID_SETPOINTS;

double kp[NUM_THERMOSTATS] = PID_KP;
double ki[NUM_THERMOSTATS] = PID_KI;
double kd[NUM_THERMOSTATS] = PID_KD;

unsigned long windowSize[NUM_THERMOSTATS] = PID_WINDOW_SIZES;
unsigned long windowStart[NUM_THERMOSTATS];

PID pid1(&pidInput[0], &pidOutput[0], &setpoint[0], kp[0], ki[0], kd[0], DIRECT);
PID pid2(&pidInput[1], &pidOutput[1], &setpoint[1], kp[1], ki[1], kd[1], DIRECT);
PID pid3(&pidInput[2], &pidOutput[2], &setpoint[2], kp[2], ki[2], kd[2], DIRECT);
PID* pids[NUM_THERMOSTATS] = {&pid1, &pid2, &pid3};

// --- Termostat status ---
// Gyldige værdier: "Opvarmning", "Run", "Advarsel", "Alarm", "HW Alarm"
// "HW Alarm" sættes automatisk ved sensorfejl (sensor 1-3) og via API.
String thermostatState[NUM_THERMOSTATS] = {"Opvarmning", "Opvarmning", "Opvarmning"};

// --- Manuel overstyringstilstand ---
// Gyldige værdier: "pid", "off", "on", "percent", "auto"
String manualMode[NUM_THERMOSTATS]   = {"pid", "pid", "pid"};
double manualPercent[NUM_THERMOSTATS] = {0.0, 0.0, 0.0};

// --- Auto-regulering: grænse-delta ---
// Fuld varme når temp < (setpunkt - delta). PID når delta <= afstand <= 0. Slukket over setpunkt.
double autoThreshold[NUM_THERMOSTATS] = AUTO_THRESHOLDS;

// Grænser er delta-værdier i °C relativt til setpunkt (kun termostat 1-3)
double alarmLimit[NUM_THERMOSTATS]   = ALARM_LIMITS;
double warningLimit[NUM_THERMOSTATS] = WARNING_LIMITS;

// --- Display ---
TM1637Display display(DISPLAY_CLK, DISPLAY_DIO);
int selectedTemp = 0;

// --- Knap-debounce ---
const int debounceDelay = DEBOUNCE_DELAY_MS;
unsigned long lastDebounce[NUM_BUTTONS];
bool lastRead[NUM_BUTTONS];
bool buttonState[NUM_BUTTONS];

// --- Serial buffer ---
// Bruger et statisk char-array for at undgå heap-fragmentering fra String-objekter.
char serialBuffer[SERIAL_BUFFER_MAX + 1];
int  serialBufferLen = 0;
bool serialOverflow = false;  // Sættes ved buffer-overflow, ryddes ved næste newline

// --- Blink-tilstand ---
bool blinkState = false;
unsigned long lastBlink = 0;

// --- Sensor-knap: langt tryk / setpoint-visning ---
unsigned long sensorButtonPressedAt = 0;   // tidspunkt for tryk-ned
bool sensorButtonLongFired          = false; // forhindrer gentagen udløsning
bool showingSetpoint                = false; // display-tilstand: setpoint-visning
unsigned long setpointDisplayStart  = 0;    // hvornår setpoint-visning begyndte

// --- Setpoint edit-mode ---
// Aktiveres ved meget langt tryk (knappen holdes inde mens setpoint vises).
// I edit-mode blinker setpunktet og relæknap 1/2 justerer værdien ±1°C.
// Afsluttes ved et kort tryk på sensorknappen.
bool editingSetpoint     = false;  // er vi i edit-mode?
bool editBlinkState      = false;  // blink-tilstand for displayet i edit-mode
unsigned long lastEditBlink = 0;   // tidspunkt for sidste blink-skift
bool veryLongFired       = false;  // forhindrer gentagen aktivering af edit-mode

// --- Manuel overstyring (fuld varme) ---
// Når aktiv: alle termostater sættes til manualMode "on" (100% effekt).
// Ved deaktivering gendannes den tilstand der var gældende ved aktivering.
bool overrideActive = false;
String  overrideSnapshot_manualMode[NUM_THERMOSTATS];
double  overrideSnapshot_manualPercent[NUM_THERMOSTATS];

// Debounce for override-knap (separat — ikke i NUM_BUTTONS-arrayet)
unsigned long overrideLastDebounce = 0;
bool overrideLastRead    = HIGH;
bool overrideButtonState = HIGH;

// --- Tilstandsopdatering timer ---
unsigned long lastStateUpdate = 0;
#define STATE_UPDATE_INTERVAL_MS 1000


// =============================================================================
// SETUP
// =============================================================================

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);

  wdt_enable(WATCHDOG_TIMEOUT);

  // --- Relæer ---
  for (int i = 0; i < NUM_RELAYS; i++) {
    pinMode(relayPins[i],    OUTPUT);
    pinMode(relayButtons[i], INPUT_PULLUP);
    pinMode(relayLEDs[i],    OUTPUT);
    relayState[i] = false;
    updateRelay(i);
  }

  // --- Varmestyring og PID ---
  for (int i = 0; i < NUM_THERMOSTATS; i++) {
    pinMode(heatRelayPins[i], OUTPUT);
    digitalWrite(heatRelayPins[i], LOW);
    heatRelayState[i] = false;

    pids[i]->SetOutputLimits(0, windowSize[i]);
    pids[i]->SetMode(AUTOMATIC);
    windowStart[i] = millis();
  }

  // --- Termostat status-LED'er og varme-LED'er ---
  for (int i = 0; i < NUM_THERMOSTATS; i++) {
    pinMode(statusLedRed[i],    OUTPUT);
    pinMode(statusLedYellow[i], OUTPUT);
    pinMode(statusLedGreen[i],  OUTPUT);
    pinMode(heatLedPins[i],     OUTPUT);
    digitalWrite(statusLedRed[i],    LOW);
    digitalWrite(statusLedYellow[i], LOW);
    digitalWrite(statusLedGreen[i],  LOW);
    digitalWrite(heatLedPins[i],     LOW);
  }

  // --- Sensor-display og LEDs ---
  pinMode(sensorButton, INPUT_PULLUP);
  for (int i = 0; i < NUM_TEMPS; i++) {
    pinMode(sensorLEDs[i], OUTPUT);
  }
  updateSensorLEDs();

  // --- Manuel overstyring ---
  pinMode(overrideButton, INPUT_PULLUP);
  pinMode(overrideLed,    OUTPUT);
  digitalWrite(overrideLed, LOW);

  // --- TM1637 display ---
  display.setBrightness(DISPLAY_BRIGHTNESS);

  // --- MAX31865 PT100 sensorer ---
  // MAX31865_3WIRE eller MAX31865_2WIRE afhængig af din kobling.
  // De fleste breakout-boards leveres konfigureret til 2-leder.
  // Skift til MAX31865_3WIRE hvis du bruger 3-leder PT100-kabling.
  for (int i = 0; i < NUM_TEMPS; i++) {
    sensors[i].begin(MAX31865_2WIRE);
    temps[i] = NAN; // Ugyldig indtil første vellykkede aflæsning
  }

  // Første aflæsning med det samme (undgår NaN i startfasen)
  updateTemps();
}


// =============================================================================
// HOVEDLOOP
// =============================================================================

void loop() {
  wdt_reset();

  readOverrideButton();
  readSensorButton();
  readRelayButtons();
  updateTemps();            // Læs PT100-sensorer via MAX31865
  updateDisplay();
  updatePID();
  controlHeating();
  updateThermostatState();
  updateStatusLEDs();
  readSerial();
}


// =============================================================================
// TEMPERATURSENSORER — MAX31865 PT100
// =============================================================================

// Læs alle fire MAX31865-moduler periodisk (TEMP_READ_INTERVAL_MS).
// Ved sensorfejl (fault) ELLER temperatur uden for [TEMP_RANGE_MIN, TEMP_RANGE_MAX]:
//   - temps[i] sættes til NAN (ugyldig)
//   - sensorFault[i] = true, sensorFaultCode[i] = fault-register (0xFF ved rækkevidde-fejl)
//   - Sensor 1-3: sætter thermostatState til "HW Alarm" → varme slukkes
//   - Sensor 4: fejl rapporteres kun i JSON (sensor4.fault = true)
// Ved gyldig aflæsning:
//   - temps[i] opdateres
//   - sensorFault[i] nulstilles
//   - "HW Alarm" sat af sensorfejl fjernes (men ikke manuelt sat HW Alarm)
void updateTemps() {
  unsigned long now = millis();
  if (now - lastTempRead < TEMP_READ_INTERVAL_MS) return;
  lastTempRead = now;

  for (int i = 0; i < NUM_TEMPS; i++) {
    uint8_t fault = sensors[i].readFault();

    if (fault) {
      // Sensorfejl — registrér og sæt temp til NAN
      sensors[i].clearFault();
      sensorFault[i]     = true;
      sensorFaultCode[i] = fault;
      temps[i]           = NAN;

      // Termostat 1-3: sæt HW Alarm (sensor 4 har ingen termostat)
      if (i < NUM_THERMOSTATS) {
        thermostatState[i] = "HW Alarm";
      }

    } else {
      // Gyldig aflæsning fra MAX31865 — tjek om temperaturen er inden for gyldigt interval.
      // Gem den tidligere fejl-tilstand FØR vi evt. nulstiller sensorFault[i],
      // så vi kan skelne sensor-udløst HW Alarm fra manuelt sat HW Alarm via API.
      bool wasFault = sensorFault[i];

      float t = sensors[i].temperature(MAX31865_RNOMINAL, MAX31865_RREF);

      if (t < TEMP_RANGE_MIN || t > TEMP_RANGE_MAX) {
        // Temperatur uden for gyldigt område — behandles som HW-fejl.
        // Fault-kode 0xFF bruges som markør for rækkevidde-fejl (ikke en MAX31865-fejlkode).
        sensorFault[i]     = true;
        sensorFaultCode[i] = 0xFF;
        temps[i]           = NAN;

        if (i < NUM_THERMOSTATS) {
          thermostatState[i] = "HW Alarm";
        }

      } else {
        // Temperatur er gyldig
        temps[i]           = t;
        sensorFault[i]     = false;
        sensorFaultCode[i] = 0;

        // Ryd kun HW Alarm hvis den blev sat af en sensorfejl (wasFault == true).
        // En manuel HW Alarm (sat via API uden aktiv sensorfejl) bevares.
        if (i < NUM_THERMOSTATS && thermostatState[i] == "HW Alarm" && wasFault) {
          // Nulstil til "Run" — updateThermostatState() beregner korrekt tilstand
          // ved næste sekund-opdatering.
          thermostatState[i] = "Run";
        }
      }
    }
  }
}


// =============================================================================
// TERMOSTAT STATUS-LED'ER
// =============================================================================

// Opdater status-LED'er for alle termostater baseret på thermostatState[]
// og manualMode[], samt varme-LED'er baseret på heatRelayState[].
//
// PID-tilstand (manualMode == "pid"):
//   Opvarmning → Grøn blinker
//   Run        → Grøn lyser
//   Advarsel   → Gul lyser
//   Alarm      → Rød lyser
//   HW Alarm   → Rød blinker
//
// Manuel tilstand (manualMode != "pid"):
//   off        → Alle LED'er slukket
//   on         → Grøn lyser + Gul blinker
//   percent    → Grøn lyser + Gul blinker
//
// Alarm og HW Alarm har altid højeste prioritet uanset manuel tilstand.
void updateStatusLEDs() {
  unsigned long now = millis();
  if (now - lastBlink >= STATUS_BLINK_INTERVAL_MS) {
    blinkState = !blinkState;
    lastBlink = now;
  }

  for (int i = 0; i < NUM_THERMOSTATS; i++) {

    digitalWrite(statusLedRed[i],    LOW);
    digitalWrite(statusLedYellow[i], LOW);
    digitalWrite(statusLedGreen[i],  LOW);

    if (thermostatState[i] == "HW Alarm") {
      digitalWrite(statusLedRed[i], blinkState ? HIGH : LOW);

    } else if (thermostatState[i] == "Alarm") {
      digitalWrite(statusLedRed[i], HIGH);

    } else if (manualMode[i] == "off") {
      // Ingen indikation — varme bevidst slukket

    } else if (manualMode[i] == "on" || manualMode[i] == "percent") {
      digitalWrite(statusLedGreen[i],  HIGH);
      digitalWrite(statusLedYellow[i], blinkState ? HIGH : LOW);

    } else {
      // PID-tilstand
      if (thermostatState[i] == "Opvarmning") {
        digitalWrite(statusLedGreen[i], blinkState ? HIGH : LOW);
      } else if (thermostatState[i] == "Run") {
        digitalWrite(statusLedGreen[i], HIGH);
      } else if (thermostatState[i] == "Advarsel") {
        digitalWrite(statusLedYellow[i], HIGH);
      }
    }

    digitalWrite(heatLedPins[i], heatRelayState[i] ? HIGH : LOW);
  }
}


// =============================================================================
// DISPLAY (TM1637)
// =============================================================================

// Vis den valgte sensors temperatur med 1 decimal.
// Viser "----" hvis sensoren er i fejltilstand (NAN).
//
// Tilstande:
//   Normal       — viser aktuel temperatur
//   Langt tryk   — viser setpunkt i SETPOINT_DISPLAY_MS ms, derefter tilbage til normal
//   Edit-mode    — viser setpunkt blinkende indtil sensorknappen trykkes
//                  Sensor 4 understøtter ikke edit-mode (ingen termostat)
void updateDisplay() {
  unsigned long now = millis();

  // --- Edit-mode: setpunkt blinker ---
  if (editingSetpoint) {
    if (now - lastEditBlink >= EDIT_BLINK_MS) {
      editBlinkState = !editBlinkState;
      lastEditBlink  = now;
    }

    if (!editBlinkState) {
      display.clear();
      return;
    }

    // Vis setpunkt (heltal i edit-mode — ingen decimal)
    long sp = (long)round(setpoint[selectedTemp]);
    if (sp < 0) {
      uint8_t segs[4] = {SEG_G, 0x00,
                         display.encodeDigit((abs(sp) / 10) % 10),
                         display.encodeDigit(abs(sp) % 10)};
      display.setSegments(segs);
    } else {
      display.showNumberDec((int)sp, false);
    }
    return;
  }

  // --- Setpoint-visning efter langt tryk (uden edit-mode) ---
  if (showingSetpoint) {
    if (!editingSetpoint && (now - setpointDisplayStart) >= SETPOINT_DISPLAY_MS) {
      // Timeout — tilbage til normal temperaturvisning
      showingSetpoint = false;
    } else {
      if (selectedTemp < NUM_THERMOSTATS) {
        long spDisplay = (long)round(abs(setpoint[selectedTemp]) * 10);
        if (setpoint[selectedTemp] < 0) {
          uint8_t segs[4];
          segs[0] = SEG_G;
          segs[1] = display.encodeDigit((spDisplay / 100) % 10);
          segs[2] = display.encodeDigit((spDisplay / 10)  % 10);
          segs[3] = display.encodeDigit(spDisplay % 10);
          segs[2] |= 0x80;
          display.setSegments(segs);
        } else {
          display.showNumberDecEx(spDisplay, 0b00100000, false);
        }
      } else {
        // Sensor 4: ingen termostat — vis "----"
        uint8_t dashes[4] = {SEG_G, SEG_G, SEG_G, SEG_G};
        display.setSegments(dashes);
      }
      return;
    }
  }

  // --- Normal temperaturvisning ---
  if (isnan(temps[selectedTemp])) {
    uint8_t dashes[4] = {SEG_G, SEG_G, SEG_G, SEG_G};
    display.setSegments(dashes);
    return;
  }

  float temp = temps[selectedTemp];
  long tempDisplay = (long)round(abs(temp) * 10);

  if (temp < 0) {
    uint8_t segs[4];
    segs[0] = SEG_G;
    segs[1] = display.encodeDigit((tempDisplay / 100) % 10);
    segs[2] = display.encodeDigit((tempDisplay / 10)  % 10);
    segs[3] = display.encodeDigit(tempDisplay % 10);
    segs[2] |= 0x80;
    display.setSegments(segs);
  } else {
    display.showNumberDecEx(tempDisplay, 0b00100000, false);
  }
}

// Tænd LED for den aktive sensor, sluk de øvrige
void updateSensorLEDs() {
  for (int i = 0; i < NUM_TEMPS; i++) {
    digitalWrite(sensorLEDs[i], (i == selectedTemp) ? HIGH : LOW);
  }
}


// =============================================================================
// MANUEL OVERSTYRING — FULD VARME
// =============================================================================

// Gem nuværende manualMode/manualPercent og sæt alle termostater til "on" (100%).
// Kaldes ved aktivering via knap eller JSON.
void activateOverride() {
  if (overrideActive) return;
  for (int i = 0; i < NUM_THERMOSTATS; i++) {
    overrideSnapshot_manualMode[i]    = manualMode[i];
    overrideSnapshot_manualPercent[i] = manualPercent[i];
    manualMode[i] = "on";
  }
  overrideActive = true;
  digitalWrite(overrideLed, HIGH);
}

// Gendan manualMode/manualPercent fra snapshot og sluk LED.
// Kaldes ved deaktivering via knap eller JSON.
void deactivateOverride() {
  if (!overrideActive) return;
  for (int i = 0; i < NUM_THERMOSTATS; i++) {
    manualMode[i]    = overrideSnapshot_manualMode[i];
    manualPercent[i] = overrideSnapshot_manualPercent[i];
    // Hvis PID genaktiveres: nulstil output så det ikke starter fra en forældet værdi
    if (manualMode[i] == "pid" && !isnan(temps[i])) {
      pidInput[i] = temps[i];
      pids[i]->SetMode(MANUAL);
      pidOutput[i] = 0;
      pids[i]->SetMode(AUTOMATIC);
    }
  }
  overrideActive = false;
  digitalWrite(overrideLed, LOW);
}

// Læs override-knap med debounce — toggle ved hvert tryk.
void readOverrideButton() {
  int reading = digitalRead(overrideButton);
  unsigned long now = millis();

  if (reading != overrideLastRead) {
    overrideLastDebounce = now;
  }

  if ((now - overrideLastDebounce) > DEBOUNCE_DELAY_MS) {
    if (reading != overrideButtonState) {
      overrideButtonState = reading;
      if (overrideButtonState == LOW) {
        if (overrideActive) {
          deactivateOverride();
        } else {
          activateOverride();
        }
      }
    }
  }

  overrideLastRead = reading;
}


// =============================================================================
// KNAPPER OG DEBOUNCE
// =============================================================================

// Håndterer sensor-vælger-knappen med kort, langt og meget langt tryk:
//   Kort tryk        → skifter til næste sensor
//   Langt tryk       → viser setpoint for aktuel termostat (LONG_PRESS_MS)
//   Meget langt tryk → aktiverer edit-mode: setpoint blinker, justerbart via relæknap 1/2
//                      (knappen holdes inde til VERY_LONG_PRESS_MS)
//   Tryk i edit-mode → afslutter edit-mode og gemmer setpunktet
void readSensorButton() {
  int reading = digitalRead(sensorButton);
  unsigned long now = millis();

  if (reading != lastRead[0]) {
    lastDebounce[0] = now;
  }

  if ((now - lastDebounce[0]) > debounceDelay) {
    if (reading != buttonState[0]) {
      buttonState[0] = reading;

      if (buttonState[0] == LOW) {
        // Knap trykket ned
        sensorButtonPressedAt = now;
        sensorButtonLongFired = false;
        veryLongFired         = false;

      } else {
        // Knap sluppet
        if (editingSetpoint && !veryLongFired) {
          // Selvstændigt tryk i edit-mode (ikke det der aktiverede edit-mode): afslut
          editingSetpoint = false;
          showingSetpoint = false;
          if (selectedTemp < NUM_THERMOSTATS) {
            pids[selectedTemp]->SetTunings(kp[selectedTemp], ki[selectedTemp], kd[selectedTemp]);
          }
        } else if (!editingSetpoint && !sensorButtonLongFired) {
          // Kort tryk (uden for edit-mode): skift sensor
          selectedTemp = (selectedTemp + 1) % NUM_TEMPS;
          updateSensorLEDs();
        }
        sensorButtonLongFired = false;
        veryLongFired         = false;
      }
    }

    // Mens knappen holdes nede: tjek for langt og meget langt tryk
    if (buttonState[0] == LOW) {
      unsigned long held = now - sensorButtonPressedAt;

      // Meget langt tryk → edit-mode (kun for termostat 1-3, ikke sensor 4)
      if (!veryLongFired && held >= VERY_LONG_PRESS_MS && selectedTemp < NUM_THERMOSTATS) {
        veryLongFired   = true;
        editingSetpoint = true;
        showingSetpoint = true;
        lastEditBlink   = now;
        editBlinkState  = true;
      }
      // Langt tryk → vis setpoint (kun hvis edit-mode ikke allerede er aktiv)
      else if (!sensorButtonLongFired && !editingSetpoint && held >= LONG_PRESS_MS) {
        sensorButtonLongFired = true;
        showingSetpoint       = true;
        setpointDisplayStart  = now;
      }
    }
  }

  lastRead[0] = reading;
}

void readRelayButtons() {
  for (int i = 0; i < NUM_RELAYS; i++) {
    int reading = digitalRead(relayButtons[i]);

    if (reading != lastRead[i + 1]) {
      lastDebounce[i + 1] = millis();
    }

    if ((millis() - lastDebounce[i + 1]) > debounceDelay) {
      if (reading != buttonState[i + 1]) {
        buttonState[i + 1] = reading;
        if (buttonState[i + 1] == LOW) {

          if (editingSetpoint && selectedTemp < NUM_THERMOSTATS) {
            // Edit-mode: knap 1 = +1°C, knap 2 = -1°C — relæet toggler IKKE
            if (i == 0) {
              setpoint[selectedTemp] += 1.0;
            } else if (i == 1) {
              setpoint[selectedTemp] -= 1.0;
            } else {
              toggleRelay(i); // Knap 3 og 4 virker normalt
            }
          } else {
            toggleRelay(i);
          }

        }
      }
    }
    lastRead[i + 1] = reading;
  }
}


// =============================================================================
// RELÆSTYRING
// =============================================================================

void toggleRelay(int i) {
  relayState[i] = !relayState[i];
  updateRelay(i);
}

void setRelay(int i, bool st) {
  relayState[i] = st;
  updateRelay(i);
}

void updateRelay(int i) {
  digitalWrite(relayPins[i], relayState[i] ? HIGH : LOW);
  digitalWrite(relayLEDs[i], relayState[i] ? HIGH : LOW);
}


// =============================================================================
// PID-BEREGNING
// =============================================================================

// Opdater PID-input og beregn output.
// Springes over hvis:
//   - Manuel tilstand er aktiv (undtagen "auto" som bruger PID), ELLER
//   - Sensoren er i fejltilstand (NAN) — undgår ukontrolleret PID-adfærd
void updatePID() {
  for (int i = 0; i < NUM_THERMOSTATS; i++) {
    if (manualMode[i] != "pid" && manualMode[i] != "auto") continue;
    if (isnan(temps[i]))       continue; // Ingen gyldig temperatur — spring over
    pidInput[i] = temps[i];
    pids[i]->Compute();
  }
}


// =============================================================================
// VARMESTYRING OG TERMOSTAT-STATUS
// =============================================================================

// Styrer varmerelæer via PID (Time-Proportional PWM) eller manuel tilstand.
//
// Prioritetsrækkefølge:
//   1. Manuel tilstand (manualMode != "pid") — bypasser PID og HW Alarm
//   2. HW Alarm (inkl. sensorfejl) — slukker varmen
//   3. PID Time-Proportional PWM
void controlHeating() {
  unsigned long now = millis();

  for (int i = 0; i < NUM_THERMOSTATS; i++) {

    if (now - windowStart[i] >= windowSize[i]) {
      windowStart[i] = now;
    }

    unsigned long elapsed = now - windowStart[i];

    if (manualMode[i] == "off") {
      digitalWrite(heatRelayPins[i], LOW);
      heatRelayState[i] = false;
      continue;

    } else if (manualMode[i] == "on") {
      digitalWrite(heatRelayPins[i], HIGH);
      heatRelayState[i] = true;
      continue;

    } else if (manualMode[i] == "percent") {
      unsigned long onTime = (unsigned long)(manualPercent[i] / 100.0 * windowSize[i]);
      if (elapsed < onTime) {
        digitalWrite(heatRelayPins[i], HIGH);
        heatRelayState[i] = true;
      } else {
        digitalWrite(heatRelayPins[i], LOW);
        heatRelayState[i] = false;
      }
      continue;

    } else if (manualMode[i] == "auto") {
      // Auto: temp < (setpunkt - delta) → 100%, imellem → PID, over setpunkt → slukket
      if (thermostatState[i] == "HW Alarm" || isnan(temps[i])) {
        digitalWrite(heatRelayPins[i], LOW);
        heatRelayState[i] = false;
      } else if ((double)temps[i] > setpoint[i]) {
        // Over setpunkt: varme slukket
        digitalWrite(heatRelayPins[i], LOW);
        heatRelayState[i] = false;
      } else if ((double)temps[i] < (setpoint[i] - autoThreshold[i])) {
        // Under grænse (setpunkt - delta): fuld varme (100%)
        digitalWrite(heatRelayPins[i], HIGH);
        heatRelayState[i] = true;
      } else {
        // Mellem grænse og setpunkt: PID time-proportional
        if (pidOutput[i] > 0.0 && (unsigned long)pidOutput[i] > elapsed) {
          digitalWrite(heatRelayPins[i], HIGH);
          heatRelayState[i] = true;
        } else {
          digitalWrite(heatRelayPins[i], LOW);
          heatRelayState[i] = false;
        }
      }
      continue;
    }

    // PID-gren
    if (thermostatState[i] == "HW Alarm") {
      digitalWrite(heatRelayPins[i], LOW);
      heatRelayState[i] = false;
      continue;
    }

    // Guard: pidOutput kan være negativ ved PID-initialisering — cast af
    // negativ double til unsigned long giver et meget stort tal og
    // vil tænde relæet ukontrolleret i et fuldt vindue.
    if (pidOutput[i] > 0.0 && (unsigned long)pidOutput[i] > elapsed) {
      digitalWrite(heatRelayPins[i], HIGH);
      heatRelayState[i] = true;
    } else {
      digitalWrite(heatRelayPins[i], LOW);
      heatRelayState[i] = false;
    }
  }
}


// =============================================================================
// TERMOSTAT TILSTANDSOPDATERING
// =============================================================================

// Opdater thermostatState[] én gang pr. sekund.
// Sensorfejl sætter HW Alarm direkte i updateTemps() uden at vente her.
// HW Alarm sat via API ryddes kun via API (setState: "clear").
//
// Tilstandsprioritering (høj → lav):
//   HW Alarm   — sensorfejl eller manuelt sat via API
//   Alarm      — temp > setpoint + alarmLimit (overophedning)
//   Opvarmning — temp < setpoint - alarmLimit (langt under setpunkt, fx efter setpoint-hævning)
//   Advarsel   — temp afviger mere end warningLimit fra setpunkt
//   Run        — temp inden for warningLimit
void updateThermostatState() {
  unsigned long now = millis();
  if (now - lastStateUpdate < STATE_UPDATE_INTERVAL_MS) return;
  lastStateUpdate = now;

  for (int i = 0; i < NUM_THERMOSTATS; i++) {

    // HW Alarm ryddes ikke herfra
    if (thermostatState[i] == "HW Alarm") continue;

    // Sensor i fejltilstand — sæt HW Alarm (burde allerede være sat af updateTemps)
    if (isnan(temps[i])) {
      thermostatState[i] = "HW Alarm";
      continue;
    }

    double diff = temps[i] - setpoint[i];

    if (diff > alarmLimit[i]) {
      thermostatState[i] = "Alarm";

    } else if (-diff > alarmLimit[i]) {
      // Temp er mere end alarmLimit under setpunkt — fx efter setpoint-hævning.
      thermostatState[i] = "Opvarmning";

    } else if (abs(diff) > warningLimit[i]) {
      thermostatState[i] = "Advarsel";

    } else {
      thermostatState[i] = "Run";
    }
  }
}


// =============================================================================
// SERIAL JSON KOMMUNIKATION
// =============================================================================

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (!serialOverflow) {
        serialBuffer[serialBufferLen] = '\0';
        handleJson(serialBuffer);  // null-termineret i serialBuffer[serialBufferLen]
      }
      serialBufferLen = 0;
      serialOverflow = false;
    } else if (c != '\r') {  // ignorer CR fra terminaler der sender CRLF
      if (serialBufferLen < SERIAL_BUFFER_MAX) {
        serialBuffer[serialBufferLen++] = c;
      } else {
        // Buffer fuld — sæt flag og ignorer resten af denne kommando.
        // Bufferen ryddes først ved newline, så næste kommando modtages korrekt.
        serialOverflow = true;
      }
    }
  }
}

void sendError(const char* msg) {
  StaticJsonDocument<200> doc;
  doc["success"] = false;
  doc["error"]   = msg;
  serializeJson(doc, Serial);
  Serial.println();
}

// Byg og send fuld systemstatus som JSON.
//
// Svarstruktur:
// {
//   "success": true,
//   "status": {
//     "uptime": <ms siden opstart>,
//     "selectedSensor": <1-4>
//   },
//   "relays": [bool, bool, bool, bool],
//   "thermostat1": {
//     "temperature":   <float, 1 decimal> | null (ved sensorfejl),
//     "setpoint":      <float>,
//     "heater":        <bool>,
//     "state":         <string>,
//     "fault":         <bool>,
//     "faultCode":     <int>  (0 = ingen fejl),
//     "kp":            <float>,
//     "ki":            <float>,
//     "kd":            <float>,
//     "alarmLimit":    <float>,
//     "warningLimit":  <float>,
//     "windowSize":    <ulong>,
//     "manualMode":    <string>,
//     "manualPercent": <float>
//   },
//   "thermostat2": { ... },
//   "thermostat3": { ... },
//   "sensor4": {
//     "temperature": <float, 1 decimal> | null (ved sensorfejl),
//     "fault":       <bool>,
//     "faultCode":   <int>
//   }
// }
void sendStatus() {
  // Dokumentstørrelse øget til 2048 for sensor4-objekt, fault-felter og heatPercent
  StaticJsonDocument<2048> doc;
  doc["success"] = true;

  // --- Systemstatus ---
  JsonObject status = doc.createNestedObject("status");
  status["uptime"]         = millis();
  status["selectedSensor"] = selectedTemp + 1;

  // --- Relæer ---
  JsonArray relays = doc.createNestedArray("relays");
  for (int i = 0; i < NUM_RELAYS; i++) {
    relays.add(relayState[i]);
  }

  // --- Termostat 1-3 ---
  const char* thermostatKeys[NUM_THERMOSTATS] = {"thermostat1", "thermostat2", "thermostat3"};

  for (int i = 0; i < NUM_THERMOSTATS; i++) {
    JsonObject t = doc.createNestedObject(thermostatKeys[i]);

    // Temperatur: null ved sensorfejl, ellers 1 decimal
    if (isnan(temps[i])) {
      t["temperature"] = (char*)nullptr;  // JSON null
    } else {
      float rounded = round(temps[i] * 10.0) / 10.0;
      t["temperature"] = serialized(String(rounded, 1));
    }

    t["setpoint"]     = setpoint[i];
    t["heater"]       = heatRelayState[i];
    t["state"]        = thermostatState[i];

    // Sensorstatus
    t["fault"]        = sensorFault[i];
    t["faultCode"]    = sensorFaultCode[i];

    // PID-parametre
    t["kp"]           = kp[i];
    t["ki"]           = ki[i];
    t["kd"]           = kd[i];

    // Grænser og PWM-vindue
    t["alarmLimit"]   = alarmLimit[i];
    t["warningLimit"] = warningLimit[i];
    t["windowSize"]   = windowSize[i];

    // Manuel overstyringstilstand
    t["manualMode"]    = manualMode[i];
    t["manualPercent"] = serialized(String(manualPercent[i], 1));

    // Aktuel varmeeffekt i procent (0.0 – 100.0)
    float heatPct = 0.0;
    if (manualMode[i] == "on") {
      heatPct = 100.0;
    } else if (manualMode[i] == "percent") {
      heatPct = (float)manualPercent[i];
    } else if (manualMode[i] == "pid" && thermostatState[i] != "HW Alarm") {
      heatPct = (float)(pidOutput[i] / (double)windowSize[i] * 100.0);
      if (heatPct < 0.0)   heatPct = 0.0;
      if (heatPct > 100.0) heatPct = 100.0;
    } else if (manualMode[i] == "auto" && thermostatState[i] != "HW Alarm" && !isnan(temps[i])) {
      if ((double)temps[i] > setpoint[i]) {
        heatPct = 0.0;
      } else if ((double)temps[i] < (setpoint[i] - autoThreshold[i])) {
        heatPct = 100.0;
      } else {
        heatPct = (float)(pidOutput[i] / (double)windowSize[i] * 100.0);
        if (heatPct < 0.0)   heatPct = 0.0;
        if (heatPct > 100.0) heatPct = 100.0;
      }
    }
    t["heatPercent"]   = serialized(String(heatPct, 1));
    t["autoThreshold"] = autoThreshold[i];
  }

  // --- Sensor 4 (ekstra/ambient) ---
  // Ingen PID, ingen alarm/advarsel — kun temperatur og fejlstatus
  JsonObject s4 = doc.createNestedObject("sensor4");
  if (isnan(temps[3])) {
    s4["temperature"] = (char*)nullptr;
  } else {
    float rounded = round(temps[3] * 10.0) / 10.0;
    s4["temperature"] = serialized(String(rounded, 1));
  }
  s4["fault"]     = sensorFault[3];
  s4["faultCode"] = sensorFaultCode[3];

  // --- Manuel overstyring ---
  doc["override"] = overrideActive;

  serializeJson(doc, Serial);
  Serial.println();
}

// =============================================================================
// LYSSHOW — LED- OG DISPLAY-SELVTEST
// =============================================================================
//
// Kører en sekventiel test af alle LED-grupper og TM1637-displayet.
// Kan kaldes via JSON: { "command": "lysshow" }
//
// Sekvens:
//   1. Alle LED'er tændes samtidig  (alles øjne åbner sig)
//   2. Knight Rider-sweep over relæ-LED'erne  (frem og tilbage)
//   3. Sensor-LED'erne løber igennem én ad gangen
//   4. Termostat-LED'er: grøn → gul → rød pr. termostat (én ad gangen)
//   5. Varme-LED'er løber igennem
//   6. Display tæller 0-9, viser derefter "bRYG" og "HUS"
//   7. Alle LED'er slukkes, og normal drift genoptages
//
// Relæer og varmerelæer berøres IKKE — kun LED-udgange styres.
// Watchdog nulstilles løbende så sekvensen ikke trigger en genstart.
// Gemmer og gendanner selectedTemp efter sekvensen.
// =============================================================================

void runLysshow() {
  const int STEP = 120;   // ms pr. trin i animationer
  const int PAUSE = 60;   // ms pause mellem grupper

  // --- Gem tilstand der ændres ---
  int savedSelectedTemp = selectedTemp;

  // ---- 1. Alle LED'er tændes på én gang ----
  for (int i = 0; i < NUM_RELAYS;     i++) digitalWrite(relayLEDs[i],       HIGH);
  for (int i = 0; i < NUM_TEMPS;      i++) digitalWrite(sensorLEDs[i],      HIGH);
  for (int i = 0; i < NUM_THERMOSTATS; i++) {
    digitalWrite(statusLedRed[i],    HIGH);
    digitalWrite(statusLedYellow[i], HIGH);
    digitalWrite(statusLedGreen[i],  HIGH);
    digitalWrite(heatLedPins[i],     HIGH);
  }
  display.setBrightness(DISPLAY_BRIGHTNESS);
  uint8_t allOn[4] = {0xFF, 0xFF, 0xFF, 0xFF};
  display.setSegments(allOn);
  delay(600);
  wdt_reset();

  // Sluk alt igen inden animationerne starter
  for (int i = 0; i < NUM_RELAYS;     i++) digitalWrite(relayLEDs[i],       LOW);
  for (int i = 0; i < NUM_TEMPS;      i++) digitalWrite(sensorLEDs[i],      LOW);
  for (int i = 0; i < NUM_THERMOSTATS; i++) {
    digitalWrite(statusLedRed[i],    LOW);
    digitalWrite(statusLedYellow[i], LOW);
    digitalWrite(statusLedGreen[i],  LOW);
    digitalWrite(heatLedPins[i],     LOW);
  }
  display.clear();
  delay(PAUSE);
  wdt_reset();

  // ---- 2. Knight Rider over relæ-LED'er (frem + tilbage) ----
  for (int rep = 0; rep < 2; rep++) {
    // Frem
    for (int i = 0; i < NUM_RELAYS; i++) {
      digitalWrite(relayLEDs[i], HIGH);
      delay(STEP);
      digitalWrite(relayLEDs[i], LOW);
      wdt_reset();
    }
    // Tilbage
    for (int i = NUM_RELAYS - 1; i >= 0; i--) {
      digitalWrite(relayLEDs[i], HIGH);
      delay(STEP);
      digitalWrite(relayLEDs[i], LOW);
      wdt_reset();
    }
  }
  delay(PAUSE);

  // ---- 3. Sensor-LED'er løber igennem ----
  for (int rep = 0; rep < 2; rep++) {
    for (int i = 0; i < NUM_TEMPS; i++) {
      digitalWrite(sensorLEDs[i], HIGH);
      delay(STEP);
      digitalWrite(sensorLEDs[i], LOW);
      wdt_reset();
    }
  }
  delay(PAUSE);

  // ---- 4. Termostat status-LED'er: rød → gul → grøn pr. termostat, én ad gangen ----
  for (int i = 0; i < NUM_THERMOSTATS; i++) {
    digitalWrite(statusLedRed[i],    HIGH); delay(STEP); wdt_reset();
    digitalWrite(statusLedRed[i],    LOW);
    digitalWrite(statusLedYellow[i], HIGH); delay(STEP); wdt_reset();
    digitalWrite(statusLedYellow[i], LOW);
    digitalWrite(statusLedGreen[i],  HIGH); delay(STEP); wdt_reset();
    digitalWrite(statusLedGreen[i],  LOW);
    delay(PAUSE);
  }

  // ---- 5. Varme-LED'er løber igennem ----
  for (int rep = 0; rep < 2; rep++) {
    for (int i = 0; i < NUM_THERMOSTATS; i++) {
      digitalWrite(heatLedPins[i], HIGH);
      delay(STEP);
      digitalWrite(heatLedPins[i], LOW);
      wdt_reset();
    }
  }
  delay(PAUSE);

  // ---- 6. Display: tæller 0 til 9, derefter "bRYG" og "HUS " ----
  for (int d = 0; d <= 9; d++) {
    display.showNumberDec(d, false);
    delay(120);
    wdt_reset();
  }
  delay(200);

  // Segment-koder: a=0x01 b=0x02 c=0x04 d=0x08 e=0x10 f=0x20 g=0x40
  // "bRYG"
  uint8_t segB = 0x7F;  // B (= 8): a b c d e f g
  uint8_t segR = 0x77;  // R (= A): a b c e f g
  uint8_t segY = 0x6E;  // Y: b c d f g
  uint8_t segG = 0x3D;  // G: a c d e f
  uint8_t bryg[4] = {segB, segR, segY, segG};
  display.setSegments(bryg);
  delay(1500);
  wdt_reset();

  display.clear();
  delay(300);

  // "HUS "  (fjerde ciffer tomt — displayet er 4-cifret)
  uint8_t segH2 = 0x76;  // H: b c e f g
  uint8_t segU  = 0x3E;  // U: b c d e f
  uint8_t segS  = 0x6D;  // S: a c d f g  (= 5)
  uint8_t hus[4] = {segH2, segU, segS, 0x00};
  display.setSegments(hus);
  delay(1500);
  wdt_reset();

  // ---- 7. Sluk alt og gendan normal tilstand ----
  display.clear();
  for (int i = 0; i < NUM_RELAYS;     i++) digitalWrite(relayLEDs[i],       LOW);
  for (int i = 0; i < NUM_TEMPS;      i++) digitalWrite(sensorLEDs[i],      LOW);
  for (int i = 0; i < NUM_THERMOSTATS; i++) {
    digitalWrite(statusLedRed[i],    LOW);
    digitalWrite(statusLedYellow[i], LOW);
    digitalWrite(statusLedGreen[i],  LOW);
    digitalWrite(heatLedPins[i],     LOW);
  }

  // Gendan sensor-valg og relæ-LED'er
  selectedTemp = savedSelectedTemp;
  updateSensorLEDs();
  for (int i = 0; i < NUM_RELAYS; i++) updateRelay(i);

  wdt_reset();
}


// Parse og behandl en JSON-kommando modtaget på serial.
void handleJson(const char* json) {
  StaticJsonDocument<512> doc;
  DeserializationError error = deserializeJson(doc, json);
  if (error) { sendError("Invalid JSON"); return; }

  // Kommando-opslagstabel: brug ArduinoJson == direkte (undgår
  // at udtrække const char* som kan være NULL i visse ArduinoJson-versioner).

  // --- lysshow ---
  if (doc["command"] == "lysshow") {
    runLysshow();
    sendStatus();
    return;
  }

  // --- status ---
  if (doc["command"] == "status") {
    sendStatus();
    return;
  }

  // --- setRelay: { "command": "setRelay", "relay": 1-4, "state": true/false } ---
  if (doc["command"] == "setRelay") {
    if (!doc.containsKey("relay") || !doc.containsKey("state")) { sendError("Missing relay/state"); return; }
    int r   = doc["relay"].as<int>();
    bool st = doc["state"].as<bool>();
    if (r < 1 || r > NUM_RELAYS) { sendError("Invalid relay"); return; }
    setRelay(r - 1, st);
    sendStatus();
    return;
  }

  // --- selectSensor: { "command": "selectSensor", "sensor": 1-4 } ---
  if (doc["command"] == "selectSensor") {
    if (!doc.containsKey("sensor")) { sendError("Missing sensor"); return; }
    int s = doc["sensor"].as<int>();
    if (s < 1 || s > NUM_TEMPS) { sendError("Invalid sensor"); return; }
    selectedTemp = s - 1;
    updateSensorLEDs();
    sendStatus();
    return;
  }

  // --- setPID: { "command": "setPID", "thermostat": 1-3, "setpoint": float (valgfri),
  //              "kp": float, "ki": float, "kd": float, "windowSize": ulong } ---
  // Alle felter undtagen "thermostat" er valgfrie — uangivne værdier forbliver uændrede.
  if (doc["command"] == "setPID") {
    if (!doc.containsKey("thermostat")) { sendError("Missing thermostat"); return; }
    int t = doc["thermostat"].as<int>() - 1;
    if (t < 0 || t >= NUM_THERMOSTATS) { sendError("Invalid thermostat"); return; }

    if (doc.containsKey("setpoint")) {
      setpoint[t] = doc["setpoint"].as<double>();
    }

    if (doc.containsKey("kp")) {
      if (doc["kp"].as<double>() < 0) { sendError("Invalid kp"); return; }
      kp[t] = doc["kp"].as<double>();
    }
    if (doc.containsKey("ki")) {
      if (doc["ki"].as<double>() < 0) { sendError("Invalid ki"); return; }
      ki[t] = doc["ki"].as<double>();
    }
    if (doc.containsKey("kd")) {
      if (doc["kd"].as<double>() < 0) { sendError("Invalid kd"); return; }
      kd[t] = doc["kd"].as<double>();
    }
    if (doc.containsKey("windowSize")) {
      windowSize[t] = doc["windowSize"].as<unsigned long>();
      pids[t]->SetOutputLimits(0, windowSize[t]);
    }

    pids[t]->SetTunings(kp[t], ki[t], kd[t]);
    sendStatus();
    return;
  }

  // --- setLimits: { "command": "setLimits", "thermostat": 1-3,
  //                 "alarm": float, "warning": float } ---
  if (doc["command"] == "setLimits") {
    if (!doc.containsKey("thermostat")) { sendError("Missing thermostat"); return; }
    int t = doc["thermostat"].as<int>() - 1;
    if (t < 0 || t >= NUM_THERMOSTATS) { sendError("Invalid thermostat"); return; }
    if (doc.containsKey("alarm"))   alarmLimit[t]   = doc["alarm"].as<double>();
    if (doc.containsKey("warning")) warningLimit[t] = doc["warning"].as<double>();
    sendStatus();
    return;
  }

  // --- setState: { "command": "setState", "thermostat": 1-3,
  //                "state": "HW Alarm"|"clear" } ---
  // Bruges til at sætte og nulstille "HW Alarm" manuelt via API.
  if (doc["command"] == "setState") {
    if (!doc.containsKey("thermostat") || !doc.containsKey("state")) { sendError("Missing thermostat/state"); return; }
    int t = doc["thermostat"].as<int>() - 1;
    if (t < 0 || t >= NUM_THERMOSTATS) { sendError("Invalid thermostat"); return; }
    if (doc["state"] != "HW Alarm" && doc["state"] != "clear") {
      sendError("Invalid state"); return;
    }
    if (doc["state"] == "clear") {
      thermostatState[t] = "Run"; // Overskrives af updateThermostatState() ved næste sekund
    } else {
      thermostatState[t] = "HW Alarm";
    }
    sendStatus();
    return;
  }

  // --- setManual: { "command": "setManual", "thermostat": 1-3,
  //                 "mode": "pid"|"off"|"on"|"percent", "percent": 0-100 } ---
  if (doc["command"] == "setManual") {
    if (!doc.containsKey("thermostat") || !doc.containsKey("mode")) { sendError("Missing thermostat/mode"); return; }
    int t = doc["thermostat"].as<int>() - 1;
    if (t < 0 || t >= NUM_THERMOSTATS) { sendError("Invalid thermostat"); return; }

    const char* mode = doc["mode"] | "";
    if (doc["mode"] != "pid" && doc["mode"] != "off" && doc["mode"] != "on" && doc["mode"] != "percent" && doc["mode"] != "auto") {
      sendError("Invalid mode"); return;
    }

    if (doc["mode"] == "percent") {
      if (!doc.containsKey("percent")) { sendError("Missing percent"); return; }
      double pct = doc["percent"].as<double>();
      if (pct < 0.0 || pct > 100.0) { sendError("Invalid percent"); return; }
      manualPercent[t] = pct;
    }

    // Initialisér PID ved skift til pid/auto fra en ikke-PID tilstand
    if ((doc["mode"] == "pid" || doc["mode"] == "auto") && (manualMode[t] != "pid" && manualMode[t] != "auto")) {
      if (!isnan(temps[t])) {
        pidInput[t] = temps[t];
      }
      pids[t]->SetMode(MANUAL);
      pidOutput[t] = 0;
      pids[t]->SetMode(AUTOMATIC);
    }

    manualMode[t] = mode;  // String::operator=(const char*) kopierer inden handleJson returnerer
    sendStatus();
    return;
  }

  // --- setAuto: { "command": "setAuto", "thermostat": 1-3,
  //               "threshold": float, "setpoint": float (valgfri) } ---
  // threshold er et delta i °C under setpunktet: fuld varme når temp < (setpunkt - delta).
  // Mellem grænsen og setpunkt: PID. Over setpunkt: slukket.
  if (doc["command"] == "setAuto") {
    if (!doc.containsKey("thermostat") || !doc.containsKey("threshold")) {
      sendError("Missing thermostat/threshold"); return;
    }
    int t = doc["thermostat"].as<int>() - 1;
    if (t < 0 || t >= NUM_THERMOSTATS) { sendError("Invalid thermostat"); return; }

    double threshold = doc["threshold"].as<double>();
    if (threshold < 0.0) { sendError("threshold must be >= 0"); return; }
    autoThreshold[t] = threshold;

    if (doc.containsKey("setpoint")) {
      setpoint[t] = doc["setpoint"].as<double>();
    }

    // Initialisér PID hvis vi skifter fra en ikke-PID tilstand
    if (manualMode[t] != "pid" && manualMode[t] != "auto") {
      if (!isnan(temps[t])) {
        pidInput[t] = temps[t];
      }
      pids[t]->SetMode(MANUAL);
      pidOutput[t] = 0;
      pids[t]->SetMode(AUTOMATIC);
    }
    manualMode[t] = "auto";
    sendStatus();
    return;
  }

  // --- setOverride: { "command": "setOverride", "active": true/false } ---
  // Aktiverer eller deaktiverer manuel overstyring (fuld varme på alle termostater).
  // Ved aktivering gemmes nuværende manualMode/manualPercent og gendannes ved deaktivering.
  if (doc["command"] == "setOverride") {
    if (!doc.containsKey("active")) { sendError("Missing active"); return; }
    bool act = doc["active"].as<bool>();
    if (act) {
      activateOverride();
    } else {
      deactivateOverride();
    }
    sendStatus();
    return;
  }

  sendError("Unknown command");
}
