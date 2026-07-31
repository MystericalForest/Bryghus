#pragma once

// =============================================================================
// config.h — Termostat Controller konfiguration
// -----------------------------------------------------------------------------
// Alle hardware-pins, tællerværdier og standardindstillinger samlet ét sted.
// Rediger kun i denne fil — ikke i termostat.ino.
// =============================================================================


// =============================================================================
// ANTAL ENHEDER
// Ændr disse hvis du tilføjer/fjerner relæer, termostater eller sensorer.
// Husk at opdatere de tilhørende pin-arrays nedenfor tilsvarende.
// =============================================================================

#define NUM_RELAYS       4   // Antal almindelige relæer
#define NUM_THERMOSTATS  3   // Antal PID-termostater / varmestyringer
#define NUM_TEMPS        4   // Antal PT100 temperatursensorer (via MAX31865)
                             // Sensor 1-3: bruges til PID-regulering
                             // Sensor 4:   ekstra / ambient — kun overvågning,
                             //             ingen PID, ingen alarm/advarsel (undtagen HW Alarm)
#define NUM_BUTTONS (NUM_RELAYS + 1) // Relæknapper + sensorvælger-knap


// =============================================================================
// PIN-DEFINITIONER — RELÆER
// Index:  0     1     2     3
// =============================================================================

#define RELAY_PINS    {2, 3, 4, 5}     // Relæ output-pins
#define RELAY_BUTTONS {6, 7, 8, 9}     // Knap input-pins (INPUT_PULLUP)
#define RELAY_LEDS    {10, 11, 12, 13} // Status-LED output-pins


// =============================================================================
// PIN-DEFINITIONER — VARMESTYRING (PID)
// Index:  0     1     2
// =============================================================================

#define HEAT_RELAY_PINS  {A0, A1, A2}  // Varmerelæ output-pins

// Status-LED'er pr. termostat — 3 LED'er (Rød, Gul, Grøn) + 1 varme-LED
// Tilstand:   Opvarmning = Grøn blinker
//             Run        = Grøn lyser
//             Advarsel   = Gul lyser
//             Alarm      = Rød lyser
//             HW Alarm   = Rød blinker
// Varme-LED:  Lyser når varmerelæet er aktivt (PWM-puls)
//
// Index:            0     1     2   (termostat 1, 2, 3)
#define STATUS_LED_RED    {22, 25, 28}  // Rød LED pr. termostat
#define STATUS_LED_YELLOW {23, 26, 29}  // Gul LED pr. termostat
#define STATUS_LED_GREEN  {24, 27, 30}  // Grøn LED pr. termostat
#define HEAT_LED_PINS     {31, 32, 33}  // Varme-LED pr. termostat

// Blink-interval i ms for Opvarmning (grøn) og HW Alarm (rød)
#define STATUS_BLINK_INTERVAL_MS  500


// =============================================================================
// PIN-DEFINITIONER — DISPLAY (TM1637)
// =============================================================================

#define DISPLAY_CLK        A8
#define DISPLAY_DIO        A9
#define DISPLAY_BRIGHTNESS 0x0f  // 0x00 (slukket) – 0x0f (maksimal lysstyrke)


// =============================================================================
// PIN-DEFINITIONER — SENSORVÆLGER OG LED'ER
// Index:  0     1     2     3
// =============================================================================

#define SENSOR_BUTTON_PIN  A3
#define SENSOR_LED_PINS    {A4, A5, A6, A7}  // En LED pr. sensor


// =============================================================================
// PIN-DEFINITIONER — MAX31865 PT100 SENSORER (SPI)
// Alle fire MAX31865-moduler deler SPI-bus (MOSI, MISO, SCK).
// Hvert modul har sin egen Chip Select (CS) pin.
//
// Standard SPI-pins på Arduino Mega:
//   MOSI = 51, MISO = 50, SCK = 52
//
// CS-pins — tilpas til dit board:
// Index:  0     1     2     3   (sensor 1, 2, 3, 4)
// =============================================================================

#define MAX31865_CS_PINS  {34, 35, 36, 37}  // CS-pins for de fire MAX31865-moduler

// PT100 konfiguration
// Vælg den rigtige reference-modstand for dit MAX31865-modul:
//   MAX31865 breakout med PT100:  Rref = 430 ohm
//   MAX31865 breakout med PT1000: Rref = 4300 ohm
#define MAX31865_RREF      430.0   // Reference-modstand i ohm
#define MAX31865_RNOMINAL  100.0   // Nominel modstand ved 0°C (100 ohm for PT100)

// Interval i ms mellem sensor-aflæsninger.
// MAX31865 conversion time: ~66ms (60Hz filter) / ~52ms (50Hz filter).
// 250ms giver 4 aflæsninger pr. sekund og er passende for varmestyring.
#define TEMP_READ_INTERVAL_MS  250


// =============================================================================
// SERIAL KOMMUNIKATION
// =============================================================================

#define SERIAL_BAUD_RATE    115200  // Baud rate — husk at matche på PC-siden
#define SERIAL_BUFFER_MAX   400     // Maks tegn i serial-buffer før kassering


// =============================================================================
// DEBOUNCE
// =============================================================================

#define DEBOUNCE_DELAY_MS   50  // Debounce-tid for alle knapper i ms


// =============================================================================
// PID STANDARDINDSTILLINGER
// Disse bruges ved opstart. Kan ændres runtime via setPID-kommandoen.
// Index:  0     1     2   (termostat 1, 2, 3)
// =============================================================================

#define PID_SETPOINTS   {25.0, 25.0, 25.0}  // Startsetpunkter i °C
#define PID_KP          {2.0,  2.0,  2.0}   // Proportional-koefficienter
#define PID_KI          {5.0,  5.0,  5.0}   // Integral-koefficienter
#define PID_KD          {1.0,  1.0,  1.0}   // Differentiations-koefficienter


// =============================================================================
// AUTO-REGULERING — GRÆNSETEMPERATUR
// Under denne temperatur kører varmeelementet på 100% i "auto"-tilstand.
// Grænsen er et delta i °C UNDER setpunktet: fuld varme når temp < (setpunkt - delta).
// Mellem grænsen og setpunkt reguleres af PID.
// Over setpunkt er varmen slukket.
// Kan ændres runtime via setAuto-kommandoen.
// Index:  0     1     2   (termostat 1, 2, 3)
// =============================================================================

#define AUTO_THRESHOLDS  {5.0, 5.0, 5.0}  // Delta i °C under setpunkt — under (setpunkt - delta) kører varmen 100%


// =============================================================================
// PWM-VINDUE (Time-Proportional varmestyring)
// Størrelsen bestemmer hvor ofte varmerelæet kan skifte tilstand.
// Større vindue = mere jævn regulering, men langsommere reaktion.
// Kan ændres runtime via setPID-kommandoen (windowSize).
// Index:  0        1        2   (termostat 1, 2, 3)
// =============================================================================

#define PID_WINDOW_SIZES  {5000, 5000, 5000}  // ms pr. termostat


// =============================================================================
// ALARM- OG ADVARSELSGRÆNSER
// Delta-værdier i °C relativt til setpunkt.
// Kan ændres runtime via setLimits-kommandoen.
// Kun for termostat 1-3 — sensor 4 har ingen alarm/advarselsgrænser.
// Index:  0     1     2   (termostat 1, 2, 3)
// =============================================================================

#define ALARM_LIMITS   {5.0, 5.0, 5.0}  // °C over setpunkt → Alarm
#define WARNING_LIMITS {2.0, 2.0, 2.0}  // °C afvigelse (begge retninger) → Advarsel


// =============================================================================
// TEMPERATUR RÆKKEVIDDE-KONTROL
// Aflæsninger uden for dette interval betragtes som HW-fejl
// (defekt sensor, løs ledning, kortslutning e.l.).
// Fault-kode 0xFF bruges i JSON som markør for rækkevidde-fejl.
// =============================================================================

#define TEMP_RANGE_MIN  -30.0f   // °C — under denne grænse → HW Alarm
#define TEMP_RANGE_MAX  150.0f   // °C — over denne grænse  → HW Alarm


// =============================================================================
// DISPLAY — SENSORKNAP (TM1637 + langt-tryk)
// =============================================================================

// Tid i ms knappen skal holdes nede for at aktivere langt-tryk (setpoint-visning)
#define LONG_PRESS_MS       800

// Tid i ms knappen skal holdes nede (totalt) for at aktivere edit-mode (setpoint blinker)
// Skal være større end LONG_PRESS_MS — edit-mode aktiveres mens setpoint allerede vises
#define VERY_LONG_PRESS_MS  1800

// Tid i ms setpunktet vises på displayet efter langt tryk (uden edit-mode)
#define SETPOINT_DISPLAY_MS 2000

// Blink-interval i ms for setpoint i edit-mode
#define EDIT_BLINK_MS       400


// =============================================================================
// MANUEL OVERSTYRING — FULD VARME
// Fysisk knap + rød LED. Sætter alle termostater til manuel 100% effekt.
// Gendanner tidligere tilstand når den slås fra.
// =============================================================================

#define OVERRIDE_BUTTON_PIN  38   // Knap input-pin (INPUT_PULLUP)
#define OVERRIDE_LED_PIN     39   // Rød LED output-pin


// =============================================================================
// WATCHDOG
// Genstarter Arduinoen hvis loop() ikke kører inden for den angivne tid.
// Gyldige værdier: WDTO_500MS, WDTO_1S, WDTO_2S, WDTO_4S, WDTO_8S
// =============================================================================

#define WATCHDOG_TIMEOUT  WDTO_2S
