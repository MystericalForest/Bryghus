# Bryghus
Det nye kontrolsoftware

## CSV-logning pr. termostat

Hver termostatfane har en knap til logning:

- `Start logning`: opretter en ny CSV-fil
- `Stop og gem`: lukker filen sikkert

Filer gemmes i mappen `logs/` i projektets rodmappe.

Der logges hvert 5. sekund med følgende kolonner:

- `timestamp`
- `thermostat_navn`
- `temperature`
- `setpoint`
- `reguleringstype`
- `state`
- `heater`
- `heat_percent`

CSV-filer skrives med `;` som separator og `,` som decimalseparator.
