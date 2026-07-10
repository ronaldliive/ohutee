from __future__ import annotations
import csv, io, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from playwright.sync_api import sync_playwright
from pyproj import Transformer

DATASET_PAGE = "https://andmed.eesti.ee/datasets/inimkannatanutega-liiklusonnetuste-andmed"
OUT = Path(__file__).resolve().parents[1] / "data"
HEADERS = {"User-Agent": "Ohutee-open-data-sync/1.1 (+https://github.com/ronaldliive/ohutee)"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("õ", "o"))


def looks_like_csv_response(r: requests.Response) -> bool:
    ct = r.headers.get("content-type", "").lower()
    sample = r.content[:2000]
    return r.ok and (
        "csv" in ct
        or r.url.lower().split("?")[0].endswith(".csv")
        or sample.count(b";") >= 3
        or sample.count(b",") >= 3
    )


def discover_csv() -> str:
    candidates: list[str] = []
    captured: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])

        def capture_response(response):
            url = response.url
            low = url.lower()
            ct = (response.headers.get("content-type") or "").lower()
            if ".csv" in low or "text/csv" in ct or "application/csv" in ct:
                captured.append(url)

        page.on("response", capture_response)
        page.goto(DATASET_PAGE, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(3000)

        # Kõik renderdatud lingid, eelistades koondfaili 2011–2026.
        for link in page.locator("a").all():
            try:
                href = link.get_attribute("href")
                text = link.inner_text(timeout=1000).strip()
            except Exception:
                continue
            if not href:
                continue
            url = urljoin(DATASET_PAGE, href)
            hay = f"{text} {url}".lower()
            if ".csv" in hay or ("2011" in hay and "2026" in hay):
                candidates.append(url)

        # Kui link on nupu või tabelirea taga, klõpsa tekstil ja püüa allalaadimine/URL kinni.
        locator = page.get_by_text(re.compile(r"2011\s*[-–]\s*2026", re.I))
        if locator.count():
            target = locator.first
            try:
                href = target.get_attribute("href")
                if href:
                    candidates.append(urljoin(DATASET_PAGE, href))
            except Exception:
                pass
            try:
                with page.expect_download(timeout=15000) as info:
                    target.click()
                download = info.value
                if download.url:
                    candidates.append(download.url)
            except Exception:
                try:
                    target.click(timeout=5000)
                    page.wait_for_timeout(3000)
                except Exception:
                    pass

        candidates.extend(captured)
        browser.close()

    candidates = list(dict.fromkeys(candidates))
    candidates.sort(key=lambda u: ("2011" not in u, "2026" not in u, ".csv" not in u.lower(), len(u)))

    errors = []
    for url in candidates:
        try:
            r = requests.get(url, headers=HEADERS, timeout=120, allow_redirects=True)
            if looks_like_csv_response(r):
                return r.url
            errors.append(f"{url} -> HTTP {r.status_code}, {r.headers.get('content-type', '')}")
        except requests.RequestException as exc:
            errors.append(f"{url} -> {exc}")

    detail = "\n".join(errors[:10]) if errors else "Renderdatud lehelt ei leitud ühtegi kandidaati."
    raise RuntimeError(f"Ametliku CSV allalaadimislinki ei õnnestunud tuvastada.\n{detail}")


def find_key(row, aliases):
    keys = {norm(k): k for k in row.keys() if k}
    for alias in aliases:
        a = norm(alias)
        for nk, original in keys.items():
            if a == nk or a in nk:
                return original
    return None


def number(v):
    if v is None:
        return None
    s = str(v).strip().replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_coords(row):
    latk = find_key(row, ["latitude", "lat", "laiuskraad", "wgs84 y"])
    lonk = find_key(row, ["longitude", "lon", "lng", "pikkuskraad", "wgs84 x"])
    lat = number(row.get(latk)) if latk else None
    lon = number(row.get(lonk)) if lonk else None
    if lat and lon and 57 < lat < 60 and 21 < lon < 29:
        return lat, lon

    xk = find_key(row, ["x koordinaat", "xkoord", "l est x", "koordinaat x", "x_coord"])
    yk = find_key(row, ["y koordinaat", "ykoord", "l est y", "koordinaat y", "y_coord"])
    x = number(row.get(xk)) if xk else None
    y = number(row.get(yk)) if yk else None
    if x and y:
        if 300000 < x < 800000 and 6300000 < y < 6700000:
            lon, lat = Transformer.from_crs(3301, 4326, always_xy=True).transform(x, y)
            return lat, lon
        if 300000 < y < 800000 and 6300000 < x < 6700000:
            lon, lat = Transformer.from_crs(3301, 4326, always_xy=True).transform(y, x)
            return lat, lon
    return None


def main():
    csv_url = discover_csv()
    print(f"Leitud ametlik CSV: {csv_url}")
    r = requests.get(csv_url, headers=HEADERS, timeout=180)
    r.raise_for_status()
    raw = r.content

    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1257", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    if text is None:
        raise RuntimeError("CSV kodeeringut ei õnnestunud tuvastada")

    try:
        dialect = csv.Sniffer().sniff(text[:15000], delimiters=";,\t,")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    out, skipped = [], 0
    for row in reader:
        coords = parse_coords(row)
        if not coords:
            skipped += 1
            continue
        joined = " ".join(str(v or "") for v in row.values()).lower()
        datek = find_key(row, ["toimumisaeg", "kuupaev", "kuupäev", "aeg", "date"])
        date = str(row.get(datek) or "")
        ym = re.search(r"(20\d{2})", date)
        hm = re.search(r"(?:\s|T)([01]?\d|2[0-3])[:.]", date)
        idk = find_key(row, ["juhtumi id", "id", "õnnetuse number", "onnetuse number"])
        victimk = find_key(row, ["kannatanute arv", "vigastatute arv", "kannatanuid"])
        fatalk = find_key(row, ["hukkunute arv", "hukkunuid"])
        fatalities = int(number(row.get(fatalk)) or (1 if "hukk" in joined else 0))
        if "jalakä" in joined:
            kind = "jalakäija"
        elif "jalgr" in joined or "kergliik" in joined:
            kind = "jalgrattur"
        elif "mootorr" in joined or "mopeed" in joined:
            kind = "mootorratas"
        else:
            kind = "auto"
        out.append({
            "id": str(row.get(idk) or len(out) + 1),
            "lat": round(coords[0], 6),
            "lng": round(coords[1], 6),
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
    status = {
        "generated_at": updated,
        "source_url": csv_url,
        "dataset_page": DATASET_PAGE,
        "records": len(out),
        "skipped_without_coordinates": skipped,
        "latest_year": max((x["year"] or 0) for x in out),
    }
    (OUT / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"VIGA: {exc}", file=sys.stderr)
        raise
