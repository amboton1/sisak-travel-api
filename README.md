# 🚌 Sisak Bus Schedule API

A lightweight REST API that provides real-time bus schedule data for city buses in **Sisak, Croatia**. It scrapes the official e-karta.si timetable, parses it, and exposes it through clean, easy-to-use JSON endpoints.

Built with **Python** and **FastAPI**, and designed to be consumed by mobile or web apps (originally built to support a Flutter app).

---

## 📖 What Does It Do?

- Automatically fetches the bus schedule from the official source on startup
- Refreshes the data every 24 hours in the background
- Lets you query departures by day (weekday, Saturday, Sunday)
- Has a smart `/next` endpoint that figures out today's day and returns upcoming buses in real time

---

## 🗂️ Project Structure

```
sisak-travel-api/
├── main.py           # All the app logic — scraper, parser, and API endpoints
├── requirements.txt  # Python dependencies
├── Procfile          # How to start the app (used by Railway / Heroku)
└── railway.toml      # Deployment config for Railway
```

---

## 🚀 Running the Project Locally

### Prerequisites

Make sure you have the following installed:

- **Python 3.11+** — [Download here](https://www.python.org/downloads/)
- **pip** — comes bundled with Python

### Step 1 — Clone the repository

```bash
git clone https://github.com/amboton1/sisak-travel-api.git
cd sisak-travel-api
```

### Step 2 — Create a virtual environment (recommended)

A virtual environment keeps your project dependencies isolated from the rest of your system.

```bash
# Create the virtual environment
python -m venv venv

# Activate it:
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

You should see `(venv)` appear in your terminal — that means it's active.

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs FastAPI, Uvicorn (the web server), and the scraping libraries.

### Step 4 — Run the server

```bash
uvicorn main:app --reload
```

- `--reload` means the server will automatically restart when you edit `main.py` — great for development.
- The server starts at **http://127.0.0.1:8000**

> ℹ️ On first startup, the app will scrape the bus schedule automatically. This may take a few seconds.

---

## 📡 API Endpoints

Once the server is running, you can open these URLs in your browser or use a tool like [Postman](https://www.postman.com/) or `curl`.

### `GET /`

Health check. Shows whether the API is up and when data was last scraped.

**Example response:**
```json
{
  "status": "ok",
  "scraped_at": "2025-04-11T10:00:00+00:00",
  "days_available": ["radni_dan", "subota", "nedjelja"]
}
```

---

### `GET /schedule`

Returns the **full schedule** for all days and all routes.

```bash
curl http://127.0.0.1:8000/schedule
```

---

### `GET /schedule/{day}`

Returns the schedule for a specific day. Replace `{day}` with one of:

| Value | Meaning |
|---|---|
| `radni_dan` | Weekday (Monday–Friday) |
| `subota` | Saturday |
| `nedjelja` | Sunday / Public holiday |

**Example:**
```bash
curl http://127.0.0.1:8000/schedule/radni_dan
```

---

### `GET /next`

Returns the **next upcoming departures** based on the current time in Croatia (Zagreb timezone). Automatically detects whether it's a weekday, Saturday, or Sunday.

**Optional query parameters:**

| Parameter | Description | Example |
|---|---|---|
| `from` | Filter by departure section | `polazak_s_kolodvora` |
| `limit` | How many upcoming buses to return (1–20, default 5) | `limit=3` |

**Available section values:**
- `polazak_s_kolodvora` — departures from the bus station
- `polazak_iz_zeljezare` — departures from Željezara
- `kruzna_linija_5` — circular line 5
- `kruzna_linija_6` — circular line 6

**Example:**
```bash
curl "http://127.0.0.1:8000/next?from=polazak_s_kolodvora&limit=3"
```

**Example response:**
```json
{
  "day": "radni_dan",
  "current_time": "14:32",
  "from_section": "polazak_s_kolodvora",
  "next_departures": {
    "polazak_s_kolodvora": [
      { "time": "14:45", "line": "1", "route_info": "" },
      { "time": "15:10", "line": "2A", "route_info": "" },
      { "time": "15:30", "line": "1", "route_info": "" }
    ]
  }
}
```

---

## 📚 Interactive Docs

FastAPI automatically generates interactive documentation. Once your server is running, visit:

- **Swagger UI:** http://127.0.0.1:8000/docs — Try out all endpoints directly in your browser
- **ReDoc:** http://127.0.0.1:8000/redoc — A clean, readable version of the docs

---

## 🧠 How It Works (Behind the Scenes)

1. **On startup**, the app fetches the bus schedule HTML from `e-karta.si`.
2. **BeautifulSoup** parses the HTML tables and extracts departure times, line numbers, and route sections.
3. The parsed data is stored **in memory** (no database needed).
4. A **background task** re-scrapes the data every 24 hours to stay up to date.
5. The `/next` endpoint uses Croatia's timezone (`Europe/Zagreb`) to compare the current time against the schedule.

---

## ☁️ Deployment

This project is set up for **Railway** (a simple cloud hosting platform).

The `Procfile` tells the platform how to start the server:
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

To deploy:
1. Create a free account at [railway.app](https://railway.app)
2. Connect your GitHub repo
3. Railway will detect the `Procfile` and deploy automatically

---

## 🛠️ Tech Stack

| Tool | Purpose |
|---|---|
| [FastAPI](https://fastapi.tiangolo.com/) | Web framework for building the API |
| [Uvicorn](https://www.uvicorn.org/) | ASGI web server to run FastAPI |
| [httpx](https://www.python-httpx.org/) | Async HTTP client for scraping |
| [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) | HTML parser |
| [lxml](https://lxml.de/) | Fast XML/HTML processing backend |

---

## ❓ Troubleshooting

**The server starts but `/schedule` returns a 503 error**
> The scrape is still in progress. Wait a few seconds and try again.

**`ModuleNotFoundError` when running the server**
> Make sure your virtual environment is activated and you ran `pip install -r requirements.txt`.

**Data looks outdated**
> The app refreshes every 24 hours automatically. You can restart the server to trigger an immediate re-scrape.
