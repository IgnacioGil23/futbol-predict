# Sección Estadísticas y reorganización de la web — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar una sección "Estadísticas" con métricas reales de análisis de fútbol (calculadas con los datos de Football-Data.co.uk que ya usa el proyecto) y reorganizar la web en grupos claros, separando lo que le interesa al hincha de lo técnico del modelo.

**Architecture:** Todas las métricas se calculan en Python, en la exportación (`src/export/stats.py`), y se escriben como JSON estático (`web/public/data/stats/`), igual que el resto del sitio: la web solo las muestra. La web (React + Vite, HashRouter) suma una página `Estadisticas.tsx` con una tabla ordenable reutilizable y pasa de 7 enlaces planos a 3 grupos.

**Tech Stack:** Python 3 (pandas, numpy, pytest) · React 19 + TypeScript + Vite + vitest · d3 (ya instalado).

**Spec:** la sección "Decisiones" de este documento (acordadas en la conversación del 27/10/2026).

## Decisiones (spec)

1. **Solo métricas que se usan en el análisis real.** Quedan afuera córners, faltas y cualquier otra columna que no aporte. Lista cerrada de métricas en la Tarea 1 y la Tarea 2.
2. **Límite de los datos, dicho en la página:** Football-Data trae el marcador al entretiempo y el final, no el minuto de cada gol. Las remontadas se miden "según el marcador al entretiempo", nunca "empezó perdiendo".
3. **Temporadas:** se exportan la temporada en curso y la anterior completa. La página arranca en la actual y tiene un selector. Con menos de 10 partidos jugados por equipo se muestra el aviso "Pocos partidos: estos números todavía se mueven mucho".
4. **Contexto histórico:** cada métrica de la liga se compara con el promedio de las 10 temporadas anteriores a la elegida (partidos agrupados, no promedio de promedios).
5. **Mercado:** las probabilidades del mercado salen de Bet365 pre-cierre (`b365_*`) con el método de Shin (`src.odds.shin_probabilities`), igual que en el resto del sitio.
6. **Navegación:** tres grupos. **Partidos** (próxima jornada + armar una previa), **Liga** (Tabla y proyección · Estadísticas · Equipos) y **El modelo** (Cómo funciona · Revisión · Monitoreo). Las rutas viejas redirigen.
7. **Limpieza:** sacar de las páginas de hinchas lo técnico (hash del modelo, tabla Brier de la simulación, columna "Elo (res.)") y unificar el Elo que se muestra.

## Global Constraints

- Textos de la web en español rioplatense con voseo, como el resto del sitio ("Elegí", "Abrí"). Números con `Intl` `es-AR` (helpers `pct`, `pct1`, `num` de `web/src/lib/data.ts`).
- Regla anti-fuga del proyecto: el estado "a hoy" usa solo partidos jugados antes de `today`.
- Solo `matches.parquet` (`src.data.load.MATCHES_PATH`) y `MatchStore` como fuentes. No se agrega ninguna fuente de datos nueva.
- JSON con `src.export.site.write` (sin NaN: `None`). Porcentajes como fracción 0–1 con 4 decimales (`r4`).
- No tocar `docs/deploy_cloud_run.md` (tiene cambios del usuario sin commitear).
- Commits en el repo `DS/football-match-predictor`, nunca en el repo padre `Proy/`.

## Review Focus

1. **Equipo sin partidos o con muy pocos** (recién ascendido en la fecha 1, o temporada que todavía no empezó): no puede haber división por cero ni NaN en el JSON. Los cocientes van a `None` y la web muestra "—". Test en la Tarea 2.
2. **Partido sin cuotas** (los hay en temporadas viejas y puede faltar alguno en la actual): se excluye solo del cálculo de puntos esperados, que informa cuántos partidos usó (`market_matches`). Test en la Tarea 2.
3. **Árbitro con nombre vacío o con espacios distintos** ("M Oliver" contra "M Oliver "): se normaliza con `strip()` y se descartan los vacíos. Test en la Tarea 3.
4. **Calendario de openfootball caído:** la exportación sigue funcionando y la dificultad del calendario queda en `null`, igual que hoy con `export_upcoming`. Test en la Tarea 3.
5. **Links viejos compartidos** (`#/proximos`, `#/previa`) tienen que seguir funcionando después de la reorganización. Verificación en la Tarea 5.

---

### Task 1: Filas equipo-partido y resumen de la liga

**Files:**
- Create: `src/export/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `matches.parquet` (columnas `home_goals`, `away_goals`, `ht_home_goals`, `ht_away_goals`, `home_shots`, `away_shots`, `home_shots_on_target`, `away_shots_on_target`, `home_yellow`, `away_yellow`, `home_red`, `away_red`, `referee`, `b365_home/draw/away`), `src.odds.shin_probabilities`.
- Produces:
  - `team_match_rows(matches: pd.DataFrame) -> pd.DataFrame`: dos filas por partido jugado (una por equipo), ordenadas por fecha, con las columnas `match_id, date, team, opponent, is_home, gf, ga, gf_ht, ga_ht, shots, shots_against, sot, sot_against, yellow, red, p_win, p_draw, points, ht_state`. `points` vale 3/1/0. `ht_state` es `"leading" | "level" | "trailing"`. `p_win` y `p_draw` son las probabilidades del mercado para ese equipo, NaN si no hay cuotas.
  - `league_summary(rows: pd.DataFrame) -> dict` con las claves `matches, home_win_pct, draw_pct, away_win_pct, goals_per_match, first_half_goals_share, btts_pct, over25_pct, ht_leader_win_pct, ht_trailer_comeback_pct`.

Definiciones exactas (sobre partidos, no sobre filas):
- `first_half_goals_share` = goles del primer tiempo / goles totales.
- `btts_pct` = partidos en que marcan los dos / partidos. `over25_pct` = partidos con 3 goles o más / partidos.
- `ht_leader_win_pct` = partidos con un equipo ganando al entretiempo que ese equipo terminó ganando / partidos con alguien ganando al entretiempo.
- `ht_trailer_comeback_pct` = partidos en que el que perdía al entretiempo terminó ganando / el mismo denominador.

- [ ] **Step 1: Write the failing tests** en `tests/test_stats.py`, con un DataFrame armado a mano de 3 partidos:
  - A 2-1 B (entretiempo 0-1). Cuotas que dan una probabilidad positiva.
  - B 0-0 C (entretiempo 0-0).
  - C 1-3 A (entretiempo 1-0). Sin cuotas (NaN).

```python
def test_rows_are_two_per_match_with_points_and_ht_state():
    rows = team_match_rows(matches)
    assert len(rows) == 6
    a1 = rows[(rows.match_id == 1) & (rows.team == "A")].iloc[0]
    assert (a1.points, a1.ht_state, a1.gf_ht, a1.is_home) == (3, "trailing", 0, True)
    b1 = rows[(rows.match_id == 1) & (rows.team == "B")].iloc[0]
    assert (b1.points, b1.ht_state) == (0, "leading")

def test_market_probs_nan_without_odds():
    rows = team_match_rows(matches)
    assert rows[rows.match_id == 3].p_win.isna().all()
    assert rows[rows.match_id == 1].p_win.notna().all()

def test_league_summary_values():
    s = league_summary(team_match_rows(matches))
    assert s["matches"] == 3
    assert s["home_win_pct"] == pytest.approx(1 / 3) and s["away_win_pct"] == pytest.approx(1 / 3)
    assert s["goals_per_match"] == pytest.approx(7 / 3)
    assert s["first_half_goals_share"] == pytest.approx(2 / 7)
    assert s["btts_pct"] == pytest.approx(2 / 3) and s["over25_pct"] == pytest.approx(2 / 3)
    assert s["ht_leader_win_pct"] == pytest.approx(0.0)       # los dos que ganaban al entretiempo perdieron
    assert s["ht_trailer_comeback_pct"] == pytest.approx(1.0)
```

- [ ] **Step 2: Run** `venv/Scripts/python -m pytest tests/test_stats.py -v`. Expected: FAIL (`ModuleNotFoundError: src.export.stats`).
- [ ] **Step 3: Implement** `team_match_rows` y `league_summary` en `src/export/stats.py`. Docstring del módulo en español, al estilo de `src/export/season.py`. El mercado se calcula una vez por partido con `shin_probabilities`: para el local, `p_win = p[0]`; para el visitante, `p_win = p[2]`; para los dos, `p_draw = p[1]`.
- [ ] **Step 4: Run** el mismo comando. Expected: PASS.
- [ ] **Step 5: Commit** `git add src/export/stats.py tests/test_stats.py && git commit -m "Add team-match rows and league summary for the stats section"`

### Task 2: Estadísticas por equipo

**Files:**
- Modify: `src/export/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `team_match_rows` (Tarea 1).
- Produces: `team_stats(rows: pd.DataFrame) -> list[dict]`, un dict por equipo con estas claves (todos los cocientes son `None` si el denominador es 0):
  - `team, played`
  - `home` y `away`: `{played, won, drawn, lost, points_per_game, gf, ga}`
  - `halves`: `{gf_1h, ga_1h, gf_2h, ga_2h, points_1h, points_2h}`. `points_1h` son los puntos que habría sumado si cada partido terminaba en el entretiempo. `points_2h` son los puntos de jugar solo los segundos tiempos.
  - `ht`: `{leading: {n, won, drawn, lost}, level: {...}, trailing: {...}, points_dropped_leading, points_won_trailing}`. `points_dropped_leading` = Σ(3 − puntos) sobre los partidos que ganaba al entretiempo. `points_won_trailing` = Σ puntos sobre los que perdía.
  - `goals`: `{gf_per_game, ga_per_game, clean_sheet_pct, failed_to_score_pct, btts_pct, over25_pct}`
  - `shots`: `{shots_per_game, shots_against_per_game, sot_per_game, sot_against_per_game, shot_share, sot_share, accuracy, conversion, save_pct, pdo}`. Fórmulas: `shot_share` = Σshots / (Σshots + Σshots_against); `sot_share` igual con tiros al arco; `accuracy` = Σsot / Σshots; `conversion` = Σgf / Σsot; `save_pct` = 1 − Σga / Σsot_against; `pdo` = 1000 · (conversion + save_pct).
  - `discipline`: `{yellow_per_game, red_total}`
  - `market`: `{market_matches, points, expected_points, difference}`, solo sobre partidos con cuotas. `expected_points` = Σ(3·p_win + p_draw).
  - `streaks`: `{unbeaten, winless, scoring}`: rachas vigentes contadas desde el último partido hacia atrás.

- [ ] **Step 1: Write the failing tests** con el mismo fixture de 3 partidos:

```python
def test_team_stats_for_A():
    a = next(t for t in team_stats(team_match_rows(matches)) if t["team"] == "A")
    assert a["played"] == 2 and a["home"]["won"] == 1 and a["away"]["won"] == 1
    assert a["ht"]["trailing"] == {"n": 2, "won": 2, "drawn": 0, "lost": 0}   # perdía al entretiempo en los dos
    assert a["ht"]["points_won_trailing"] == 6
    assert a["halves"]["gf_1h"] == 0 and a["halves"]["gf_2h"] == 5
    assert a["market"]["market_matches"] == 1          # el partido 3 no tiene cuotas
    assert a["streaks"] == {"unbeaten": 2, "winless": 0, "scoring": 2}

def test_ratios_are_none_without_denominator():
    one = matches[matches.match_id == 2].assign(home_shots=0, away_shots=0,
                                                home_shots_on_target=0, away_shots_on_target=0)
    b = next(t for t in team_stats(team_match_rows(one)) if t["team"] == "B")
    assert b["shots"]["accuracy"] is None and b["shots"]["pdo"] is None
    assert json.dumps(b)                                # sin NaN que rompa el JSON
```

- [ ] **Step 2: Run** `venv/Scripts/python -m pytest tests/test_stats.py -v`. Expected: los dos tests nuevos FAIL.
- [ ] **Step 3: Implement** `team_stats`. Un helper privado `_ratio(num, den) -> float | None` devuelve `None` si `den == 0` y, si no, `r4(num / den)`.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "Add per-team stats: home/away, halves, half-time states, shots, PDO, market points"`

### Task 3: Árbitros, dificultad del calendario y exportación

**Files:**
- Modify: `src/export/stats.py`, `src/export/site.py` (`main()` y una función nueva `export_stats`)
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: Tareas 1 y 2, `MatchStore.rating_as_of`, `src.data.schedule.fetch_schedule`, `src.export.season.current_state` (su campo `fixtures` tiene los cruces pendientes), `src.data.fixtures.fetch_fixtures`.
- Produces:
  - `referee_stats(matches: pd.DataFrame, min_matches: int = 3) -> list[dict]`: `{referee, matches, yellow_per_game, red_total}` sumando los dos equipos, ordenado por `yellow_per_game` de mayor a menor.
  - `remaining_difficulty(fixtures: list[tuple[str, str]], ratings: dict[str, float]) -> dict[str, dict]`: `{team: {remaining, avg_opponent_rating, rank}}`. `rank` 1 = el calendario más difícil.
  - `build_stats(matches: pd.DataFrame, season_start: int, difficulty: dict | None, referees_next: dict | None) -> dict`: `{season, matches_played, league, league_reference, teams, referees, difficulty, referees_next}`. `league_reference` es `league_summary` sobre las 10 temporadas anteriores agrupadas.
  - En `site.py`: `export_stats(out: Path, store: MatchStore, today: pd.Timestamp, rating: str) -> list[str]` escribe `stats/<temporada>.json` (por ejemplo `stats/2026-27.json`) para la temporada actual y la anterior, más `stats/index.json` = `[{"season": "2026-27", "current": true}, ...]`.
  - `referees_next`: `{"Home|Away": "Árbitro"}` sale de la columna `Referee` de `fixtures.csv` si existe y no está vacía. Si no, `null`. `parse_fixtures` ya conserva todas las columnas.

- [ ] **Step 1: Write the failing tests**

```python
def test_referee_names_are_normalized_and_filtered():
    m = matches.assign(referee=["M Oliver", "M Oliver ", ""])
    assert referee_stats(m, min_matches=2) == [
        {"referee": "M Oliver", "matches": 2, "yellow_per_game": pytest.approx(...), "red_total": ...}]

def test_remaining_difficulty_ranks_hardest_first():
    d = remaining_difficulty([("A", "B"), ("C", "A"), ("B", "C")], {"A": 2000, "B": 1800, "C": 1600})
    assert d["A"]["avg_opponent_rating"] == 1700 and d["B"]["rank"] == 1

def test_build_stats_without_schedule():
    s = build_stats(matches, 2026, difficulty=None, referees_next=None)
    assert s["difficulty"] is None and s["teams"]
```

  Los `...` de `yellow_per_game` y `red_total` se completan con los valores del fixture al escribir el test.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** En `main()` de `site.py`, llamar `export_stats(out, store, today, predictor.rating)` después de `export_upcoming`. La descarga del calendario y de `fixtures.csv` va con el mismo `try/except requests.RequestException` que usa `export_upcoming`. Si falla, `difficulty` o `referees_next` quedan en `None` y se agrega un `logger.warning`. Los ratings de la dificultad se calculan con `store.rating_as_of(team, today, rating)`, el mismo Elo que muestran Partidos y Equipos.
- [ ] **Step 4: Run** `venv/Scripts/python -m pytest -q` (toda la suite). Expected: PASS. Después `venv/Scripts/python -m src.export.site --out web/public/data`. Expected: existen `web/public/data/stats/index.json`, `2026-27.json` y `2025-26.json`, y `grep -c NaN` da 0 en los tres.
- [ ] **Step 5: Commit** `git add src tests web/public/data/stats && git commit -m "Export stats JSON (teams, referees, remaining schedule difficulty)"`

### Task 4: Página Estadísticas

**Files:**
- Create: `web/src/pages/Estadisticas.tsx`, `web/src/pages/estadisticas.css`, `web/src/components/SortableTable.tsx`, `web/src/components/SortableTable.test.ts`
- Modify: `web/src/lib/types.ts` (tipos `StatsFile`, `TeamStats`, `LeagueSummary`, `RefereeStats`, `StatsIndex`, que reflejan las Tareas 1 a 3 campo por campo), `web/src/App.tsx` (ruta `/estadisticas`)

**Interfaces:**
- Consumes: `stats/index.json` y `stats/<temporada>.json` mediante `useData`.
- Produces:
  - `SortableTable<T>({ rows, columns, initialSort })`, con `columns: { key: string; label: string; value: (r: T) => number | null; format: (v: number) => string; better: 'high' | 'low'; title?: string }[]`. Los `null` siempre van al final y se muestran como "—". El orden se cambia con clic en el encabezado (con `aria-sort`).
  - Función pura exportada `sortRows<T>(rows, value, dir): T[]` (es la que se testea).

Secciones de la página, en este orden y con estos títulos:
1. **La liga en números**: tarjetas para local / empate / visitante, goles por partido, % de goles en el primer tiempo, ambos marcan, más de 2,5 goles, y "el que gana al entretiempo, gana" / "el que pierde al entretiempo, lo da vuelta". Cada una con "promedio últimas 10 temporadas: X".
2. **Local y visitante**: tabla con PJ, puntos por partido de local, de visitante y la diferencia.
3. **Primer y segundo tiempo**: goles a favor y en contra por tiempo, más "tabla del primer tiempo" y "tabla del segundo tiempo" (puntos).
4. **Remontadas y cierres**: cuando ganaba al entretiempo (G-E-P y puntos que dejó escapar) y cuando perdía (G-E-P y puntos que rescató). Nota fija: *"Según el marcador al entretiempo: los datos no tienen el minuto de cada gol."*
5. **Ataque y defensa**: goles a favor y en contra por partido, valla invicta, sin convertir, ambos marcan, +2,5, tiros y tiros al arco a favor y en contra, % de tiros al arco, % del total de tiros del partido.
6. **Suerte o rendimiento**: puntos reales contra esperados según el mercado (diferencia) y PDO, con una explicación de 2 líneas: *"PDO = % de tiros al arco convertidos + % atajados, × 1000. Muy por encima de 1000 suele indicar buena racha que tiende a normalizarse."*
7. **Disciplina y árbitros**: amarillas por partido y rojas por equipo, tabla de árbitros (mínimo 3 partidos) y, si existe `referees_next`, el árbitro de cada partido de la próxima jornada.
8. **Lo que viene**: dificultad del calendario restante (solo para la temporada actual).

Selector de temporada arriba (con `stats/index.json`). Aviso de pocos partidos si el promedio de PJ es menor a 10. Cada equipo enlaza a `/equipos/:slug`.

- [ ] **Step 1: Write the failing test** `SortableTable.test.ts`: `sortRows` ordena de mayor a menor y de menor a mayor, y deja los `null` al final en los dos sentidos.
- [ ] **Step 2: Run** `cd web && npx vitest run`. Expected: FAIL.
- [ ] **Step 3: Implement** `SortableTable`, los tipos, la página y la ruta. Para estilos, reutilizar las clases de `season.css` y `teams.css` (`.container`, `.section`, `.eyebrow`, `.lede`, `table`, `.num`, `.tabular`).
- [ ] **Step 4: Run** `npx vitest run && npm run build && npm run lint`. Expected: todo PASS, sin errores de TypeScript.
- [ ] **Step 5: Commit** `git commit -am "Add Estadísticas page with sortable tables"`

### Task 5: Navegación en tres grupos

**Files:**
- Modify: `web/src/components/Layout.tsx`, `web/src/components/layout.css`, `web/src/App.tsx`, los enlaces internos que apuntan a `/proximos` o `/previa` (`Home.tsx`, `Upcoming.tsx`, `Preview.tsx` y `TeamPreview.tsx`: buscar con `grep -rn "/proximos\|/previa" web/src`)

**Interfaces:**
- Produces, en `Layout.tsx`, `NAV: { label: string; to?: string; items?: { to: string; label: string }[] }[]` =
  - `Partidos` → `/partidos` (Upcoming). La previa pasa a `/partidos/previa` y en Partidos queda el botón "Armar una previa".
  - `Liga` → items `Tabla y proyección` (`/temporada`), `Estadísticas` (`/estadisticas`), `Equipos` (`/equipos`).
  - `El modelo` → items `Cómo funciona` (`/metodologia`), `Revisión` (`/revision`), `Monitoreo` (`/monitoreo`).
- En escritorio, cada grupo con items abre un menú desplegable (`<button aria-expanded>` y lista). Se cierra con Escape y al hacer clic afuera. Queda activo si la ruta actual es de uno de sus items. En móvil, los grupos aparecen como encabezados dentro del menú abierto. El indicador deslizante (`useNavIndicator`) se mide sobre el elemento del grupo activo.
- Redirecciones en `App.tsx`: `proximos` → `/partidos` y `previa` → `/partidos/previa` (`<Navigate replace />`, conservando `location.search`).

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** con `npm run build && npm run lint` (PASS). Después, en el navegador de vista previa (`npm run dev`), comprobar:
  - `#/proximos` termina en `#/partidos` y `#/previa?...` en `#/partidos/previa?...`.
  - El desplegable de "Liga" abre, navega y se cierra con Escape.
  - A 375 px de ancho, el menú móvil muestra los tres grupos.
- [ ] **Step 3: Commit** `git commit -am "Group navigation into Partidos, Liga and El modelo"`

### Task 6: Limpieza de páginas

**Files:**
- Modify: `web/src/pages/Season.tsx`, `web/src/pages/Method.tsx`, `web/src/pages/Home.tsx`, `web/src/pages/Teams.tsx`, `web/src/pages/Monitoring.tsx`, `web/src/components/Layout.tsx` (pie)

Cambios exactos:
- **Tabla y proyección (`Season.tsx`):**
  - Quitar la columna "Elo (res.)" de la tabla. Es la que contradice el Elo de las fichas de equipo.
  - Quitar "Modelo {s.model_version}." del texto.
  - Mover el componente `Evaluation` ("¿Son creíbles estas probabilidades?") a `Method.tsx`, en una subsección `id="simulacion"`. En Season queda una línea: *"¿Qué tan confiables son estas probabilidades? Ver la validación →"*, que enlaza a `/metodologia#simulacion`.
  - El párrafo sobre el Elo de resultados pasa a Método.
- **Pie (`Layout.tsx`):** quitar "· modelo {model_version}" y dejar "Datos actualizados al …". El hash del modelo sigue visible en Monitoreo y en Método.
- **Inicio (`Home.tsx`):**
  - Texto principal nuevo: *"Un modelo de Machine Learning calcula la probabilidad de cada resultado de la Premier League. Lo comparamos en vivo con el mercado de apuestas."*
  - Agregar el bloque **"Datos de la temporada"** con 3 tarjetas sacadas de `stats/<actual>.json`: (a) goles por partido de la liga contra el promedio histórico; (b) el equipo con mayor `market.difference` positiva ("suma más de lo que esperaba el mercado"); (c) el equipo con más `ht.points_won_trailing`. Más un enlace "Ver todas las estadísticas →".
- **Equipos (`Teams.tsx`):**
  - El "Archivo" de clubes históricos queda dentro de un `<details>` cerrado ("Otros clubes en la Premier desde 2000-01 (26)").
  - En la ficha del equipo, un bloque **"Esta temporada en detalle"** con local / visitante, goles por tiempo y entretiempo → final, sacados de `stats/<actual>.json`, y un enlace a Estadísticas.
- **Monitoreo (`Monitoring.tsx`):** si el estado global es "datos insuficientes", no repetir la etiqueta en cada indicador. Las tarjetas muestran solo valor y rango normal, y el aviso grande queda una sola vez.

- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** con `npm run build && npm run lint && npx vitest run` (PASS). En la vista previa, recorrer todas las rutas buscando errores de consola, tema claro y oscuro, y 375 px de ancho sin scroll horizontal.
- [ ] **Step 3: Commit** `git commit -am "Simplify fan pages: move model internals to El modelo, add season highlights"`

### Task 7: Verificación final

- [ ] `venv/Scripts/python -m pytest -q`: todo PASS.
- [ ] `cd web && npx vitest run && npm run build && npm run lint`: todo PASS.
- [ ] Vista previa: capturas de Estadísticas, Inicio y el menú, en escritorio y a 375 px.
- [ ] Revisar a mano 3 números de `stats/2025-26.json` contra los resultados reales de la temporada pasada (por ejemplo, el porcentaje de victorias de local de la liga y los puntos de local del campeón).
- [ ] Sin push: el despliegue (`deploy.yml`) lo dispara el usuario.
