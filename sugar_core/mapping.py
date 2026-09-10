from __future__ import annotations

import html
from pathlib import Path

import pandas as pd


def _coordinates(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    for name in ("latitude", "longitude"):
        if name not in work: return work.iloc[0:0]
        work[name] = pd.to_numeric(work[name].astype("string").str.replace(r"^'", "", regex=True), errors="coerce")
    return work.dropna(subset=["latitude", "longitude"])


def create_map(df: pd.DataFrame, output_file: str | Path) -> str:
    import folium
    from folium.plugins import HeatMap, MarkerCluster

    work = _coordinates(df)
    if work.empty: raise ValueError("No valid coordinates are available to map.")
    m = folium.Map(location=[work.latitude.mean(), work.longitude.mean()], zoom_start=2,
                   tiles="CartoDB positron", control_scale=True)
    cluster = MarkerCluster(name="Collected observations").add_to(m)
    for _, row in work.iterrows():
        author = row.get("author_handle", row.get("username", ""))
        text = row.get("translated_text", row.get("translated_en", "")) or row.get("original_text", "")
        place = row.get("inferred_location", "")
        url = row.get("canonical_url", row.get("post_url", ""))
        popup = (
            f"<b>{html.escape(str(author))}</b><br>{html.escape(str(place))}<br>"
            f"{html.escape(str(text))[:1200]}<br><a href='{html.escape(str(url))}' target='_blank'>Open source</a>"
        )
        folium.Marker([row.latitude, row.longitude], popup=folium.Popup(popup, max_width=420)).add_to(cluster)
    if "published_at" in work or "date_iso" in work:
        date_col = "published_at" if "published_at" in work else "date_iso"
        dates = pd.to_datetime(work[date_col], errors="coerce", utc=True)
        now = pd.Timestamp.now(tz="UTC")
        for days in (7, 30, 90, 365):
            mask = dates.ge(now - pd.Timedelta(days=days)) & dates.le(now)
            points = work.loc[mask, ["latitude", "longitude"]].values.tolist()
            layer = folium.FeatureGroup(name=f"Activity heatmap — {days}d", show=(days == 30))
            if points: HeatMap(points, radius=24, blur=18).add_to(layer)
            layer.add_to(m)
    folium.LayerControl().add_to(m)
    output_file = str(Path(output_file).expanduser().resolve())
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    m.save(output_file)
    return output_file
