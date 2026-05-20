# OddTracker — CLAUDE.md

Analytický nástroj pro sledování pohybu kurzů na sportovních trzích. Cílem není přímé sázení, ale sběr dat, detekce patterns a zpětné vyhodnocení CLV.

## Spuštění

```
run.bat
# nebo
streamlit run app.py --server.port 8501
```

## Stack

| Komponenta | Technologie |
|-----------|------------|
| Dashboard | Streamlit 1.54 |
| Databáze | SQLite (raw sqlite3, WAL mode) |
| API | The Odds API v4 |
| Vizualizace | Pandas styled DataFrames (tabulky, ne grafy) |
| Python | 3.12 |

## Struktura projektu

```
OddTracker/
├── app.py              # Streamlit router, credit counter v sidebaru
├── config.py           # Konstanty: trhy, bookmakeři, prahy pro steam/CLV, Plotly dark theme
├── run.bat             # Spustí Streamlit na portu 8501
├── .env                # ODDS_API_KEY=... (nikdy do gitu)
│
├── db/
│   ├── database.py     # get_connection() — sqlite3 + WAL + foreign keys
│   ├── models.py       # init_db() — CREATE TABLE IF NOT EXISTS pro všech 9 tabulek
│   └── queries.py      # Všechny SELECT/INSERT/UPSERT funkce, vracejí pd.DataFrame nebo dict
│
├── fetcher/
│   ├── api_client.py   # OddsAPIClient — get_sports(), get_odds(), get_scores()
│   ├── normalizer.py   # flatten_odds(): API JSON → list[dict] připravené pro INSERT
│   └── runner.py       # run_once() a fetch_scores() — volané z dashboard tlačítek
│
├── analytics/
│   ├── movements.py    # detect_line_changes(snapshot_time) → int
│   ├── steam.py        # detect_steam_moves(snapshot_time) → int
│   ├── clv.py          # calculate_clv_for_match(), mark_matches_completed()
│   └── results.py      # win_rate_by_signal(), clv_summary() — pro záložku Analytics
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

## Databázové tabulky

| Tabulka | Účel |
|---------|------|
| `user_config` | Klíč/hodnota — persistuje poslední výběr uživatele (sport, trhy, bookmakeři) |
| `fetch_presets` | Pojmenované konfigurace pro rychlé přepínání (sport + trhy + bookmakeři) |
| `matches` | Registr sledovaných zápasů (id, týmy, commence_time, is_completed) |
| `match_results` | Výsledky zápasů ze /scores endpointu (skóre, is_completed) |
| `odds_snapshots` | Hlavní time-series tabulka — jeden řádek = jeden kurz v jeden čas |
| `line_changes` | Detekované změny kurzů/linií mezi snapshoty (auto po každém fetchi) |
| `steam_moves` | Steam moves — koordinované pohyby u 3+ bookmakrů v 15 min okně |
| `clv_records` | CLV záznamy — opening vs closing, vypočítáno po dokončení zápasu |

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
      → db/queries.insert_snapshots()
      → db/queries.upsert_matches()
      → analytics/movements.detect_line_changes()
      → analytics/steam.detect_steam_moves()
      → analytics/clv.mark_matches_completed()
      → vrátí dict {events_fetched, snapshots_stored, credits_used, credits_remaining}
```

Žádný automatický scheduler — vše je manuální přes dashboard.

## Preset systém

- Uložení: `pages/matches.py` → tlačítko "💾 Uložit" → `@st.dialog` → `db/queries.save_preset()`
- Načtení: výběr z dropdownu → předvyplní všechny selektory
- Persistuje: sport_key, competition, markets (JSON list), bookmakers (JSON list), regions
- Poslední výběr se vždy ukládá do `user_config` i bez pojmenovaného presetu

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

- `db/database.py:get_connection()` vždy volat bez kontextového manageru — `conn.close()` explicitně
- WAL mode je kritický — Streamlit čte zatímco runner zapisuje
- `analytics/` moduly přijímají `snapshot_time: str` (ISO8601 UTC) jako parametr
- `pages/matches.py` volá `init_db()` při každém načtení — idempotentní, bezpečné
- Streamlit cache: `@st.cache_data(ttl=3600)` pouze na `/sports` endpoint (drahé volání)
