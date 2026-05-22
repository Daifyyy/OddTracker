import json
from datetime import datetime, timezone, timedelta

import streamlit as st

from db.queries import (
    get_config, set_config, invalidate_queries,
    get_presets, save_preset, delete_preset, touch_preset,
    get_matches_df, get_line_changes_df, get_steam_moves_df,
)
from fetcher.api_client import OddsAPIClient
from fetcher.runner import run_once, fetch_scores
from config import MARKETS_AVAILABLE, BOOKMAKERS_AVAILABLE, BOOKMAKERS_DEFAULT, REGIONS_AVAILABLE
from pages.utils import sport_label_map

st.title("Matches")

# ── Sports map ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def _get_sports():
    try:
        client = OddsAPIClient()
        sports = client.get_sports()
        return {s["key"]: s["title"] for s in sports if not s.get("has_outrights")}
    except Exception:
        return {"soccer_germany_bundesliga": "Bundesliga"}

sports_map = _get_sports()

# ── Dashboard metriky ─────────────────────────────────────────────────────────
df_all     = get_matches_df()
df_active  = get_matches_df(only_active=True)
df_steam24 = get_steam_moves_df(hours=24)
df_lc      = get_line_changes_df()
credits    = get_config("credits_remaining")
last_fetch = get_config("last_fetch_at")

changes_24h = 0
if not df_lc.empty:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    changes_24h = int((df_lc["detected_at"] >= cutoff).sum())

if last_fetch:
    fetch_dt = datetime.fromisoformat(last_fetch)
    fetch_label = fetch_dt.strftime("%d.%m %H:%M")
else:
    fetch_label = "—"

credit_icon = "🟢" if (credits or 0) > 100 else ("🟡" if (credits or 0) > 20 else "🔴")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric(f"{credit_icon} API kredity", credits if credits is not None else "—")
m2.metric("Sledované zápasy", len(df_all))
m3.metric("Aktivní zápasy", len(df_active))
m4.metric("Změny kurzů (24h)", changes_24h)
m5.metric("Steam moves (24h)", len(df_steam24))
if last_fetch:
    st.caption(f"Poslední fetch: {fetch_label}")

st.divider()

# ── Dialogy ───────────────────────────────────────────────────────────────────
def _do_fetch(sport_key, markets, regions, bookmakers, preset_name=None):
    """Provede fetch a uloží výsledek. Vrátí result dict nebo vyhodí výjimku."""
    result = run_once(sport_key, markets, regions, bookmakers or None)
    set_config("last_fetch_at", datetime.now(timezone.utc).isoformat())
    if preset_name:
        touch_preset(preset_name)
    invalidate_queries()
    return result


@st.dialog("Preset")
def _preset_dialog(preset_data=None):
    original_name = preset_data["name"] if preset_data else None
    st.markdown(f"### {'Upravit' if original_name else 'Nový'} preset")

    sport_keys = list(sports_map.keys())
    default_sport = preset_data["sport_key"] if preset_data else sport_keys[0]
    sport_idx = sport_keys.index(default_sport) if default_sport in sport_keys else 0

    name = st.text_input("Název", value=original_name or "", placeholder="např. Bundesliga H2H")
    sport_key = st.selectbox(
        "Sport / Soutěž", sport_keys, index=sport_idx,
        format_func=lambda k: sports_map.get(k, k),
    )
    default_markets = json.loads(preset_data["markets"]) if preset_data else ["h2h", "totals"]
    markets = st.multiselect(
        "Trhy", list(MARKETS_AVAILABLE.keys()),
        default=[m for m in default_markets if m in MARKETS_AVAILABLE],
        format_func=lambda k: MARKETS_AVAILABLE.get(k, k),
    )
    default_bms = json.loads(preset_data["bookmakers"]) if preset_data else BOOKMAKERS_DEFAULT
    bookmakers = st.multiselect(
        "Bookmakeři", BOOKMAKERS_AVAILABLE,
        default=[b for b in default_bms if b in BOOKMAKERS_AVAILABLE],
    )
    region_keys = list(REGIONS_AVAILABLE.keys())
    default_region = preset_data["regions"] if preset_data else "eu"
    region_idx = region_keys.index(default_region) if default_region in region_keys else 0
    regions = st.selectbox(
        "Region", region_keys, index=region_idx,
        format_func=lambda k: REGIONS_AVAILABLE.get(k, k),
    )
    auto_fetch = st.toggle(
        "⚡ Automatický fetch",
        value=bool(preset_data.get("auto_fetch", 0)) if preset_data else False,
        help="GitHub Actions bude tento preset fetchovat automaticky dle vzdálenosti od výkopu.",
    )

    if st.button("💾 Uložit", type="primary", disabled=not name.strip() or not markets):
        if original_name and original_name != name.strip():
            delete_preset(original_name)
        save_preset(
            name.strip(), sport_key,
            sports_map.get(sport_key, sport_key),
            markets, bookmakers, regions,
            auto_fetch=auto_fetch,
        )
        invalidate_queries()
        st.rerun()


# ── Preset karty ──────────────────────────────────────────────────────────────
presets = get_presets()

header_col, batch_col = st.columns([3, 1])
with header_col:
    st.markdown("### Presety")
with batch_col:
    if presets and st.button("🔄 Fetch vše", use_container_width=True,
                              help="Fetchne všechny presety postupně."):
        bar = st.progress(0, text="Fetching…")
        total_snap, total_credits = 0, 0
        errors = []
        for i, p in enumerate(presets):
            bar.progress((i) / len(presets), text=f"Fetching {p['name']}…")
            try:
                r = _do_fetch(
                    p["sport_key"],
                    json.loads(p["markets"]),
                    p["regions"],
                    json.loads(p["bookmakers"]),
                    preset_name=p["name"],
                )
                total_snap    += r["snapshots_stored"]
                total_credits += r["credits_used"]
            except Exception as exc:
                errors.append(f"{p['name']}: {exc}")
        bar.progress(1.0, text="Hotovo")
        if errors:
            st.error("Chyby: " + " · ".join(errors))
        else:
            last_credits = get_config("credits_remaining")
            st.success(
                f"✅ Fetchnuto {len(presets)} presetů · "
                f"{total_snap} snapshotů · "
                f"použito {total_credits} kreditů · "
                f"zbývá **{last_credits}**"
            )

# Karty: presety + "nový preset" karta
all_items = presets + [None]
cols = st.columns(3)

for i, item in enumerate(all_items):
    with cols[i % 3]:
        if item is None:
            with st.container(border=True):
                st.markdown("&nbsp;")
                st.markdown("&nbsp;")
                if st.button("➕ Nový preset", use_container_width=True):
                    _preset_dialog()
                st.markdown("&nbsp;")
        else:
            p = item
            with st.container(border=True):
                sport_title = p.get("competition") or sports_map.get(p["sport_key"], p["sport_key"])
                badge = " ⚡" if p.get("auto_fetch") else ""
                st.markdown(f"**{p['name']}{badge}**")
                st.caption(f"🏆 {sport_title}")

                try:
                    mkt_list = json.loads(p["markets"])
                    st.caption("📋 " + " · ".join(MARKETS_AVAILABLE.get(m, m) for m in mkt_list))
                except Exception:
                    pass

                try:
                    bm_list = json.loads(p["bookmakers"])
                    bm_str = ", ".join(bm_list[:3]) + ("…" if len(bm_list) > 3 else "")
                    st.caption(f"🏦 {bm_str}")
                except Exception:
                    pass

                if p.get("last_used_at"):
                    ts = p["last_used_at"][:16].replace("T", " ")
                    st.caption(f"🕐 {ts}")
                else:
                    st.caption("🕐 —")

                fc, fe, fd = st.columns([3, 1, 1])
                with fc:
                    fetch_key = f"fetch_preset_{p['name']}"
                    if st.button("🔄 Fetch", key=fetch_key, use_container_width=True, type="primary"):
                        with st.spinner(f"Fetching {p['name']}…"):
                            try:
                                r = _do_fetch(
                                    p["sport_key"],
                                    json.loads(p["markets"]),
                                    p["regions"],
                                    json.loads(p["bookmakers"]),
                                    preset_name=p["name"],
                                )
                                st.success(
                                    f"✅ {r['snapshots_stored']} snap · "
                                    f"{r['credits_used']} kr · "
                                    f"zbývá {r['credits_remaining']}"
                                )
                            except Exception as exc:
                                st.error(str(exc))
                with fe:
                    if st.button("✏️", key=f"edit_{p['name']}", help="Upravit preset"):
                        _preset_dialog(preset_data=p)
                with fd:
                    if st.button("🗑️", key=f"del_{p['name']}", help="Smazat preset"):
                        delete_preset(p["name"])
                        invalidate_queries()
                        st.rerun()

st.divider()

# ── Auto-fetch nastavení ───────────────────────────────────────────────────────
with st.expander("🤖 Auto-fetch nastavení"):
    st.caption(
        "GitHub Actions fetchuje automaticky každou hodinu. "
        "Interval se dynamicky zkracuje čím blíž je výkop — daleko od zápasů se nefetchuje vůbec."
    )
    saved_floor = get_config("auto_fetch_credit_floor", 30)
    new_floor = st.slider(
        "Credit floor — zastav auto-fetch pod tímto limitem",
        min_value=10, max_value=100, value=int(saved_floor),
        help="Ochrana před vyčerpáním kreditů. Doporučeno: 30.",
    )
    if new_floor != saved_floor:
        set_config("auto_fetch_credit_floor", new_floor)
        st.success(f"Credit floor nastaven na {new_floor}")
    auto_presets = [p for p in presets if p.get("auto_fetch")]
    if auto_presets:
        st.caption(f"⚡ Aktivní auto-fetch presety: {', '.join(p['name'] for p in auto_presets)}")
        intervals = {
            "> 48h": "skip", "24–48h": "8h", "12–24h": "4h",
            "6–12h": "2h", "2–6h": "1h", "0–2h": "30 min",
        }
        import pandas as pd
        st.dataframe(
            pd.DataFrame(list(intervals.items()), columns=["Do výkopu", "Interval"]),
            use_container_width=False, hide_index=True,
        )
    else:
        st.info("Žádný preset nemá zapnutý auto-fetch. Uprav preset a zapni '⚡ Automatický fetch'.")

st.divider()

# ── Jednorázový fetch ──────────────────────────────────────────────────────────
with st.expander("⚙️ Jednorázový fetch (bez presetu)"):
    sport_keys = list(sports_map.keys())
    saved_sport = get_config("active_sport_key", sport_keys[0] if sport_keys else "soccer_germany_bundesliga")
    sport_idx   = sport_keys.index(saved_sport) if saved_sport in sport_keys else 0

    ec1, ec2 = st.columns(2)
    with ec1:
        adhoc_sport = st.selectbox(
            "Sport / Soutěž", sport_keys, index=sport_idx,
            format_func=lambda k: sports_map.get(k, k),
            key="adhoc_sport",
        )
        set_config("active_sport_key", adhoc_sport)

        saved_markets = get_config("active_markets", ["h2h", "totals"])
        adhoc_markets = st.multiselect(
            "Trhy", list(MARKETS_AVAILABLE.keys()),
            default=[m for m in saved_markets if m in MARKETS_AVAILABLE],
            format_func=lambda k: MARKETS_AVAILABLE.get(k, k),
            key="adhoc_markets",
        )
        set_config("active_markets", adhoc_markets)

    with ec2:
        saved_bms = get_config("active_bookmakers", BOOKMAKERS_DEFAULT)
        adhoc_books = st.multiselect(
            "Bookmakeři", BOOKMAKERS_AVAILABLE,
            default=[b for b in saved_bms if b in BOOKMAKERS_AVAILABLE],
            key="adhoc_books",
        )
        set_config("active_bookmakers", adhoc_books)

        region_keys = list(REGIONS_AVAILABLE.keys())
        saved_region = get_config("regions", "eu")
        region_idx  = region_keys.index(saved_region) if saved_region in region_keys else 0
        adhoc_region = st.selectbox(
            "Region", region_keys, index=region_idx,
            format_func=lambda k: REGIONS_AVAILABLE.get(k, k),
            key="adhoc_region",
        )
        set_config("active_regions", adhoc_region)

    ba1, ba2, ba3 = st.columns([2, 2, 2])
    with ba1:
        if st.button("🔄 Fetch", type="primary", use_container_width=True,
                     disabled=not adhoc_markets, key="adhoc_fetch"):
            with st.spinner("Stahuji kurzy…"):
                try:
                    r = _do_fetch(adhoc_sport, adhoc_markets, adhoc_region, adhoc_books or None)
                    st.success(
                        f"✅ {r['snapshots_stored']} snapshotů · "
                        f"{r['events_fetched']} zápasů · "
                        f"použito {r['credits_used']} kreditů · "
                        f"zbývá **{r['credits_remaining']}**"
                    )
                except Exception as exc:
                    st.error(f"Chyba: {exc}")
    with ba2:
        if st.button("💾 Uložit jako preset", use_container_width=True,
                     disabled=not adhoc_markets, key="adhoc_save"):
            _preset_dialog()
    with ba3:
        if st.button("📋 Fetch výsledky", use_container_width=True, key="adhoc_scores"):
            with st.spinner("Stahuji výsledky…"):
                try:
                    r = fetch_scores(adhoc_sport)
                    invalidate_queries()
                    st.success(
                        f"✅ {r['matches_updated']} výsledků · "
                        f"zbývá **{r['credits_remaining']}** kreditů"
                    )
                except Exception as exc:
                    st.error(f"Chyba: {exc}")

st.divider()

# ── Hot matches ───────────────────────────────────────────────────────────────
if not df_all.empty:
    now = datetime.now(timezone.utc)
    df_check = df_all[df_all["is_completed"] == 0].copy()
    if not df_check.empty:
        df_check["commence_dt"] = df_check["commence_time"].apply(
            lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))
        )
        df_check["hours_to_ko"] = df_check["commence_dt"].apply(
            lambda dt: (dt - now).total_seconds() / 3600
        )

        steam_match_ids = set(df_steam24["match_id"].tolist()) if not df_steam24.empty else set()

        hot = []
        for _, row in df_check.iterrows():
            badges = []
            if row["id"] in steam_match_ids:
                badges.append("🚨 Steam")
            if 0 < row["hours_to_ko"] <= 3:
                badges.append("⏰ Brzy")
            if badges:
                hot.append({
                    "Zápas": f"{row['home_team']} vs {row['away_team']}",
                    "Výkop": f"{row['hours_to_ko']:.1f}h",
                    "Signály": "  ".join(badges),
                })

        if hot:
            import pandas as pd
            st.markdown("### 🔥 Hot matches")
            st.dataframe(
                pd.DataFrame(hot),
                use_container_width=True, hide_index=True,
            )
            st.divider()

# ── Přehled zápasů ────────────────────────────────────────────────────────────
st.markdown("### Sledované zápasy")

labels = sport_label_map(df_all)

if df_all.empty:
    st.info("Žádné zápasy. Fetchni první preset nebo použij jednorázový fetch.")
else:
    with st.container(border=True):
        fc1, fc2 = st.columns(2)
        with fc1:
            filter_status = st.selectbox("Status", ["Vše", "Nadcházející", "Dokončené"])
        with fc2:
            filter_hours = st.number_input(
                "Do KO max (h)", min_value=0, max_value=999, value=0,
                help="0 = bez omezení",
            )

    df = df_all.copy()
    if filter_status == "Nadcházející":
        df = df[df["is_completed"] == 0]
    elif filter_status == "Dokončené":
        df = df[df["is_completed"] == 1]

    now = datetime.now(timezone.utc)
    df["commence_dt"] = df["commence_time"].apply(
        lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))
    )
    df["Do KO (h)"] = df["commence_dt"].apply(
        lambda dt: round((dt - now).total_seconds() / 3600, 1) if dt > now else None
    )

    if filter_hours > 0:
        df = df[df["Do KO (h)"].apply(lambda h: h is not None and 0 <= h <= filter_hours)]

    df["Status"] = df.apply(
        lambda r: "✅ Hotovo" if r["is_completed"] else (
            "🟡 Brzy" if 0 < (r["Do KO (h)"] or 99) < 2 else "⏳ Nadcházející"
        ), axis=1
    )
    df["Zápas"]       = df["home_team"] + " vs " + df["away_team"]
    df["Výkop (UTC)"] = df["commence_time"].str[:16].str.replace("T", " ")

    total = len(df)
    done  = int(df["is_completed"].sum())
    st.caption(f"{total} zápasů · {done} dokončeno · {total - done} nadcházejících")

    for sport_key, group in df.groupby("sport_key"):
        league_name = labels.get(sport_key, sport_key)
        with st.expander(f"🏆 {league_name}  ({len(group)})", expanded=True):
            for _, row in group.iterrows():
                c1, c2, c3 = st.columns([4, 2, 1])
                ko_str = f"· ⏰ {row['Do KO (h)']:.1f}h" if row["Do KO (h)"] is not None else ""
                c1.write(f"**{row['Zápas']}**  {row['Výkop (UTC)']} {ko_str}")
                c2.write(row["Status"])
                if c3.button("Detail →", key=f"detail_{row['id']}"):
                    st.session_state.selected_match_id = row["id"]
                    st.session_state.selected_match_label = row["Zápas"]
                    st.switch_page("pages/match_detail.py")
