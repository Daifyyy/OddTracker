import json
from datetime import datetime, timezone

import streamlit as st

from db.models import init_db
from db.queries import (
    get_config, set_config,
    get_presets, save_preset, delete_preset, touch_preset,
    get_matches_df,
)
from fetcher.api_client import OddsAPIClient
from fetcher.runner import run_once, fetch_scores
from config import MARKETS_AVAILABLE, BOOKMAKERS_AVAILABLE, BOOKMAKERS_DEFAULT, REGIONS_AVAILABLE

init_db()

st.title("Matches")
st.caption("Vyber soutěž a trhy, nastav preset a fetchni kurzy.")

# ── Preset systém ──────────────────────────────────────────────────────────────
presets      = get_presets()
preset_names = [p["name"] for p in presets]

@st.dialog("Uložit preset")
def _save_dialog():
    name = st.text_input("Název presetu", placeholder="např. Bundesliga H2H+Totals")
    if st.button("💾 Uložit", type="primary"):
        if name.strip():
            save_preset(
                name.strip(),
                st.session_state["_ps_sport"],
                st.session_state["_ps_sport"],
                st.session_state["_ps_markets"],
                st.session_state["_ps_bookmakers"],
                st.session_state["_ps_regions"],
            )
            st.rerun()
        else:
            st.warning("Zadej název.")

with st.container(border=True):
    col_p, col_s, col_d = st.columns([4, 1, 1])
    with col_p:
        selected_preset = st.selectbox(
            "Preset", ["— nový —"] + preset_names,
            key="preset_sel", label_visibility="collapsed",
            help="Vyber uložený preset nebo nastav nový ručně níže.",
        )
    preset_data = next((p for p in presets if p["name"] == selected_preset), None)

    with col_s:
        if st.button("💾 Uložit", use_container_width=True):
            _save_dialog()
    with col_d:
        if preset_data and st.button("🗑️ Smazat", use_container_width=True):
            delete_preset(selected_preset)
            st.rerun()

# ── Selektory ─────────────────────────────────────────────────────────────────
def _load(key, default):
    if preset_data:
        val = preset_data.get(key)
        if val and key in ("markets", "bookmakers"):
            try:
                return json.loads(val)
            except Exception:
                pass
        return val or default
    return get_config(key, default)

@st.cache_data(ttl=3600)
def _get_sports():
    try:
        client = OddsAPIClient()
        sports = client.get_sports()
        return {s["key"]: s["title"] for s in sports if not s.get("has_outrights")}
    except Exception:
        return {"soccer_germany_bundesliga": "Bundesliga"}

sports_map = _get_sports()

with st.container(border=True):
    st.markdown("**Konfigurace sledování**")
    c1, c2 = st.columns(2)
    with c1:
        sport_keys   = list(sports_map.keys())
        default_sport = _load("active_sport_key", sport_keys[0] if sport_keys else "soccer_germany_bundesliga")
        sport_idx    = sport_keys.index(default_sport) if default_sport in sport_keys else 0
        sport_key    = st.selectbox(
            "Sport / Soutěž",
            sport_keys, index=sport_idx,
            format_func=lambda k: sports_map.get(k, k),
        )
        set_config("active_sport_key", sport_key)

        all_markets     = list(MARKETS_AVAILABLE.keys())
        default_markets = _load("active_markets", ["h2h", "totals"])
        markets = st.multiselect(
            "Trhy",
            all_markets,
            default=[m for m in default_markets if m in all_markets],
            format_func=lambda k: MARKETS_AVAILABLE.get(k, k),
        )
        set_config("active_markets", markets)

    with c2:
        default_bms = _load("active_bookmakers", BOOKMAKERS_DEFAULT)
        bookmakers  = st.multiselect(
            "Bookmakeři",
            BOOKMAKERS_AVAILABLE,
            default=[b for b in default_bms if b in BOOKMAKERS_AVAILABLE],
        )
        set_config("active_bookmakers", bookmakers)

        region_keys   = list(REGIONS_AVAILABLE.keys())
        default_region = _load("regions", "eu")
        region_idx    = region_keys.index(default_region) if default_region in region_keys else 0
        regions = st.selectbox(
            "Region",
            region_keys, index=region_idx,
            format_func=lambda k: REGIONS_AVAILABLE.get(k, k),
        )
        set_config("active_regions", regions)

# uložení hodnot pro dialog
st.session_state.update({
    "_ps_sport": sport_key, "_ps_markets": markets,
    "_ps_bookmakers": bookmakers, "_ps_regions": regions,
})

# ── Fetch akce ────────────────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown("**Stažení dat**")
    cf1, cf2 = st.columns(2)
    with cf1:
        if st.button("🔄 Fetch odds", type="primary", use_container_width=True, disabled=not markets):
            with st.spinner("Stahuji kurzy…"):
                try:
                    result = run_once(sport_key, markets, regions, bookmakers or None)
                    if preset_data:
                        touch_preset(selected_preset)
                    st.success(
                        f"✅ {result['snapshots_stored']} snapshotů · "
                        f"{result['events_fetched']} zápasů · "
                        f"použito {result['credits_used']} kreditů · "
                        f"zbývá **{result['credits_remaining']}**"
                    )
                except Exception as exc:
                    st.error(f"Chyba: {exc}")
        st.caption("Stáhne aktuální kurzy a uloží snapshot.")

    with cf2:
        if st.button("📋 Fetch výsledky", use_container_width=True,
                     help="Stáhne výsledky dokončených zápasů ze /scores endpointu."):
            with st.spinner("Stahuji výsledky…"):
                try:
                    result = fetch_scores(sport_key)
                    st.success(
                        f"✅ {result['matches_updated']} výsledků aktualizováno · "
                        f"zbývá **{result['credits_remaining']}** kreditů"
                    )
                except Exception as exc:
                    st.error(f"Chyba: {exc}")
        st.caption("Načte skóre po skončení zápasů (nutné pro Analytics).")

# ── Přehled zápasů ────────────────────────────────────────────────────────────
st.markdown("### Sledované zápasy")

df = get_matches_df(sport_key)
if df.empty:
    st.info("Žádné zápasy. Klikni na **Fetch odds** pro načtení.")
else:
    now = datetime.now(timezone.utc)
    df["commence_dt"] = df["commence_time"].apply(
        lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))
    )
    df["Do KO (h)"] = df["commence_dt"].apply(
        lambda dt: round((dt - now).total_seconds() / 3600, 1) if dt > now else None
    )
    df["Status"] = df.apply(
        lambda r: "✅ Hotovo" if r["is_completed"] else (
            "🟡 Brzy" if 0 < (r["Do KO (h)"] or 99) < 2 else "⏳ Nadcházející"
        ), axis=1
    )
    df["Zápas"]       = df["home_team"] + " vs " + df["away_team"]
    df["Výkop (UTC)"] = df["commence_time"].str[:16].str.replace("T", " ")
    df["Poslední fetch"] = df["last_seen_at"].str[:16].str.replace("T", " ")

    st.dataframe(
        df[["Zápas", "Výkop (UTC)", "Do KO (h)", "Status", "Poslední fetch"]],
        use_container_width=True, hide_index=True,
    )
    total = len(df)
    done  = int(df["is_completed"].sum())
    st.caption(f"{total} zápasů celkem · {done} dokončeno · {total - done} nadcházejících")
