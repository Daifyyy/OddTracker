import pandas as pd


def highlight_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Highlight cells where value changed vs previous row (green=up, red=down)."""
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for col in df.columns:
        for i in range(1, len(df)):
            prev, curr = df[col].iloc[i - 1], df[col].iloc[i]
            if pd.notna(prev) and pd.notna(curr) and curr != prev:
                styles.iloc[i][col] = (
                    "background-color:#1b3a2a;font-weight:bold" if curr > prev
                    else "background-color:#3a1b1b;font-weight:bold"
                )
    return styles


def sport_label_map(df_matches: pd.DataFrame) -> dict[str, str]:
    """Return {sport_key: sport_title} derived from a matches DataFrame."""
    if df_matches.empty or "sport_key" not in df_matches.columns:
        return {}
    return (
        df_matches.drop_duplicates("sport_key")
        .set_index("sport_key")["sport_title"]
        .to_dict()
    )
