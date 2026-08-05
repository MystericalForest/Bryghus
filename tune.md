# Tuning af termostater

## Aktuelle firmware-defaults

- Kp = 5.0
- Ki = 0.002
- Kd = 0.0
- PWM-vindue = 5000 ms

Disse værdier svarer til konfigurationen i interface/config.h.

## Praktisk fremgangsmåde

1. Start med standardværdierne ovenfor.
2. Kør et trin, fx 20 °C -> 60 °C.
3. Vurder især de sidste 5-10 °C op mod setpunkt.

Typiske justeringer:

- Hvis temperaturen går 3-5 °C over setpunkt: sænk Kp lidt eller sænk Ki.
- Hvis den bliver 1-2 °C under setpunkt i lang tid: øg Ki lidt.
- Hvis den oscillerer konstant: sænk Kp.

## Noter

- Sensorplacering og omrøring/cirkulation har ofte større effekt end små PID-ændringer.
- Hvis føleren sidder tæt på varmelegemet, kan resten af væsken være koldere end målingen viser.
- Auto-tilstandens threshold er et delta under setpunkt og bør tunes sammen med PID.