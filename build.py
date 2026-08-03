#!/usr/bin/env python3
"""
build.py — rebuild the Quidi Vidi regatta rowing flag outlook with fresh data.

Pipeline:
  1. Fetch ECCC RDPS (temp, wind speed/dir, cloud, 1h precip) from GeoMet WMS
     GetFeatureInfo at Quidi Vidi Lake, for a Friday-noon -> Sunday-midnight window.
  2. Fetch The Weather Company hourly forecast (temp, sky phrase, POP, cloud) for
     the same point (used for sky, temperature and shower chance).
  3. Compute:
       - data/final.json : merged per-hour record (rdps + twc) for the technical meteogram
       - data/rowing.json: per-hour rowing metrics + Green/Yellow/Red flag
  4. Inject both arrays into regatta_meteogram.html and refresh the run/date labels.

Run:   TWC_API_KEY=xxxxx  python build.py
Deps:  standard library only (urllib, json, math, concurrent.futures).

Design decisions baked in (from the committee's guidance):
  - Course axis is SW(225)-NE(45); a SW wind blows straight down the course.
  - Flag is driven by ECCC RDPS sustained wind. Red > 30 km/h sustained,
    Yellow 20-30, Green <= 20.
  - South-shadow correction: only winds FROM the south sector (within +/-30 deg
    of due south) are discounted (lake sits in the lee); all other directions
    are taken at face value.
"""
import json, math, os, re, sys, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------- config
LAT, LON   = 47.582, -52.685          # Quidi Vidi Lake
NDT_OFFSET = timedelta(hours=2, minutes=30)   # NDT = UTC-2:30
HTML       = os.path.join(os.path.dirname(__file__), "regatta_meteogram.html")
DATA_DIR   = os.path.join(os.path.dirname(__file__), "data")

# course + rowability model
AXIS_BEARING = 45.0     # start(SW) -> buoys(NE)
CROSS_FETCH  = 300.0    # m, effective cross-axis fetch
BUOYS_FETCH  = 1200.0   # m, fetch to the far turn
G            = 9.81

GEOMET = "https://geo.weather.gc.ca/geomet"
RDPS_LAYERS = {
    "temp":     "RDPS_10km_AirTemp_2m",
    "wspd":     "RDPS_10km_WindSpeed_10m",
    "wdir":     "RDPS_10km_WindDir_10m",
    "cloud":    "RDPS_10km_TotalCloudCover",
    "precip1h": "RDPS_10km_Precip-Accum1h",
}

# ---------------------------------------------------------------- geomet
_run_seen = {}
def geomet(layer, tiso=None):
    d = 0.05
    p = {"SERVICE":"WMS","VERSION":"1.1.1","REQUEST":"GetFeatureInfo","LAYERS":layer,
         "QUERY_LAYERS":layer,"SRS":"EPSG:4326",
         "BBOX":f"{LON-d},{LAT-d},{LON+d},{LAT+d}","WIDTH":101,"HEIGHT":101,
         "X":50,"Y":50,"INFO_FORMAT":"application/json"}
    if tiso: p["TIME"] = tiso
    try:
        with urllib.request.urlopen(f"{GEOMET}?{urllib.parse.urlencode(p)}", timeout=45) as r:
            fs = json.load(r).get("features", [])
        if fs:
            _run_seen["run"] = fs[0]["properties"].get("dim_reference_time")
            return fs[0]["properties"].get("value")
    except Exception:
        return None
    return None

def fetch_rdps():
    # window: from max(run start, Fri 12Z) through Sun 00Z, hourly
    _, run = None, None
    val, run = geomet("RDPS_10km_WindSpeed_10m"), _run_seen.get("run")
    run_dt = datetime.strptime(run, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    # anchor on the Saturday of the run's week
    sat = run_dt + timedelta((5 - run_dt.weekday()) % 7)   # next Saturday
    start = max(run_dt, (sat - timedelta(hours=13))).replace(minute=0, second=0, microsecond=0)  # ~Fri 12Z rel
    start = max(run_dt, datetime(sat.year, sat.month, sat.day, 0, tzinfo=timezone.utc) - timedelta(hours=12))
    start = start.replace(minute=0, second=0, microsecond=0)
    end   = datetime(sat.year, sat.month, sat.day, 0, tzinfo=timezone.utc) + timedelta(hours=24)  # Sun 00Z
    times, t = [], start
    while t <= end:
        times.append(t.strftime("%Y-%m-%dT%H:%M:%SZ")); t += timedelta(hours=1)
    jobs = [(k, l, ts) for ts in times for k, l in RDPS_LAYERS.items()]
    res = {}
    def one(j):
        k, l, ts = j; return (ts, k, geomet(l, ts))
    with ThreadPoolExecutor(max_workers=16) as ex:
        for ts, k, v in ex.map(one, jobs):
            res.setdefault(ts, {})[k] = v
    return times, res, _run_seen.get("run")

# ---------------------------------------------------------------- twc
def fetch_twc():
    key = os.environ.get("TWC_API_KEY")
    if not key:
        sys.exit("Set TWC_API_KEY in the environment.")
    url = (f"https://api.weather.com/v3/wx/forecast/hourly/15day?geocode={LAT},{LON}"
           f"&units=m&language=en-US&format=json&apiKey={key}")
    tw = json.load(urllib.request.urlopen(url, timeout=40))
    out = {}
    for i, vt in enumerate(tw["validTimeUtc"]):
        ts = datetime.fromtimestamp(vt, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out[ts] = dict(temp=tw["temperature"][i], wspd=tw["windSpeed"][i], gust=tw["windGust"][i],
                       wdir=tw["windDirection"][i], cloud=tw["cloudCover"][i],
                       pop=tw["precipChance"][i], phrase=tw["wxPhraseLong"][i])
    return out

def emoji(p):
    p = (p or "").lower()
    if "thunder" in p: return "⛈️"
    if "rain" in p or "shower" in p:
        return "\U0001f326️" if any(w in p for w in ("few","isolated","scattered")) else "\U0001f327️"
    if "fog" in p or "mist" in p: return "\U0001f32b️"
    if "mostly cloudy" in p: return "\U0001f325️"
    if any(w in p for w in ("partly","few clouds","mostly sunny","mostly clear")): return "⛅"
    if "cloud" in p: return "☁️"
    if any(w in p for w in ("sun","clear","fair")): return "☀️"
    return "☁️"

def wxcls(cloud, precip):
    pp = precip or 0
    if pp >= 0.5: return "rain"
    if pp >= 0.1: return "showers"
    c = cloud or 0
    return "sunny" if c < 15 else "mostly-sunny" if c < 50 else "mostly-cloudy" if c < 85 else "cloudy"

# ---------------------------------------------------------------- rowability model
def wave_hs(u_ms, fetch_m):
    if u_ms <= 0 or fetch_m <= 0: return 0.0
    x = G * fetch_m / u_ms**2
    return min(0.0016 * x**0.5, 0.243) * u_ms**2 / G          # metres (fetch-limited)

def eff_fetch(fetch_m, wind_from):
    a = abs((wind_from - AXIS_BEARING + 90) % 180 - 90)
    return max(fetch_m * max(math.cos(math.radians(a)), 0),
               min(CROSS_FETCH, fetch_m) * math.sin(math.radians(a)))

def decompose(spd, f):
    d = math.radians(f - AXIS_BEARING)
    return -spd * math.cos(d), abs(spd * math.sin(d))         # (along +toward buoys, cross)

def relword(along, cross, spd):
    if spd < 3: return "calm"
    return ("down-course" if along > 0 else "up-course") if abs(along) >= cross else "cross-course"

def south_shadow(f):
    diff = abs(((f - 180 + 180) % 360) - 180)                 # angular distance from due south
    if diff > 30: return 1.0
    return 1 - 0.4 * math.cos(math.radians(diff * 3))         # 0.6 at S -> 1.0 at 30 deg off

def flag(spd):
    if spd > 30: return ("red", "RED")
    if spd > 20: return ("yellow", "YELLOW")
    return ("green", "GREEN")

def compass(d):
    return ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"][round((d%360)/22.5)%16]

def metrics(spd, f):
    if spd is None or f is None: return {}
    adj = spd * south_shadow(f)
    along, cross = decompose(adj, f)
    return {"raw": round(spd), "adj": round(adj), "dir": f, "card": compass(f),
            "hs": round(wave_hs(adj/3.6, eff_fetch(BUOYS_FETCH, f)) * 100),
            "cross": round(cross), "rel": relword(along, cross, adj)}

# ---------------------------------------------------------------- build json
def build(times, rdps, twc):
    final, rowing = [], []
    for ts in times:
        r = rdps[ts]; t = twc.get(ts, {})
        lo = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) - NDT_OFFSET
        spd = r["wspd"] * 3.6 if r["wspd"] is not None else None
        final.append({
            "utc": ts, "ndt": lo.strftime("%Y-%m-%dT%H:%M"), "day": lo.strftime("%a"),
            "hour": lo.hour, "dow": lo.strftime("%Y-%m-%d"),
            "rdps": {"temp": round(r["temp"],1) if r["temp"] is not None else None,
                     "wspd": round(spd,1) if spd is not None else None,
                     "gust": round(spd*1.5,1) if spd is not None else None,
                     "wdir": round(r["wdir"]) if r["wdir"] is not None else None,
                     "cloud": r["cloud"], "wx": wxcls(r["cloud"], r["precip1h"])},
            "twc": {"temp": t.get("temp"), "wspd": t.get("wspd"), "gust": t.get("gust"),
                    "wdir": t.get("wdir"), "cloud": t.get("cloud"), "pop": t.get("pop"),
                    "phrase": t.get("phrase"), "icon": None, "emoji": emoji(t.get("phrase"))}})
    for d0 in final:
        o = {"utc": d0["utc"], "ndt": d0["ndt"], "day": d0["day"], "hour": d0["hour"],
             "dow": d0["dow"], "emoji": d0["twc"]["emoji"], "phrase": d0["twc"]["phrase"],
             "pop": d0["twc"]["pop"], "tw_temp": d0["twc"]["temp"], "rd_temp": d0["rdps"]["temp"]}
        o["twc"]  = metrics(d0["twc"]["wspd"], d0["twc"]["wdir"])    # kept for the wave-comparison line
        o["rdps"] = metrics(d0["rdps"]["wspd"], d0["rdps"]["wdir"])
        R = o["rdps"]                                                # FLAG driven by RDPS wind
        o["adj_worst"] = R.get("adj", 0)
        o["dir_card"]  = R.get("card", "–")
        o["downdc"]    = (R.get("rel") == "down-course" and R.get("adj", 0) >= 15)
        o["flag"], o["flagLab"] = flag(R.get("adj", 0))
        rowing.append(o)
    return final, rowing

def inject(final, rowing, run):
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump(final,  open(os.path.join(DATA_DIR, "final.json"),  "w"), separators=(",", ":"))
    json.dump(rowing, open(os.path.join(DATA_DIR, "rowing.json"), "w"), separators=(",", ":"))
    h = open(HTML).read()
    h = re.sub(r"const ROW = \[.*?\];",  lambda m: "const ROW = "  + json.dumps(rowing, separators=(",",":")) + ";", h, count=1, flags=re.S)
    h = re.sub(r"const DATA = \[.*?\];", lambda m: "const DATA = " + json.dumps(final,  separators=(",",":")) + ";", h, count=1, flags=re.S)
    if run:
        label = datetime.strptime(run, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %HZ")
        h = re.sub(r"run \d{4}-\d\d-\d\d \d\dZ", f"run {label}", h)
    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    h = re.sub(r"generated \d{4}-\d\d-\d\d", f"generated {gen}", h)
    open(HTML, "w").write(h)
    print(f"Wrote {HTML}, data/final.json, data/rowing.json")

def main():
    print("Fetching RDPS from GeoMet ...")
    times, rdps, run = fetch_rdps()
    print(f"  run {run}, {len(times)} hourly steps")
    print("Fetching TWC ...")
    twc = fetch_twc()
    final, rowing = build(times, rdps, twc)
    inject(final, rowing, run)
    sat = [o for o in rowing if 6 <= o["hour"] <= 17 and o["dow"] == max({o2['dow'] for o2 in rowing})]
    flags = {}
    for o in rowing:
        if 6 <= o["hour"] <= 17:
            flags[o["flagLab"]] = flags.get(o["flagLab"], 0) + 1
    print("Flag tally (all daytime hours):", flags)

if __name__ == "__main__":
    main()
