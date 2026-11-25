"""AH-Übersicht für WoW Forever.

Liest die AH-Scans von NaowhForever aus den SavedVariables, rechnet Materialkosten
und Gewinn für die Taschen aus und schreibt docs/index.html (GitHub Pages).
Mit --push wird die Seite danach committet und gepusht, falls sie sich geändert hat.
"""
from __future__ import annotations

import html
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------- Einstellungen
WOW = Path(r"D:\Spiele\World of Warcraft\_forever_")
ACCOUNT = "1205901586#1"      # Account-Ordner unter WTF\Account, dessen Scans zählen
FACTION = "Alliance"          # Alliance, Horde oder Blackwater
AH_CUT = 0.05                 # Auktionshaus-Gebühr auf den Verkaufspreis

# Taschen: (Item-ID, deutscher Name, Rezept-Zauber-ID, Plätze)
# Namen und Plätze laut Wowhead Classic (deutscher Client)
BAGS = [
    (5762, "Rote Leinentasche", 6686, 6),
    (5763, "Rote Wolltasche", 6688, 8),
    (5764, "Grünes Seidenpack", 6693, 10),
    (5765, "Schwarzes Seidenpack", 6695, 10),
    (10051, "Rote Magiestofftasche", 12079, 12),
]
# Taschen, die ich herstellen kann, auch wenn das Addon sie noch nicht kennt
# (zusätzlich zu dem, was NaowhForever in "profMakes" gespeichert hat)
CAN_CRAFT = {5762, 5763, 5764, 5765}
# Deutsche Client-Namen der Materialien
NAMES = {
    2996: "Leinenstoffballen", 2997: "Wollstoffballen", 4305: "Seidenstoffballen",
    4339: "Magiestoffballen", 2321: "Feiner Faden", 4291: "Seidenfaden",
    2604: "Roter Farbstoff", 2605: "Grüner Farbstoff", 2325: "Schwarzer Farbstoff",
    4234: "Schweres Leder", 8343: "Schwerer Seidenfaden",
}
# --------------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
ADDONS = WOW / "Interface" / "AddOns"
SV = WOW / "WTF" / "Account" / ACCOUNT / "SavedVariables" / "NaowhForever.lua"


# ---------- Lua-SavedVariables lesen ----------
_TOKEN = re.compile(r'''
    \s+ | --[^\n]* |
    (?P<str>"(?:\\.|[^"\\])*") |
    (?P<num>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?) |
    (?P<name>[A-Za-z_][A-Za-z0-9_]*) |
    (?P<sym>[{}\[\]=,;])
''', re.X | re.S)


def _tokens(text):
    pos, n = 0, len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            raise ValueError(f"Unerwartetes Zeichen bei {pos}: {text[pos:pos+20]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind:
            yield kind, m.group(kind)


def _unescape(s):
    return re.sub(r'\\(.)', lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s[1:-1])


def parse_lua(text):
    toks = list(_tokens(text))
    i = 0

    def value():
        nonlocal i
        kind, v = toks[i]
        i += 1
        if kind == "str":
            return _unescape(v)
        if kind == "num":
            return float(v) if "." in v or "e" in v.lower() else int(v)
        if kind == "name":
            return {"true": True, "false": False, "nil": None}.get(v, v)
        if v == "{":
            out, idx = {}, 1
            while toks[i][1] != "}":
                if toks[i][1] == "[":
                    i += 1
                    k = value()
                    i += 2  # "]" "="
                    out[k] = value()
                elif toks[i][0] == "name" and toks[i + 1][1] == "=":
                    k = toks[i][1]
                    i += 2
                    out[k] = value()
                else:
                    out[idx] = value()
                    idx += 1
                if toks[i][1] in (",", ";"):
                    i += 1
            i += 1
            return out
        raise ValueError(f"Unerwartet: {v}")

    result = {}
    while i < len(toks):
        name = toks[i][1]
        i += 2  # name "="
        result[name] = value()
    return result


# ---------- Daten zusammentragen ----------
def b36(s):
    return int(s, 36)


def decode_feed(s):
    """'id:preis:anzahl,...' in Base 36, jede ID als Abstand zur vorigen."""
    out, item = {}, 0
    for part in s.split(","):
        bits = part.split(":")
        if len(bits) < 2:
            continue
        item += b36(bits[0])
        out[item] = (b36(bits[1]), b36(bits[2]) if len(bits) > 2 else None)
    return out


def load_feed():
    text = (ADDONS / "NaowhForever_AuctionData" / "Prices.lua").read_text(encoding="utf-8")
    t = int(re.search(r"time\s*=\s*(\d+)", text).group(1))
    m = re.search(r"middles\s*=\s*\{\s*\[3\]\s*=\s*\{(.*?)\}", text, re.S)
    fac = re.search(FACTION + r'\s*=\s*"([^"]*)"', m.group(1)) if m else None
    return t, decode_feed(fac.group(1)) if fac else {}


def load_reagents():
    text = (ADDONS / "NaowhForever_Professions" / "Data" / "RecipeReagents.lua").read_text(encoding="utf-8")
    out = {}
    for spell, body in re.findall(r"\[(\d+)\]\s*=\s*\{([^}]*)\}", text):
        nums = [int(x) for x in re.findall(r"\d+", body.split("made")[0])]
        out[int(spell)] = list(zip(nums[0::2], nums[1::2]))
    return out


def load_vendor():
    text = (ADDONS / "NaowhForever_Professions" / "Data" / "VendorPrices.lua").read_text(encoding="utf-8")
    return {int(a): int(b) for a, b in re.findall(r"\[(\d+)\]\s*=\s*(\d+)", text)}


def load_account():
    return parse_lua(SV.read_text(encoding="utf-8"))["NaowhForeverDB"]["account"]


def load_known(db):
    """Items, die irgendeiner deiner Charaktere laut Berufsfenster herstellen kann."""
    known = set(CAN_CRAFT)
    for char in db.get("profMakes", {}).values():
        if isinstance(char, dict):
            known.update(char)
    return known


def load_scans(db):
    scans = {}  # item -> (preis, anzahl, zeit)
    for house, data in db.get("ahPrices", {}).items():
        if not str(house).endswith("-" + FACTION):
            continue
        for item, price in data.get("prices", {}).items():
            seen = data.get("seen", {}).get(item, 0)
            if item not in scans or seen > scans[item][2]:
                scans[item] = (price, data.get("listed", {}).get(item), seen)
    history = {}  # item -> {tag: preis}
    for house, data in db.get("marketHistory", {}).items():
        if not str(house).endswith("-" + FACTION):
            continue
        for day, s in data.get("days", {}).items():
            if not isinstance(s, str):
                continue
            for part in s.split(","):
                bits = part.split(":")
                if len(bits) >= 2 and bits[0].isdigit():
                    history.setdefault(int(bits[0]), {})[int(day)] = int(bits[1])
    return scans, history


def ah_price(item, scans, feed_time, feed):
    """Neuester bekannter AH-Preis: eigener Scan oder, falls neuer, Blizzard-Daten im Addon."""
    own = scans.get(item)
    if own and (own[2] >= feed_time or item not in feed):
        return {"price": own[0], "listed": own[1], "time": own[2], "src": "Eigener Scan"}
    if item in feed:
        p, n = feed[item]
        return {"price": p, "listed": n, "time": feed_time, "src": "Addon-Daten (Mittel aller AHs)"}
    return None


# ---------- HTML ----------
def money(c):
    if c is None:
        return "–"
    neg, c = c < 0, abs(int(round(c)))
    g, s, k = c // 10000, c // 100 % 100, c % 100
    parts = ([f"{g}g"] if g else []) + ([f"{s}s"] if g or s else []) + [f"{k}k"]
    return ("−" if neg else "") + " ".join(parts)


def when(t):
    return datetime.fromtimestamp(t).strftime("%d.%m. %H:%M") if t else "–"


def wh(item, name):
    return f'<a href="https://www.wowhead.com/classic/de/item={item}" target="_blank" rel="noopener">{html.escape(name)}</a>'


def build():
    db = load_account()
    reagents, vendor = load_reagents(), load_vendor()
    vendor.update(db.get("profVendorPrices", {}))  # im Spiel gesehene Händlerpreise
    known = load_known(db)
    scans, history = load_scans(db)
    feed_time, feed = load_feed()
    now = datetime.now()
    rows, sections, newest = [], [], 0

    for item, name, spell, slots in BAGS:
        ah = ah_price(item, scans, feed_time, feed)
        mats, total, complete = [], 0, True
        for mat, qty in reagents.get(spell, []):
            a = ah_price(mat, scans, feed_time, feed)
            v = vendor.get(mat)
            if v is not None and (a is None or v <= a["price"]):
                unit, src = v, "Händler"
            elif a:
                label = "AH" if a["src"] == "Eigener Scan" else "AH-Mittel (Addon)"
                unit, src = a["price"], f'{label} · {when(a["time"])}'
                newest = max(newest, a["time"])
            else:
                unit, src, complete = None, "unbekannt", False
            if unit is not None:
                total += unit * qty
            mats.append((mat, qty, unit, src))
        cost = total if complete else None
        profit = ah["price"] * (1 - AH_CUT) - cost if ah and cost is not None else None
        if ah:
            newest = max(newest, ah["time"])

        hist = sorted(history.get(item, {}).items())[-7:]
        trend = " · ".join(f'{datetime.fromtimestamp(d * 86400):%d.%m.} {money(p)}' for d, p in hist)

        cls = "up" if profit and profit > 0 else "dn"
        tick = ' <span class="ok" title="kann ich herstellen">✔</span>' if item in known else ""
        rows.append(f"""<tr><th class="cl">{wh(item, name)}{tick}</th><td>{slots}</td>
<td><b>{money(ah and ah['price'])}</b></td><td>{ah and ah['listed'] or '–'}</td>
<td>{money(cost)}</td><td class="{cls}"><b>{money(profit)}</b></td><td>{when(ah and ah['time'])}</td></tr>""")

        mrows = "".join(
            f"<tr><th class=\"cl\">{wh(m, NAMES.get(m, f'Item {m}'))}</th><td>{q}×</td><td>{money(u)}</td>"
            f"<td><b>{money(u * q if u is not None else None)}</b></td><td>{src}</td></tr>"
            for m, q, u, src in mats)
        sections.append(f"""
<section class="bag">
  <h2>{wh(item, name)}{tick}</h2>
  <div class="h2s"><b>{slots} Plätze</b> · AH: <b>{money(ah and ah['price'])}</b> · {ah and ah['listed'] or '–'} Angebote · {ah['src'] if ah else 'kein Preis'}, {when(ah and ah['time'])}</div>
  <div class="scroll"><table class="mx">
    <thead><tr><th class="cl">Material</th><th>Menge</th><th>Stückpreis</th><th>Summe</th><th>Quelle</th></tr></thead>
    <tbody>{mrows}
      <tr class="sum"><th class="cl">Materialkosten</th><td></td><td></td><td><b>{money(cost)}</b></td><td></td></tr>
      <tr class="sum"><th class="cl">Gewinn nach {int(AH_CUT*100)} % AH-Gebühr</th><td></td><td></td><td class="{cls}"><b>{money(profit)}</b></td><td></td></tr>
    </tbody>
  </table></div>
  {f'<p class="note"><b>Verlauf:</b> {trend}</p>' if trend else ''}
</section>""")

    page = f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AH-Übersicht Taschen · WoW: Forever</title>
<link rel="stylesheet" href="assets/ci.css">
<style>
  html,body{{background:var(--papier)}}
  body{{font-size:11pt;padding:4mm}}
  .page{{width:auto;max-width:210mm;height:auto;margin:0 auto;padding:9mm 9mm 4mm;overflow:visible}}
  .frame{{inset:0}}
  .in{{padding:4mm 6mm 2mm}}
  .mx{{font-size:10.5pt}}
  .mx td,.mx tbody th{{padding:1.4mm 1.2mm}}
  .mx th.cl{{font-size:10.5pt;white-space:normal}}
  .mx .sum th,.mx .sum td{{background:var(--band)}}
  .ok{{color:var(--pve);font-weight:700;border:0}}
  td.up{{color:var(--pve)}} td.dn{{color:var(--horde)}}
  a{{color:inherit;text-decoration:none;border-bottom:.6px dotted var(--gold)}}
  .scroll{{overflow-x:auto}}
  .h2s{{font-size:10pt}}
  .note{{font-size:9.5pt;text-align:center}}
  .bag{{margin-top:5mm}}
  footer{{position:static;margin-top:6mm;padding-bottom:2mm}}
  footer .st{{position:static;display:block;margin-top:1mm}}
  @media (max-width:600px){{ .fac img{{height:9mm}} .logo{{height:15mm}} .page{{padding:5mm}} .in{{padding:3mm 2mm}}
    body{{padding:1mm}} .mx{{font-size:9pt}} .mx thead th{{font-size:9pt}} .mx th.cl{{font-size:9pt}} .mx td{{white-space:nowrap}} }}
</style></head>
<body><div class="page"><div class="frame"></div><div class="in">
  <header class="top">
    <div class="fac h"><img src="assets/img/logos/horde.png" alt=""><span>HORDE</span></div>
    <img class="logo" src="assets/img/logos/wow-forever.png" alt="WoW Forever">
    <div class="fac a"><img src="assets/img/logos/allianz.png" alt=""><span>ALLIANZ</span></div>
  </header>
  <div class="ttl">AH-Übersicht Taschen</div>
  <div class="sub">Schneiderei · Auktionshaus {'Allianz' if FACTION == 'Alliance' else FACTION} · neuester Scan {when(newest)}</div>
  <div class="rule">◆</div>

  <h2 class="first">Übersicht</h2>
  <div class="h2s">Niedrigster Sofortkaufpreis aus dem NaowhForever-Scan · Gewinn = AH-Preis − {int(AH_CUT*100)} % Gebühr − Materialkosten</div>
  <div class="scroll"><table class="mx">
    <thead><tr><th class="cl">Tasche</th><th>Plätze</th><th>AH-Preis</th><th>Angebote</th><th>Material</th><th>Gewinn</th><th>Scan</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>
  <p class="note"><b>Hinweis:</b> <span class="ok">✔</span> = kann ich herstellen. Materialien zählen zum günstigeren Preis von Händler und AH. Die Einstellgebühr ist nicht eingerechnet. Preise ändern sich nur, wenn jemand im Spiel das AH scannt.</p>
  {''.join(sections)}
</div>
<footer>AH-ÜBERSICHT · WOW: FOREVER<span class="st">Stand: {now:%d.%m.%Y %H:%M} · Daten: NaowhForever-Scan vom {when(newest)}</span></footer>
</div></body></html>
"""
    out = HERE / "docs" / "index.html"
    out.write_text(page, encoding="utf-8")
    (HERE / "docs" / ".nojekyll").touch()
    print(f"Geschrieben: {out} (neuester Scan {when(newest)})")


def push():
    def git(*args):
        return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True)
    git("add", "docs")
    if git("diff", "--cached", "--quiet").returncode == 0:
        print("Keine Änderung, nichts zu pushen.")
        return
    git("commit", "-m", f"Preise aktualisiert {datetime.now():%d.%m.%Y %H:%M}")
    r = git("push")
    print("Gepusht." if r.returncode == 0 else f"Push fehlgeschlagen:\n{r.stderr}")
    if r.returncode:
        sys.exit(1)


if __name__ == "__main__":
    build()
    if "--push" in sys.argv:
        push()
