from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone, time
import asyncio
import httpx
import re
import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sisak-bus")

IFRAME_URL = "https://www.e-karta.si/bus4i_vr/aps/p_vr?p_ozn=1"
REFRESH_INTERVAL_HOURS = 24

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "hr,en;q=0.5",
}

# ─── In-memory cache ───────────────────────────────────────────
cache: dict = {
    "schedule": {},
    "legend": [],
    "scraped_at": None,
}

# ─── Scraper (isti kao v5, async verzija) ──────────────────────

TIME_PREFIX_RE = re.compile(r'^([0-1]?\d|2[0-3]):[0-5]\d')

def extract_time(s: str) -> str | None:
    m = TIME_PREFIX_RE.match(s.strip())
    return m.group(0) if m else None

def extract_route_info(s: str) -> str:
    s = s.strip()
    m = TIME_PREFIX_RE.match(s)
    return s[m.end():].strip() if m else ""

def clean(s: str) -> str:
    return " ".join(s.split()).strip()

def normalize_section(s: str) -> str:
    sl = s.lower()
    if "kolodvor" in sl: return "polazak_s_kolodvora"
    if "željezar" in sl or "zeljezar" in sl: return "polazak_iz_zeljezare"
    if "5" in sl: return "kruzna_linija_5"
    if "6" in sl: return "kruzna_linija_6"
    return re.sub(r'[^a-z0-9_]', '_', sl).strip('_')[:40]

DAY_KEYWORDS = {
    "radni_dan": ["radnim danom", "radni dan"],
    "subota":    ["subotom", "subota"],
    "nedjelja":  ["nedjeljom", "nedjelja", "blagdan"],
}

def find_day_tables(tables):
    found = {}
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) < 5:
            continue
        header_text = " ".join(clean(r.get_text()).lower() for r in rows[:5])
        for day, keywords in DAY_KEYWORDS.items():
            if day not in found and any(kw in header_text for kw in keywords):
                found[day] = t
                break
    return found

def parse_table(table) -> dict:
    rows = table.find_all("tr")
    section_row_idx = subheader_row_idx = None

    for i, row in enumerate(rows):
        text = clean(row.get_text()).lower()
        if section_row_idx is None and ("polazak" in text or "kružna" in text or "kruzna" in text):
            section_row_idx = i
        elif section_row_idx is not None and "vrijemepolaska" in text.replace(" ", ""):
            subheader_row_idx = i
            break

    if section_row_idx is None or subheader_row_idx is None:
        return {}

    section_cells = rows[section_row_idx].find_all(["td", "th"])
    sections, col = [], 0
    for cell in section_cells:
        text = clean(cell.get_text())
        span = int(cell.get("colspan", 1))
        if text:
            sections.append((normalize_section(text), col))
        col += span
    total_cols = col

    subheader_cells = rows[subheader_row_idx].find_all(["td", "th"])
    time_col_indices = []
    for i, cell in enumerate(subheader_cells):
        text = clean(cell.get_text()).lower().replace(" ", "")
        if "vrijemepolaska" in text or "vrijemep" in text:
            time_col_indices.append(i)

    def col_to_section(col_idx):
        for j, (name, start) in enumerate(sections):
            next_start = sections[j+1][1] if j+1 < len(sections) else total_cols
            if start <= col_idx < next_start:
                return name
        return None

    result = {name: [] for name, _ in sections}

    for row in rows[subheader_row_idx + 1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        for t_col in time_col_indices:
            if t_col >= len(cells):
                continue
            raw = clean(cells[t_col].get_text())
            time_val = extract_time(raw)
            if not time_val:
                continue
            line_val = clean(cells[t_col + 1].get_text()) if t_col + 1 < len(cells) else ""
            section = col_to_section(t_col)
            if section and section in result:
                result[section].append({
                    "time": time_val,
                    "line": line_val,
                    "route_info": extract_route_info(raw),
                })

    for deps in result.values():
        deps.sort(key=lambda x: x["time"])
    return result

def extract_legend(tables):
    for t in tables:
        if "LEGENDA" not in t.get_text():
            continue
        entries = re.findall(r'(\d+[A-Za-z]?\s*\([^)]+\))\s+([A-ZČĆŠŽĐ][^\n]+)', t.get_text())
        legend = [{"code": clean(c), "description": clean(d)} for c, d in entries]
        if legend:
            return legend
    return []

async def scrape() -> bool:
    """Dohvati i parsiraj raspored. Vraća True ako je uspjelo."""
    try:
        log.info("Scraping started...")
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(IFRAME_URL, headers=HEADERS)
            r.raise_for_status()

        soup = BeautifulSoup(r.text, "lxml")
        tables = soup.find_all("table")
        day_tables = find_day_tables(tables)

        schedule = {}
        for day, table in day_tables.items():
            schedule[day] = parse_table(table)

        cache["schedule"] = schedule
        cache["legend"] = extract_legend(tables)
        cache["scraped_at"] = datetime.now(timezone.utc).isoformat()

        total = sum(len(d) for day in schedule.values() for d in day.values())
        log.info(f"Scrape OK — {total} departures across {len(schedule)} days")
        return True

    except Exception as e:
        log.error(f"Scrape failed: {e}")
        return False

async def refresh_loop():
    """Background task: re-scrape svakih REFRESH_INTERVAL_HOURS sati."""
    while True:
        await asyncio.sleep(REFRESH_INTERVAL_HOURS * 3600)
        await scrape()

# ─── App lifecycle ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await scrape()                          # Inicijalni scrape pri startu
    task = asyncio.create_task(refresh_loop())
    yield
    task.cancel()

app = FastAPI(
    title="Sisak Bus Schedule API",
    description="Vozni redovi gradskih autobusa u Sisku",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Flutter app može zvati s bilo koje adrese
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ─── Endpoints ─────────────────────────────────────────────────

@app.get("/")
async def health():
    return {
        "status": "ok",
        "scraped_at": cache["scraped_at"],
        "days_available": list(cache["schedule"].keys()),
    }

@app.get("/schedule")
async def get_schedule():
    if not cache["schedule"]:
        raise HTTPException(503, "Podaci još nisu učitani, pokušaj za trenutak.")
    return {
        "scraped_at": cache["scraped_at"],
        "legend": cache["legend"],
        "schedule": cache["schedule"],
    }

@app.get("/schedule/{day}")
async def get_day(day: str):
    valid = list(cache["schedule"].keys())
    if day not in cache["schedule"]:
        raise HTTPException(404, f"Dan '{day}' nije pronađen. Dostupno: {valid}")
    return {
        "day": day,
        "scraped_at": cache["scraped_at"],
        "sections": cache["schedule"][day],
    }

@app.get("/next")
async def get_next(
    from_section: str = Query(
        default=None,
        alias="from",
        description="polazak_s_kolodvora | polazak_iz_zeljezare | kruzna_linija_5 | kruzna_linija_6"
    ),
    limit: int = Query(default=5, ge=1, le=20),
):
    """
    Vraća sljedećih N polazaka od trenutnog vremena.
    Automatski određuje dan u tjednu (radni/sub/ned).
    """
    if not cache["schedule"]:
        raise HTTPException(503, "Podaci još nisu učitani.")

    # Odredi koji dan koristiti (Croatia = UTC+1/UTC+2)
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Europe/Zagreb"))
    weekday = now.weekday()  # 0=pon, 5=sub, 6=ned
    current_time = now.strftime("%H:%M")

    if weekday == 6:
        day_key = "nedjelja"
    elif weekday == 5:
        day_key = "subota"
    else:
        day_key = "radni_dan"

    # Fallback ako traženi dan nije scrapan
    schedule_day = cache["schedule"].get(day_key, {})

    results = {}
    sections_to_check = (
        [from_section] if from_section and from_section in schedule_day
        else list(schedule_day.keys())
    )

    for section in sections_to_check:
        upcoming = [
            d for d in schedule_day.get(section, [])
            if d["time"] >= current_time
        ]
        results[section] = upcoming[:limit]

    return {
        "day": day_key,
        "current_time": current_time,
        "from_section": from_section,
        "next_departures": results,
    }
