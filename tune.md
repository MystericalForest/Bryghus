PID: PI-regulering (D = 0)
Tidsvindue: 5–10 sekunder
P: moderat
I-tid: 300–600 sekunder

En praktisk tuning:

Sæt:
P = 10
I = 500 s
D = 0
Kør fra fx 20 °C til 60 °C.
Kig på de sidste 5–10 °C:
Hvis den går 3–5 °C over → gør integralet langsommere (fx I = 800 s)
Hvis den stopper 1–2 °C under → gør integralet hurtigere (fx I = 300 s)
Hvis den oscillerer konstant → sænk aggressiviteten

Med en stor gryde vil omrøring/cirkulation og placering af føleren faktisk have større betydning end små ændringer i PID-værdierne. Hvis føleren sidder tæt ved varmelegemet, vil PID'en typisk blive for langsom og give oversving, fordi resten af vandmassen er koldere.

Hvis du kan aflæse mærkepladen på varmelegemet (fx "400 V 6 kW", "230 V 3 kW" osv.), kan jeg regne den faktiske effekt ud og give et mere præcist udgangspunkt.

Til at begynde med

Kp = 5.0
Ki = 0.002
Kd = 0

Måske senere
Kp = 3
Ki = 0.0005
Kd = 0