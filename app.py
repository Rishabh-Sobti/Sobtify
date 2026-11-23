"""
Spotify listening dashboard.
Input: history_with_features.csv (output of fetch_audio_features.py). Nothing else.

Run locally:   streamlit run app.py
"""
import os
from zoneinfo import available_timezones

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

st.set_page_config(page_title="Sobtify", page_icon="🎧", layout="wide")

LOCAL_FILE = "history_with_features.csv"  # used automatically if present next to app.py
REQUIRED = ["ts", "ms_played", "master_metadata_track_name", "master_metadata_album_artist_name"]
OPTIONAL = ["spotify_track_uri"]
UNIT_FEATURES = ["valence", "energy", "danceability", "acousticness",
                 "instrumentalness", "speechiness", "liveness"]
EXTRA_FEATURES = {"tempo": "Tempo (BPM)", "loudness": "Loudness (dB)"}
# Only these columns are ever loaded, so ip_addr, platform, etc. never enter memory.
WANTED = set(REQUIRED + OPTIONAL + UNIT_FEATURES + list(EXTRA_FEATURES))


# ---------- helpers ----------
def read_csv(src):
    return pd.read_csv(src, usecols=lambda c: c in WANTED)


def prepare(raw, tz):
    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        return None, missing
    df = raw.dropna(subset=REQUIRED).copy()  # drops podcasts / unknown tracks
    df["ms_played"] = pd.to_numeric(df["ms_played"], errors="coerce")
    ts = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    keep = ts.notna() & df["ms_played"].notna()
    df, ts = df[keep].copy(), ts[keep]
    local = ts.dt.tz_convert(tz)
    df["day"] = local.dt.tz_localize(None).dt.normalize()
    df["hour"] = local.dt.hour
    df["minutes"] = df["ms_played"] / 60000
    df["artist"] = df["master_metadata_album_artist_name"]
    df["track"] = df["master_metadata_track_name"]
    fallback = df["artist"] + "||" + df["track"]
    df["track_key"] = df["spotify_track_uri"].fillna(fallback) if "spotify_track_uri" in df else fallback
    return df, []


def wide_button(label, key, on_click, args, selected):
    kw = dict(key=key, on_click=on_click, args=args, type="primary" if selected else "secondary")
    try:
        return st.button(label, width="stretch", **kw)  # newer Streamlit
    except TypeError:
        return st.button(label, use_container_width=True, **kw)  # older Streamlit


def pick_artist(name):
    st.session_state.artist = None if st.session_state.artist == name else name
    st.session_state.track = None
    st.session_state.track_label = None


def pick_track(key, label):
    if st.session_state.track == key:
        st.session_state.track, st.session_state.track_label = None, None
    else:
        st.session_state.track, st.session_state.track_label = key, label


def clear_filters():
    st.session_state.artist = None
    st.session_state.track = None
    st.session_state.track_label = None


for k in ("artist", "track", "track_label"):
    st.session_state.setdefault(k, None)

# ---------- sidebar: data + settings ----------
with st.sidebar:
    st.header("Data")
    up = st.file_uploader("Upload history_with_features.csv", type="csv")
    tz_options = sorted(available_timezones()) or ["UTC", "Asia/Kolkata"]
    tz = st.selectbox("Timezone", tz_options,
                      index=tz_options.index("Asia/Kolkata") if "Asia/Kolkata" in tz_options else 0,
                      help="Spotify timestamps are UTC. Hour-of-day is computed in this timezone.")
    min_sec = st.number_input("Count a play only if played for at least (seconds)", 0, 600, 30, step=5,
                              help="Spotify counts a stream after 30 seconds.")
    rank_by = st.radio("Rank top 5 by", ["Minutes", "Plays"], horizontal=True)

if up is not None:
    src, src_id = up, ("upload", up.name, up.size)
elif os.path.exists(LOCAL_FILE):
    src, src_id = LOCAL_FILE, ("local", os.path.getmtime(LOCAL_FILE))
else:
    st.title("🎧 Spotify Listening Dashboard")
    st.info("Upload **history_with_features.csv** in the sidebar to begin.")
    st.stop()

if st.session_state.get("raw_id") != src_id:
    with st.spinner("Reading file..."):
        st.session_state.raw = read_csv(src)
    st.session_state.raw_id = src_id
    st.session_state.pop("prep_id", None)
    clear_filters()

prep_id = (src_id, tz)
if st.session_state.get("prep_id") != prep_id:
    df, missing = prepare(st.session_state.raw, tz)
    if missing:
        st.error(f"The file is missing required columns: {', '.join(missing)}")
        st.stop()
    st.session_state.df, st.session_state.prep_id = df, prep_id
df = st.session_state.df
if df.empty:
    st.error("No usable track plays found in this file.")
    st.stop()

unit_present = [c for c in UNIT_FEATURES if c in df.columns]
extra_present = {c: lbl for c, lbl in EXTRA_FEATURES.items() if c in df.columns}
all_features = unit_present + list(extra_present)

# ---------- period slider ----------
dmin, dmax = df["day"].min().date(), df["day"].max().date()
with st.sidebar:
    if dmin < dmax:
        start, end = st.slider("Period", min_value=dmin, max_value=dmax,
                               value=(dmin, dmax), format="DD MMM YYYY")
    else:
        start = end = dmin
        st.caption(f"All data is from {dmin:%d %b %Y}.")

n_days = (end - start).days + 1
base = df[(df["day"] >= pd.Timestamp(start)) & (df["day"] <= pd.Timestamp(end))
          & (df["ms_played"] >= min_sec * 1000)]

st.title("🎧 Spotify Listening Dashboard")
st.caption(f"{start:%d %b %Y} to {end:%d %b %Y} · {n_days:,} days · times in {tz}")

if base.empty:
    st.warning("No plays in this period with the current settings.")
    st.stop()

# ---------- apply tile filters ----------
f = base
if st.session_state.artist:
    f = f[f["artist"] == st.session_state.artist]
if st.session_state.track:
    f = f[f["track_key"] == st.session_state.track]

parts = []
if st.session_state.artist:
    parts.append(f"Artist: **{st.session_state.artist}**")
if st.session_state.track:
    parts.append(f"Song: **{st.session_state.track_label}**")
if parts:
    c1, c2 = st.columns([6, 1])
    c1.markdown("Filtering by " + " · ".join(parts) + ". Click the highlighted tile again to remove it.")
    c2.button("Clear filters", on_click=clear_filters)

if f.empty:
    st.warning("The selected artist/song has no plays in this period. Clear the filters or widen the period.")
    st.stop()

# ---------- KPIs ----------
total_min = f["minutes"].sum()
k = st.columns(5)
k[0].metric("Total minutes", f"{total_min:,.0f}")
k[1].metric("Artists", f"{f['artist'].nunique():,}")
k[2].metric("Unique songs", f"{f['track_key'].nunique():,}")
k[3].metric("Total plays", f"{len(f):,}")
k[4].metric("Avg minutes / day", f"{total_min / n_days:,.1f}")

# ---------- top 5 tiles ----------
rank_col = "minutes" if rank_by == "Minutes" else "plays"

artists = (base.groupby("artist").agg(minutes=("minutes", "sum"), plays=("minutes", "size"))
           .sort_values(rank_col, ascending=False).head(5).reset_index())

tbase = base[base["artist"] == st.session_state.artist] if st.session_state.artist else base
tracks = (tbase.groupby("track_key")
          .agg(track=("track", "first"), artist=("artist", "first"),
               minutes=("minutes", "sum"), plays=("minutes", "size"))
          .sort_values(rank_col, ascending=False).head(5).reset_index())

st.subheader("Top 5 artists")
cols = st.columns(5)
for i, row in artists.iterrows():
    with cols[i]:
        wide_button(f"**{i + 1}. {row['artist']}**  \n{row['minutes']:,.0f} min · {row['plays']:,} plays",
                    f"artist_tile_{i}", pick_artist, (row["artist"],),
                    st.session_state.artist == row["artist"])

heading = f"Top 5 songs by {st.session_state.artist}" if st.session_state.artist else "Top 5 songs"
st.subheader(heading)
cols = st.columns(5)
for i, row in tracks.iterrows():
    with cols[i]:
        label = f"{row['track']} ({row['artist']})"
        wide_button(f"**{i + 1}. {row['track']}**  \n{row['artist']} · {row['plays']:,} plays",
                    f"track_tile_{i}", pick_track, (row["track_key"], label),
                    st.session_state.track == row["track_key"])

# ---------- hour-of-day charts ----------
hours = list(range(24))
left, right = st.columns(2)

with left:
    st.subheader("Listening by hour of day")
    per_hour = f.groupby("hour")["minutes"].sum().reindex(hours, fill_value=0) / n_days
    fig1 = go.Figure(go.Bar(x=hours, y=per_hour.values,
                            hovertemplate="%{x}:00 · %{y:.1f} min/day<extra></extra>"))
    fig1.update_layout(xaxis=dict(title="Hour of day", dtick=1), yaxis_title="Avg minutes per day",
                       margin=dict(t=10, b=10))
    st.plotly_chart(fig1)
    st.caption("Total minutes in each hour divided by the number of days in the period, "
               "so the bars add up to the 'Avg minutes / day' KPI.")

with right:
    st.subheader("Audio features by hour of day")
    if not all_features:
        st.info("No audio feature columns found in this file.")
    else:
        chosen = st.multiselect("Features (0 to 1 scale)", unit_present,
                                default=[c for c in ["valence", "energy", "danceability"] if c in unit_present])
        sec_options = ["None"] + list(extra_present.values())
        sec_label = st.radio("Secondary axis", sec_options, horizontal=True)
        sec_col = next((c for c, lbl in extra_present.items() if lbl == sec_label), None)

        plot_cols = chosen + ([sec_col] if sec_col else [])
        if not plot_cols:
            st.info("Pick at least one feature.")
        else:
            means = f.groupby("hour")[plot_cols].mean().reindex(hours)
            fig2 = make_subplots(specs=[[{"secondary_y": True}]])
            for c in chosen:
                fig2.add_trace(go.Scatter(x=hours, y=means[c], mode="lines+markers", name=c), secondary_y=False)
            if sec_col:
                fig2.add_trace(go.Scatter(x=hours, y=means[sec_col], mode="lines+markers",
                                          name=extra_present[sec_col], line=dict(dash="dot")),
                               secondary_y=True)
            fig2.update_xaxes(title_text="Hour of day", dtick=1)
            fig2.update_yaxes(title_text="Feature value (0 to 1)", range=[0, 1], secondary_y=False)
            if sec_col:
                fig2.update_yaxes(title_text=extra_present[sec_col], secondary_y=True)
            fig2.update_layout(legend=dict(orientation="h", y=-0.25), margin=dict(t=10, b=10))
            st.plotly_chart(fig2)
            coverage = f[plot_cols].notna().any(axis=1).mean()
            st.caption(f"Average per play. {coverage:.0%} of plays in this selection have audio features; "
                       "the rest are ignored. Hours with few plays can look noisy.")
