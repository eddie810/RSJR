# Quidi Vidi Regatta — Rowing Flag Outlook

A committee-facing **Green / Yellow / Red** rowing outlook for the Royal St. John's
Regatta on Quidi Vidi Lake. Self-contained HTML (all data embedded), plus the
Python that rebuilds it from live forecasts.

## What's in here

| File | What it is |
|------|------------|
| `regatta_meteogram.html` | **The page.** Self-contained (data, styles, charts all inline). Open in any browser. |
| `regatta_squarespace_embed.html` | Paste-into-a-Code-Block embed — runs the page inside an **isolated iframe** so a host site's CSS can't affect it. Use this to embed on Squarespace etc. |
| `regatta_squarespace_iframe.html` | Tiny `<iframe src="URL">` snippet if you'd rather host the file and point at it. |
| `build.py` | Rebuilds the page from fresh data (fetch → compute → inject). |
| `quidi_vidi_waves.py` | Stand-alone fetch-limited wave calculator (the model `build.py` uses). |
| `data/rowing.json` | Per-hour rowing metrics + flag (what the timeline reads). |
| `data/final.json` | Per-hour merged RDPS+TWC record (what the technical meteogram reads). |

The `data/*.json` files are also embedded inside `regatta_meteogram.html` as
`const ROW = …` and `const DATA = …`; the JSON copies are for reference / reuse.

## Rebuild with fresh data

```bash
export TWC_API_KEY=your_weather_company_key
python build.py
```

This fetches the latest **ECCC RDPS** run (via GeoMet WMS) and the latest
**The Weather Company** hourly forecast for Quidi Vidi Lake, recomputes both JSON
files, and rewrites the `ROW`/`DATA` arrays and run/date labels inside
`regatta_meteogram.html`. Standard library only — no pip installs.

## How the flag works

- **Course axis is SW → NE.** A southwesterly blows straight down the course
  (longest fetch, worst chop at the NE turn buoys, headwind home). Easterlies run
  up the course; NW/SE winds blow across it.
- **Flag = ECCC RDPS sustained wind.** `Red > 30 km/h`, `Yellow 20–30`,
  `Green ≤ 20`. The Weather Company supplies sky, temperature and shower chance.
- **South-shadow correction.** Only winds *from the south sector* (within ±30° of
  due south) are discounted (the lake sits in the lee and models over-forecast
  southerlies); every other direction is taken at face value.
- **Waves** are a fetch-limited estimate (`quidi_vidi_waves.py`) at the 1.2 km turn.

Tuning knobs live at the top of `build.py` (`LAT/LON`, `AXIS_BEARING`,
`CROSS_FETCH`, `BUOYS_FETCH`, and the `flag()` / `south_shadow()` functions).

## Notes

- Times shown on the page are **Newfoundland Daylight (NDT, UTC−2:30)**.
- The page is theme-aware (light/dark) and mobile-friendly (the hourly flags are a
  3-wide grid). It is **not** an official race-day decision tool — treat it as an
  outlook and re-check as race day nears.
