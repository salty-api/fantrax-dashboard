#!/usr/bin/env python3
"""Build link-preview assets (needs Google Chrome + macOS sips).

- docs/og.png          site-wide 1200x630 card
- docs/p/<pid>/        (600x315 card) stub page per player: own og:title/description/image, then redirects to
                       /#whohas/<pid>. iMessage/Slack never see the # part, so share these URLs.
- docs/t/<tab>/        stub page per tab with its own title/description (shared site card)
Run after build_dashboard.py. Cards are redrawn only when what they show (name, team, owner history) changes, or with --force.
Works on macOS (sips) and Linux (Chrome + ImageMagick) so a GitHub Action can run it.
"""
import hashlib, html, json, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE = "https://fantrax.whohashim.com"
CHROME = next((c for c in (shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser"),
               "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome") if c and Path(c).exists()), None)
LINUX = sys.platform.startswith("linux")
MANIFEST = ROOT / "data" / "cards.json"  # card id -> hash of what the card shows (name, team, owners, ...)
FORCE = "--force" in sys.argv

CSS = """*{box-sizing:border-box;margin:0;padding:0}body{width:1200px;height:630px;overflow:hidden;background:#0f1117;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,'Liberation Sans',sans-serif;color:#f8fafc;position:relative}
.bar{position:absolute;left:0;top:0;bottom:0;width:14px;background:#f97316}
.brand{position:absolute;left:70px;top:48px;font-size:26px;font-weight:700;letter-spacing:.14em;color:#f97316;text-transform:uppercase}
.dom{position:absolute;right:60px;top:50px;font-size:24px;color:#64748b}"""


def slug(o):
    return re.sub(r"[^a-z0-9]+", "-", o.lower()).strip("-")


def load():
    h = (DOCS / "index.html").read_text()
    return json.loads(re.search(r"const D = (\{.*?\});\n", h, re.S).group(1))


def card_site(D):
    champs = {}
    for r in D["rows"]:
        if r["fin"] == "Champion":
            champs.setdefault(r["o"], []).append(r["s"])
    rows = "".join(
        f"<div style='display:flex;align-items:center;gap:18px;margin:10px 0;font-size:34px'>"
        f"<img src='file://{DOCS}/logos/{slug(o)}.webp' style='width:56px;height:56px;border-radius:12px'>"
        f"<b>{o}</b><span style='color:#94a3b8;font-size:26px'>{' · '.join(sorted(ss))}</span>"
        f"<span style='font-size:30px'>{'🏆' * len(ss)}</span></div>"
        for o, ss in sorted(champs.items(), key=lambda x: -len(x[1])))
    return f"""<style>{CSS}</style><div class=bar></div><div class=brand>Big Baller Brand</div><div class=dom>fantrax.whohashim.com</div>
<div style='position:absolute;left:70px;top:140px;right:60px'>
<div style='font-size:64px;font-weight:700;line-height:1.1'>Fantasy Basketball<br>League History</div>
<div style='font-size:26px;color:#94a3b8;margin:16px 0 26px'>{len(D['seasons'])} seasons · {len(D['owners'])} owners · all-time standings, records, rivalries and who-has-him</div>
<div style='font-size:20px;letter-spacing:.12em;color:#64748b;text-transform:uppercase;margin-bottom:6px'>Champions</div>{rows}</div>"""


def card_player(D, pid):
    n, pos = D["players"][pid]
    S = D["stats"].get(pid)
    st = D["stints"].get(pid, [])
    cur = st[-1][1] if st else None
    nowS = D["seasonsAll"][-1]
    tm = S["tm"] if S and S.get("tm") and S["tm"] != "(N/A)" else ""
    photo = (f"<img src='https://fantraximg.com/si/headshots/NBA/hs{pid}_96_{D['heads'][pid]}.png' "
             f"style='width:290px;height:290px;border-radius:50%;border:6px solid #f97316;background:#1e293b;object-fit:cover;object-position:top'>"
             if pid in D["heads"] else "")
    stats = ""
    if S and S.get("g"):
        cell = lambda k, v: f"<div style='text-align:center;min-width:120px'><div style='font-size:46px;font-weight:700'>{v}</div><div style='font-size:17px;color:#64748b;letter-spacing:.1em'>{k}</div></div>"
        stats = (f"<div style='display:flex;gap:34px;margin-top:34px'>{cell('FP RANK', '#' + str(S['rk']))}{cell('FP/G', format(S['fpg'], '.1f'))}"
                 f"{cell('PTS', format(S['pts'], '.1f'))}{cell('REB', format(S['reb'], '.1f'))}{cell('AST', format(S['ast'], '.1f'))}</div>"
                 f"<div style='font-size:17px;color:#64748b;margin-top:10px'>{D['statsSeason']} per game</div>")
    seasons = {}
    for x in st:
        seasons.setdefault(x[0], x[1])
    strip = "".join(
        f"<div style='text-align:center'><img src='file://{DOCS}/logos/{slug(o)}.webp' style='width:62px;height:62px;border-radius:12px'>"
        f"<div style='font-size:15px;color:#64748b;margin-top:4px'>{s[2:4]}-{s[-2:]}</div></div>"
        for s, o in sorted(seasons.items()))
    return f"""<style>{CSS}</style><div class=bar></div><div class=brand>Who Has Him</div><div class=dom>fantrax.whohashim.com</div>
<div style='position:absolute;left:80px;top:170px'>{photo}</div>
<div style='position:absolute;left:450px;top:140px;right:50px'>
<div style='font-size:{58 if len(n) < 20 else 46}px;font-weight:700;line-height:1.05'>{html.escape(n)}</div>
<div style='font-size:28px;color:#94a3b8;margin-top:10px'>{' · '.join(x for x in (pos, tm) if x)}</div>
{stats}
<div style='margin-top:30px;display:flex;gap:18px;align-items:flex-end'>{strip}</div></div>"""


def to_jpeg(png, out):
    if shutil.which("sips"):
        cmd = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "55", str(png), "--out", str(out)]
    else:
        cmd = [shutil.which("magick") or shutil.which("convert"), str(png), "-quality", "55", str(out)]
    subprocess.run(cmd, capture_output=True, check=True)


def shoot(args):
    """Render one card. Cards are only redrawn when `key` (what the card shows) changed, or with --force."""
    name, body, out, key = args
    scale = 0.5 if out.suffix == ".jpg" else 1  # player cards are half size (600x315)
    h = hashlib.sha1(key.encode()).hexdigest()[:12]
    if not FORCE and out.exists() and MANIFEST_DATA.get(name, h) == h:
        MANIFEST_DATA[name] = h  # unchanged (or adopting an existing card)
        return
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "c.html"
        f.write_text(f"<!doctype html><meta charset=utf-8>{body}")
        png = Path(t) / "c.png"
        flags = ["--no-sandbox"] if LINUX else []
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", *flags,
                        f"--force-device-scale-factor={scale}", "--window-size=1200,630",
                        "--virtual-time-budget=5000", f"--screenshot={png}", f"file://{f}"], capture_output=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix == ".png":
            png.replace(out)
        else:
            to_jpeg(png, out)
    MANIFEST_DATA[name] = h


MANIFEST_DATA = json.load(open(MANIFEST)) if MANIFEST.exists() else {}


STUB = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><meta name="description" content="{desc}">
<meta property="og:type" content="website"><meta property="og:site_name" content="Big Baller Brand">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{img}">
<meta property="og:image:width" content="{w}"><meta property="og:image:height" content="{h}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}"><meta name="twitter:image" content="{img}">
<meta name="theme-color" content="#0c0f18">
<script>location.replace("/{hash}")</script><meta http-equiv="refresh" content="0;url=/{hash}"></head>
<body style="background:#0f1117;color:#e2e8f0;font-family:sans-serif;padding:40px"><a href="/{hash}" style="color:#f97316">Open {esc}</a></body></html>"""

TABS = {"alltime": ("All-Time", "All-time standings, titles, win % and points per game for every owner."),
        "seasons": ("Seasons", "Final standings and playoff brackets for every season."),
        "owner": ("Owners", "Owner profiles with season-by-season finishes and head-to-head records."),
        "records": ("Records", "Highest scores, biggest blowouts, closest wins and longest streaks."),
        "rivalry": ("Rivalry", "Head-to-head history between any two owners."),
        "recap": ("Weekly Recap", "Scoreboard, standings and top performers for each week."),
        "whohas": ("Who Has Him", "Draft and ownership history for every player in the league.")}


def write_stub(path, title, desc, url, img, hash_, w=1200, h=630):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STUB.format(title=html.escape(title, True), desc=html.escape(desc, True), url=url, img=img,
                                hash=hash_, esc=html.escape(title), w=w, h=h))


def main():
    D = load()
    if not CHROME:
        sys.exit("ERROR: no Chrome/Chromium found")
    champs = sorted((r["s"], r["o"]) for r in D["rows"] if r["fin"] == "Champion")
    jobs = [("site", card_site(D), DOCS / "og.png", json.dumps([champs, len(D["seasons"])]))]
    for pid in D["players"]:
        S = D["stats"].get(pid) or {}
        owners = sorted({(x[0], x[1]) for x in D["stints"].get(pid, [])})
        key = json.dumps([D["players"][pid], S.get("tm"), D["heads"].get(pid), owners])  # identity only: weekly stat changes don't redraw
        jobs.append((pid, card_player(D, pid), DOCS / "p" / pid / "card.jpg", key))
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(shoot, jobs))
    json.dump(MANIFEST_DATA, open(MANIFEST, "w"), sort_keys=True, indent=0)
    # stubs
    nowS = D["seasonsAll"][-1]
    for pid, (n, pos) in D["players"].items():
        st = D["stints"].get(pid, [])
        S = D["stats"].get(pid)
        cur = st[-1][1] if st else None
        bits = [f"{pos}" if pos else "", f"Currently on {cur} ({nowS})" if cur else ""]
        if S and S.get("g"):
            bits.append(f"{D['statsSeason']}: {S['pts']:.1f} PTS, {S['reb']:.1f} REB, {S['ast']:.1f} AST, #{S['rk']} in fantasy points")
        owners = len({x[1] for x in st})
        bits.append(f"{owners} owner{'s' if owners != 1 else ''} since {D['seasonsAll'][0]}")
        write_stub(DOCS / "p" / pid / "index.html", f"{n} | Who Has Him", " · ".join(b for b in bits if b),
                   f"{SITE}/p/{pid}/", f"{SITE}/p/{pid}/card.jpg", f"#whohas/{pid}", 600, 315)
    for k, (t, d) in TABS.items():
        write_stub(DOCS / "t" / k / "index.html", f"{t} | Big Baller Brand", d, f"{SITE}/t/{k}/", f"{SITE}/og.png", f"#{k}")
    print(len(D["players"]), "player stubs,", len(TABS), "tab stubs")


if __name__ == "__main__":
    main()
