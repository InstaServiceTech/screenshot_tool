# InstaService Screenshot Tool (no emulator)

Generates the mobile **"Service Information"** screen as PNG screenshots from an
Excel sheet — organized into `screenshots/<City>/<ServiceName>.png` and zipped
for download. It replaces the old Appium + Android emulator flow: there is **no
emulator, no Appium, no device** — the screen is drawn directly with Pillow, so
it runs anywhere Python runs.

## What it does

1. **Upload Excel** (same pattern as `serviceDetails.xlsx`) → preview the rows →
   click **Generate Screenshots** → each row is rendered and saved as
   `screenshots/<City>/<ServiceName>.png` → download everything as a ZIP.
2. **Manual entry** → fill one form → get a single screenshot (also downloadable).

File naming matches the original tool exactly: the name is the part of
`ServiceName` **before `*`** (e.g. `General Handyman Service * 3 hours job` →
`General Handyman Service.png`).

## Run it

```bash
# macOS / Linux
./run.sh
# Windows
run.bat
```

Then open <http://127.0.0.1:5000>.

On macOS, port 5000 is often taken by AirPlay Receiver. Disable it in
**System Settings → General → AirPlay & Continuity**, or map Docker to another
host port (see below).

### Docker

```bash
docker compose up --build
```

Then open <http://127.0.0.1:5000>. If that port is busy:

```bash
HOST_PORT=8000 docker compose up --build
```

and open <http://127.0.0.1:8000>.

Without Compose:

```bash
docker build -t screenshot-tool .
docker run --rm -p 8000:5000 screenshot-tool
```

Manual setup instead of the scripts:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd app && python app.py
```

## Excel format

Required columns:

`ServiceAmount, ServiceName, EstimatedTime, City, Zipcode, CustomerName, CustomerInstructions`

Optional columns (used if present):

`Category` (set to `Cleaning` to show the AddOn Q&A block),
`BookingDateTime` (the date shown on the card; defaults to a sample date),
`AddOn1..AddOn4`, `AddOn1Value..AddOn4Value`.

An example sheet is in `samples/serviceDetails_example.xlsx`.

## Service Includes checklist

The green-tick **"Service Includes"** list is app content (not Excel data), so it
lives in **`app/service_includes.json`**, keyed by service name. The wording is
taken verbatim from the app's own `includesExcludesData`, and currently covers
these services:

Interior Paint Touch-Ups · General Handyman Service · Furniture Assembly ·
TV Mounting Service · Leak Repairs · Water Filter Installation · Bathtub clogging ·
Complete Shower System Replacement · Sink Clogging · Toilet Repair Service ·
General Plumbing Service(s) · Faucet replacement · Water Filter Replacement.

Matching is **case-insensitive** and ignores any `* …` suffix on the Excel
`ServiceName` (so `bathtub clogging * 1 hour job` → the "Bathtub clogging" list).

**To add a new service:** open `app/service_includes.json` and add an entry, e.g.

```json
"Chimney Sweep": [
  "Inspection of flue and firebox",
  "Removal of soot and creosote",
  "Basic cleanup of the work area"
]
```

Then any Excel row whose `ServiceName` is "Chimney Sweep" (any case, with or
without a `* …` suffix) shows that checklist. A service with no entry falls back
to `_default`. Cleaning services show their AddOn Q&A block instead of a checklist.

## Project layout

```
app/
  app.py               Flask routes (upload / preview / generate / manual / download)
  renderer.py          Pillow renderer — draws the Service Information screen
  data.py              Excel parsing + ServiceRecord mapping
  service_includes.json  editable Service Includes per service
  templates/           UI (upload + manual tabs, preview, results)
  runs/                per-run output (screenshots + zip); safe to delete
requirements.txt
run.sh / run.bat
Dockerfile / docker-compose.yml
samples/               example Excel + example renders
```

## Notes

- Output height is dynamic so nothing is cut off (unlike a fixed phone screen).
- The renderer uses DejaVu Sans (bundled on most systems). To match your brand
  font, point `_REG`/`_BOLD` in `renderer.py` at your `.ttf` files.
- `app/runs/` accumulates outputs; delete it anytime to reclaim space.
