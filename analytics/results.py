import pandas as pd

from db.queries import get_line_changes_df, get_results_df, get_steam_moves_df, get_clv_df


def win_rate_by_signal(min_odds_delta: float = 0.05,
                       market: str | None = None) -> pd.DataFrame:
    changes = get_line_changes_df()
    results = get_results_df()

    if changes.empty or results.empty:
        return pd.DataFrame()

    if market:
        changes = changes[changes["market"] == market]

    # Keep only significant moves
    changes = changes[changes["odds_delta"].abs() >= min_odds_delta].copy()
    if changes.empty:
        return pd.DataFrame()

    changes["direction"] = changes["odds_delta"].apply(lambda x: "down" if x < 0 else "up")

    merged = changes.merge(results[["match_id", "corners_total",
                                    "home_score", "away_score"]],
                           on="match_id", how="inner")
    if merged.empty:
        return pd.DataFrame()

    def hit(row: pd.Series) -> bool | None:
        if row["market"] == "totals" and row["selection"] in ("Over", "Under"):
            if row["corners_total"] is None:
                return None
            if row["selection"] == "Over":
                return row["corners_total"] > (row["new_line"] or row["old_line"] or 0)
            return row["corners_total"] < (row["new_line"] or row["old_line"] or 0)
        return None

    merged["hit"] = merged.apply(hit, axis=1)
    merged = merged.dropna(subset=["hit"])
    if merged.empty:
        return pd.DataFrame()

    summary = (
        merged.groupby(["market", "selection", "direction"])
        .agg(count=("hit", "count"), wins=("hit", "sum"))
        .reset_index()
    )
    summary["hit_rate_pct"] = (summary["wins"] / summary["count"] * 100).round(1)
    return summary.sort_values("hit_rate_pct", ascending=False)


def clv_summary(sport_key: str | None = None) -> dict:
    df = get_clv_df(sport_key)
    if df.empty:
        return {"count": 0, "avg_clv_pct": 0.0, "beat_closing_pct": 0.0}
    return {
        "count": len(df),
        "avg_clv_pct": round(df["clv_pct"].mean(), 2),
        "beat_closing_pct": round((df["clv_pct"] > 0).mean() * 100, 1),
    }
