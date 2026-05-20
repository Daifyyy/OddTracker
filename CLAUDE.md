# OddTracker — CLAUDE.md

Analytický nástroj pro sledování pohybu kurzů na sportovních trzích. Cílem není přímé sázení, ale sběr dat, detekce patterns a zpětné vyhodnocení CLV.

## Spuštění

```
run.bat
# nebo
streamlit run app.py --server.port 8501
```

Cloudová verze: https://github.com/Daifyyy/OddTracker → deploy na Streamlit Community Cloud.

## Stack

| Komponenta | Technologie |
|-----------|------------|
| Dashboard | Streamlit 1.54 |
| Databáze (lokálně) | SQLite (raw sqlite3, WAL mode) |
| Databáze (cloud) | Turso (libsql) přes HTTP REST API |
| API | The Odds API v4 |
| Vizualizace | Pandas styled DataFrames (tabulky, ne grafy) |
| Python | 3.12 |

## Struktura projektu

```
OddTracker/
├── app.py              # Streamlit router, credit counter v sidebaru, init_db() při startu
├── config.py           # Konstanty: trhy, bookmakeři, prahy pro steam/CLV, Plotly dark theme
├── run.bat             # Spustí Streamlit na portu 8501
├── .env                # ODDS_API_KEY=... (nikdy do gitu)
│
├── db/
│   ├── database.py     # get_connection() — vrací Connection (sqlite3) nebo _TursoHTTPConnection
│   ├── models.py       # init_db() — CREATE TABLE IF NOT EXISTS pro všech 8 tabulek
│   └── queries.py      # SELECT/INSERT/UPSERT funkce + @st.cache_data na read queries
│
├── fetcher/
│   ├── api_client.py   # OddsAPIClient — get_sports(), get_odds(), get_scores()
│   ├── normalizer.py   # flatten_odds(): API JSON → list[dict] připravené pro INSERT
│   └── runner.py       # run_once() a fetch_scores() — volané z dashboard tlačítek
│
├── analytics/
│   ├── movements.py    # detect_line_changes(snapshot_time) → int  [pure SQL INSERT…SELECT]
│   ├── steam.py        # detect_steam_moves(snapshot_time) → int   [pure SQL INSERT…SELECT]
│   ├── clv.py          # calculate_clv_for_match(), mark_matches_completed()
│   └── results.py      # win_rate_by_signal(), clv_summary() — pro záložku Analytics
│
├── tests/
│   └── test_database.py  # 29 testů: Connection, Row, _df, TursoHTTP mock, detect_line_changes
│
└── pages/
    ├── matches.py      # Fetch UI, preset systém, seznam zápasů
    ├── movement.py     # Pivot tabulka vývoje kurzů v čase
    ├── lines.py        # Tabulka detekovaných změn kurzů
    ├── bookmakers.py   # Porovnání bookmakrů, best/worst odds
    ├── clv.py          # CLV distribuce a detailní záznamy
    ├── steam.py        # Steam move log
    ├── analytics.py    # Win rate, CLV souhrn, steam summary
    └── help.py         # Kompletní průvodce v češtině (5 tabů)
```

## Databázová vrstva

### Duální backend: sqlite3 / Turso HTTP

`db/database.py:get_connection()` rozhoduje podle env proměnných:

```python
# Lokálně (bez TURSO_URL) → sqlite3
raw = sqlite3.connect(DB_PATH)

# Cloud (TURSO_URL + TURSO_TOKEN nastaveny) → HTTP REST
return _TursoHTTPConnection(TURSO_URL, TURSO_TOKEN)
```

**`Connection`** — wrapper nad sqlite3, vrací `Row` (dict subclass s indexovým přístupem).

**`_TursoHTTPConnection`** — HTTP klient pro Turso REST API (`/v2/pipeline`, Hrana v2 protokol).
- `execute(sql, params)` → jeden HTTP request
- `execute_batch(stmts)` → N statementů v **jednom** HTTP requestu (kritické pro insert_snapshots)
- Float parametry: `{"type": "float", "value": 3.14}` — Turso nezná `"real"`
- Integer parametry: `{"type": "integer", "value": "42"}` — hodnota je string
- `SELECT changes()` je interceptován — vrací `_last_changes` bez HTTP callu

### Databázové tabulky

| Tabulka | Účel |
|---------|------|
| `user_config` | Klíč/hodnota — persistuje poslední výběr uživatele |
| `fetch_presets` | Pojmenované konfigurace pro rychlé přepínání |
| `matches` | Registr sledovaných zápasů |
| `match_results` | Výsledky zápasů ze /scores endpointu |
| `odds_snapshots` | Hlavní time-series tabulka — jeden řádek = jeden kurz v jeden čas |
| `line_changes` | Detekované změny kurzů/linií mezi snapshoty |
| `steam_moves` | Koordinované pohyby u 3+ bookmakrů v 15min okně |
| `clv_records` | Opening vs closing odds, vypočítáno po dokončení zápasu |

### odds_snapshots schéma
```
snapshot_time, match_id, home_team, away_team, commence_time,
bookmaker, market, selection, line (REAL nullable), odds
UNIQUE(snapshot_time, match_id, bookmaker, market, selection, line)
```

## API — klíčové informace

- **Free tier:** 500 kreditů/měsíc, 1 kredit = 1 volání
- **SSL:** `verify=False` + urllib3 warnings potlačeny — Windows SSL chain issue
- **Dostupné trhy (EU, fotbal):** pouze `h2h`, `totals`, `spreads`
- **Corners, BTTS, team totals:** v tomto API nejsou dostupné
- **bet365, Fortuna, Betano, Tipsport:** v API nejsou
- **Doporučení:** Pinnacle (referenční sharp book) + Williamhill, Nordicbet, Betsson
- **Kredity:** header `X-Requests-Remaining` čten po každém volání, uložen do `user_config`

## Fetch flow

```
UI tlačítko "Fetch odds"
  → fetcher/runner.py:run_once(sport_key, markets, regions, bookmakers)
      → api_client.get_odds()
      → normalizer.flatten_odds()
      → db/queries.insert_snapshots()        ← execute_batch (1 HTTP call pro N řádků)
      → db/queries.upsert_matches()          ← execute_batch
      → analytics/movements.detect_line_changes()  ← 1 INSERT…SELECT SQL
      → analytics/steam.detect_steam_moves()       ← 1 INSERT…SELECT SQL
      → analytics/clv.mark_matches_completed()
      → invalidate_queries()                 ← vymaže @st.cache_data
      → vrátí dict {events_fetched, snapshots_stored, credits_used, credits_remaining}
```

Žádný automatický scheduler — vše je manuální přes dashboard.

## Caching a výkon

Read funkce v `db/queries.py` jsou dekorované `@st.cache_data(ttl=60)`:
- `get_matches_df`, `get_snapshots_df`, `get_opening_odds`, `get_closing_odds`
- `get_latest_odds_per_book`, `get_line_changes_df`, `get_steam_moves_df`
- `get_clv_df`, `get_results_df`, `get_presets`

Po každém write (fetch, save/delete preset) se volá `invalidate_queries()` → `st.cache_data.clear()`.

`set_config` v `pages/matches.py` se zapisuje do DB **pouze když se hodnota změnila** (session_state guard `_set_config_if_changed`) — při procházení filtrů bez změn = 0 HTTP zápisů.

## Preset systém

- Uložení: `pages/matches.py` → tlačítko "💾 Uložit" → `@st.dialog` → `db/queries.save_preset()`
- Načtení: výběr z dropdownu → předvyplní všechny selektory
- Persistuje: sport_key, competition, markets (JSON list), bookmakers (JSON list), regions
- Poslední výběr se ukládá do `user_config` (jen při změně hodnoty)

## Výsledky a Analytics

- Výsledky se fetchují přes `fetcher/runner.fetch_scores()` → `/scores` endpoint
- CLV se počítá automaticky v `analytics/clv.mark_matches_completed()` po dokončení zápasu
- `analytics/results.win_rate_by_signal()` koreluje line changes s výsledky (vyžaduje match_results)
- Záložka Analytics je smysluplná až po 30+ dokončených zápasech

## Vizuální konvence

- Všechny stránky: filtry v `st.container(border=True)`, metriky v řadě `st.columns`
- Tabulky: `st.dataframe()` se styled DataFrame (zelená = kurz vzrostl, červená = klesl)
- Popisky: každá tabulka má `st.caption()` s vysvětlením
- Sidebar: credit counter s barevným indikátorem (🟢 >100, 🟡 >20, 🔴 ≤20)
- Jazyk UI: čeština
- Grafy: nepoužíváme — pouze tabulky

## Důležité poznámky

- `get_connection()` vždy volat s explicitním `conn.close()` — žádný context manager na Connection
- WAL mode jen pro lokální sqlite3 — pro Turso HTTP není relevantní
- `analytics/movements.py` a `analytics/steam.py` jsou pure SQL (INSERT…SELECT) — žádné Python smyčky
- `app.py` volá `init_db()` při každém startu — idempotentní; `pages/matches.py` init_db() nevolá
- `analytics/` moduly přijímají `snapshot_time: str` (ISO8601 UTC) jako parametr
- Streamlit cache: `@st.cache_data(ttl=3600)` na `/sports` endpoint, `ttl=60` na DB read queries

## Cloud deployment (Streamlit Community Cloud)

Secrets v Streamlit Cloud dashboard:
```toml
ODDS_API_KEY = "..."
TURSO_URL = "libsql://oddtracker-daifyyy.aws-eu-west-1.turso.io"
TURSO_TOKEN = "..."
```

Nový Turso token: `turso db tokens create oddtracker --expiration none`
