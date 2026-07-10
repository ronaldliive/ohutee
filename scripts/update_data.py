from __future__ import annotations
import csv, io, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pyproj import Transformer

DATASET_PAGE = "https://andmed.eesti.ee/datasets/inimkannatanutega-liiklusonnetuste-andmed"
OUT = Path(__file__).resolve().parents[1] / "data"
HEADERS = {"User-Agent": "Ohutee-open-data-sync/1.0 (+https://github.com/ronaldliive/ohutee)"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("õ", "o"))


def discover_csv() -> str:
    r = requests.get(DATASET_PAGE, headers=HEADERS, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    candidates = []
    for tag in soup.find_all(["a", "link"]):
        href = tag.get("href")
        if href:
            u = urljoin(DATASET_PAGE, href)
            txt = (tag.get_text(" ", strip=True) + " " + u).lower()
            if ".csv" in txt or "2011" in txt and "2026" in txt:
                candidates.append(u)
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        for m in re.findall(r'https?[^"\'<>\\\s]+', text):
            u = m.replace("\\u002F", "/").replace("\\/", "/")
            if ".csv" in u.lower():
                candidates.append(u)
    # Eelista koondfaili, mitte metaandmeid.
    candidates = list(dict.fromkeys(candidates))
    candidates.sort(key=lambda u: ("2011" not in u, "2026" not in u, len(u)))
    for u in candidates:
        try:
            h = requests.get(u, headers=HEADERS, timeout=45, allow_redirects=True)
            ct = h.headers.get("content-type", "").lower()
            if h.ok and ("csv" in ct or ";" in h.text[:1000] or "," in h.text[:1000]):
                return h.url
        except requests.RequestException:
            pass
    raise RuntimeError("Ametliku CSV allalaadimislinki ei õnnestunud andmestiku lehelt tuvastada.")


def find_key(row, aliases):
    keys = {norm(k): k for k in row.keys() if k}
    for alias in aliases:
        a = norm(alias)
        for nk, original in keys.items():
            if a == nk or a in nk:
                return original
    return None


def number(v):
    if v is None: return None
    s = str(v).strip().replace(" ", "").replace(",", ".")
    try: return float(s)
    except ValueError: return None


def parse_coords(row):
    latk = find_key(row, ["latitude", "lat", "laiuskraad", "wgs84 y"])
    lonk = find_key(row, ["longitude", "lon", "lng", "pikkuskraad", "wgs84 x"])
    lat, lon = number(row.get(latk)) if latk else None, number(row.get(lonk)) if lonk else None
    if lat and lon and 57 < lat < 60 and 21 < lon < 29:
        return lat, lon
    xk = find_key(row, ["x koordinaat", "xkoord", "l est x", "koordinaat x"])
    yk = find_key(row, ["y koordinaat", "ykoord", "l est y", "koordinaat y"])
    x, y = number(row.get(xk)) if xk else None, number(row.get(yk)) if yk else None
    if x and y:
        # EPSG:3301 L-EST97 tavapärased vahemikud.
        if 300000 < x < 800000 and 6300000 < y < 6700000:
            lon, lat = Transformer.from_crs(3301, 4326, always_xy=True).transform(x, y)
            return lat, lon
        if 300000 < y < 800000 and 6300000 < x < 6700000:
            lon, lat = Transformer.from_crs(3301, 4326, always_xy=True).transform(y, x)
            return lat, lon
    return None


def main():
    csv_url = discover_csv()
    r = requests.get(csv_url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    raw = r.content
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1257", "latin-1"):
        try:
            text = raw.decode(enc); break
        except UnicodeDecodeError: pass
    if text is None: raise RuntimeError("CSV kodeeringut ei õnnestunud tuvastada")
    sample = text[:10000]
    try: dialect = csv.Sniffer().sniff(sample, delimiters=";,\t,")
    except csv.Error: dialect = csv.excel; dialect.delimiter = ";"
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    out, skipped = [], 0
    for row in reader:
        coords = parse_coords(row)
        if not coords:
            skipped += 1; continue
        joined = " ".join(str(v or "") for v in row.values()).lower()
        datek = find_key(row, ["toimumisaeg", "kuupaev", "kuupäev", "aeg", "date"])
        date = str(row.get(datek) or "")
        ym = re.search(r"(20\d{2})", date)
        hm = re.search(r"(?:\s|T)([01]?\d|2[0-3])[:.]", date)
        idk = find_key(row, ["juhtumi id", "id", "õnnetuse number", "onnetuse number"])
        victimk = find_key(row, ["kannatanute arv", "vigastatute arv", "kannatanuid"])
        fatalk = find_key(row, ["hukkunute arv", "hukkunuid"])
        fatalities = int(number(row.get(fatalk)) or (1 if "hukk" in joined else 0))
        if "jalakä" in joined: kind = "jalakäija"
        elif "jalgr" in joined or "kergliik" in joined: kind = "jalgrattur"
        elif "mootorr" in joined or "mopeed" in joined: kind = "mootorratas"
        else: kind = "auto"
        out.append({
            "id": str(row.get(idk) or len(out)+1),
            "lat": round(coords[0], 6), "lng": round(coords[1], 6),
            "year": int(ym.group(1)) if ym else None,
            "hour": int(hm.group(1)) if hm else None,
            "type": kind,
            "severity": "hukkunu" if fatalities else "vigastus",
            "victims": max(1, int(number(row.get(victimk)) or 1)),
            "fatalities": fatalities,
        })
    if len(out) < 1000:
        raise RuntimeError(f"Tuvastati ainult {len(out)} koordinaatidega kirjet; automaatne avaldamine katkestati.")
    updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUT.mkdir(exist_ok=True)
    (OUT / "accidents.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    status = {"generated_at": updated, "source_url": csv_url, "dataset_page": DATASET_PAGE, "records": len(out), "skipped_without_coordinates": skipped, "latest_year": max((x["year"] or 0) for x in out)}
    (OUT / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"VIGA: {e}", file=sys.stderr); raise
