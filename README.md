# Rama `monitoring`: registro de predicciones

Esta rama contiene **solo datos de monitoreo**, escritos por GitHub Actions (`.github/workflows/monitoring.yml`
en `main`). No se edita a mano.

## `ledger/predictions.csv`

Registro **inmutable** de lo que predijo el modelo antes de cada partido de Premier League:

* Una fila por partido, clave `(season_start, home_team, away_team)`. La primera predicción es la definitiva.
* Solo se registran partidos con fecha **posterior** al día de la corrida (UTC), así que cada predicción es anterior
  al partido. El historial de git de este archivo permite verificar cuándo se agregó cada fila.
* Cada corrida solo agrega filas al final; el workflow verifica que el contenido anterior no haya cambiado.
* `source = vivo`: registrada antes del partido. `source = reconstruido`: predicción fuera de muestra calculada
  después (solo para arrancar el historial de 2026-27); **no** cuenta como predicción en vivo.
* `model_version`: hash de los parámetros del modelo (regresión + Elo) que hizo la predicción.

Código y documentación del proyecto: rama `main`.
