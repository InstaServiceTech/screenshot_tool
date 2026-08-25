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

## Run it locally

```bash
# macOS / Linux
./run.sh
# Windows
run.bat
```

Then open <http://127.0.0.1:5000>. Local `.env` defaults to `user` / `user`
(only on your machine; not used on the hosted site).

On macOS, port 5000 is often taken by AirPlay Receiver. Disable it in
**System Settings → General → AirPlay & Continuity**, or use Docker on another
host port (see below).

Manual setup instead of the scripts:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd app && python app.py
```

## Docker

Compose is not required. Build and run from the Dockerfile:

```bash
docker build -t screenshot-tool .
docker run -d --name screenshot-tool-container --restart=always \
  -p 8000:5000 \
  -v screenshot-runs:/opt/screenshot-tool/app/runs \
  --env-file .env \
  screenshot-tool
```

Then open <http://127.0.0.1:8000>.

`-p 8000:5000` maps host port **8000** to the app port **5000** inside the
container. Use `5000:5000` if 5000 is free on the host.

`-v screenshot-runs:/opt/screenshot-tool/app/runs` persists uploaded Excel files,
generated PNGs, and ZIPs. Data survives container restarts and redeploys. It is
lost only if you delete the volume (`docker volume rm screenshot-runs`) or the
machine.

Stop / start:

```bash
docker stop screenshot-tool-container
docker start screenshot-tool-container
docker logs -f screenshot-tool-container
```

## Deploy (dev server)

GitHub Actions workflow: `.github/workflows/dev-build-push-deploy.yml`
(**Build and Deploy Docker Image**). Trigger it with **Run workflow**.

On the VM it:

1. Pulls the branch
2. Builds `screenshot-tool`
3. Recreates `screenshot-tool-container`

```bash
docker run -d --name screenshot-tool-container --restart=always \
  -p 5006:5000 \
  -v screenshot-runs:/opt/screenshot-tool/app/runs \
  --env-file .env \
  screenshot-tool
```

Public URL: **https://jobnotifications.instaservice.com** (login comes from
GitHub secrets, not the local `user`/`user` default).

Required GitHub secrets: `GCE_INSTANCE_IP`, `VM_SSH_PRIVATE_KEY`, `SECRET_KEY`,
`AUTH_USERS` (comma-separated `name:password` for the real team).

Dev URL: **http://\<GCE_INSTANCE_IP\>:5006/**

GCP must allow inbound **TCP 5006** (SSH on 22 is not enough). Example:

```bash
gcloud compute firewall-rules create allow-screenshot-tool-5006 \
  --direction=INGRESS \
  --priority=1000 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:5006 \
  --source-ranges=0.0.0.0/0
```

The VM must already have the repo cloned as `screenshot_tool` (the workflow
does `cd screenshot_tool` then `git pull`).

## Login and who generated what

The tool is public on the internet, so **sign-in is required**. Every Excel or
manual run is tagged with the signed-in username.

- Shown on the results page and in the header
- Listed under **History**
- Written into `meta.json` and `GENERATED_BY.txt` (included in the ZIP)

**Do not put passwords in git.** The hosted site does not use a default login.

- **Local:** `./run.sh` writes a gitignored `.env` with `AUTH_USERS=user:user` if
  none exists. That is only for http://127.0.0.1:5000.
- **Host:** the GitHub workflow writes `screenshot_tool/.env` from secrets
  `AUTH_USERS` and `SECRET_KEY`, then `docker run --env-file .env`. There is no
  `user:user` fallback on [jobnotifications.instaservice.com](https://jobnotifications.instaservice.com/).

Set repo secrets:

```
AUTH_USERS=sagar:PassOne,amit:PassTwo,neha:PassThree
SECRET_KEY=a-long-random-string
```

`.env` is gitignored and dockerignored. Credentials are never placed in the
public URL.

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
  app.py                 Flask routes (upload / preview / generate / manual / download)
  auth.py                login (hashed users.json)
  set_user.py            add/update a user (writes a hash, not the password)
  renderer.py            Pillow renderer — draws the Service Information screen
  data.py                Excel parsing + ServiceRecord mapping
  service_includes.json  editable Service Includes per service
  templates/             UI (login, upload + manual tabs, preview, results, history)
  runs/                  per-run output (screenshots + zip + who generated it)
.github/workflows/       deploy to the dev GCE VM
Dockerfile
requirements.txt
run.sh / run.bat
samples/                 example Excel + example renders
```

## Notes

- Output height is dynamic so nothing is cut off (unlike a fixed phone screen).
- The renderer uses DejaVu Sans (bundled on most systems). To match your brand
  font, point `_REG`/`_BOLD` in `renderer.py` at your `.ttf` files.
- `app/runs/` accumulates outputs; delete it anytime to reclaim space.
- Docker named volume `screenshot-runs` is the production copy of `app/runs/`.
