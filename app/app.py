"""
app.py — Flask web UI for the Screenshot Tool (no emulator / no Appium).

Flows:
  • Upload an Excel (serviceDetails.xlsx pattern) -> preview rows -> "Generate
    Screenshots" -> renders each row to screenshots/<City>/<ServiceName>.png,
    zips the folder, offers a download.
  • Manual entry -> renders a single Service Information screen, shows it, and
    saves it under a city folder you can download.
"""
from __future__ import annotations

import os
import shutil
import uuid
import zipfile

from flask import (Flask, abort, redirect, render_template, request,
                   send_file, url_for)
from werkzeug.utils import secure_filename

from data import (DEFAULT_BOOKING, DEFAULT_BOOKING_TIME, REQUIRED_COLUMNS,
                  clean_file_name, default_booking_date, format_booking,
                  includes_for, load_includes, read_excel, row_to_record,
                  safe_folder, today_str)
from renderer import ServiceRecord, render_service_screen

_HERE = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(_HERE, "runs")
os.makedirs(RUNS_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB uploads


def _run_dir(run_id: str) -> str:
    d = os.path.join(RUNS_DIR, secure_filename(run_id))
    if not os.path.isdir(d):
        abort(404)
    return d


def _zip_folder(src_folder: str, zip_path: str) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src_folder):
            for name in files:
                fp = os.path.join(root, name)
                arc = os.path.relpath(fp, os.path.dirname(src_folder))
                zf.write(fp, arc)


# ── Home ─────────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return render_template("index.html", required=REQUIRED_COLUMNS,
                           default_booking=DEFAULT_BOOKING,
                           min_date=today_str(), default_date=default_booking_date(),
                           default_time=DEFAULT_BOOKING_TIME)


# ── Excel upload -> preview ───────────────────────────────────────────────────
@app.post("/upload")
def upload():
    file = request.files.get("excel")
    if not file or file.filename == "":
        return render_template("index.html", required=REQUIRED_COLUMNS,
                               default_booking=DEFAULT_BOOKING,
                               error="Please choose an .xlsx file to upload."), 400

    run_id = uuid.uuid4().hex[:12]
    rd = os.path.join(RUNS_DIR, run_id)
    os.makedirs(rd, exist_ok=True)
    xlsx_path = os.path.join(rd, secure_filename(file.filename))
    file.save(xlsx_path)

    try:
        df, missing = read_excel(xlsx_path)
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(rd, ignore_errors=True)
        return render_template("index.html", required=REQUIRED_COLUMNS,
                               default_booking=DEFAULT_BOOKING,
                               error=f"Could not read the Excel file: {e}"), 400

    if missing:
        shutil.rmtree(rd, ignore_errors=True)
        return render_template("index.html", required=REQUIRED_COLUMNS,
                               default_booking=DEFAULT_BOOKING,
                               error=f"Missing required columns: {', '.join(missing)}"), 400

    preview = df.head(50).fillna("").to_dict(orient="records")
    cities = sorted({str(r.get("City", "")).strip() for r in df.fillna("").to_dict("records") if str(r.get("City", "")).strip()})
    has_booking_col = "BookingDateTime" in df.columns
    return render_template("preview.html", run_id=run_id,
                           columns=list(df.columns), rows=preview,
                           total=len(df), cities=cities,
                           filename=os.path.basename(xlsx_path),
                           has_booking_col=has_booking_col,
                           min_date=today_str(), default_date=default_booking_date(),
                           default_time=DEFAULT_BOOKING_TIME)


# ── Generate all screenshots -> zip ───────────────────────────────────────────
@app.post("/generate/<run_id>")
def generate(run_id):
    rd = _run_dir(run_id)
    xlsx = next((os.path.join(rd, f) for f in os.listdir(rd) if f.lower().endswith((".xlsx", ".xls"))), None)
    if not xlsx:
        abort(404)

    df, missing = read_excel(xlsx)
    if missing:
        abort(400)

    includes_map = load_includes()
    # Optional batch-wide booking date/time chosen on the preview page. Applied to
    # every row that does not carry its own BookingDateTime column value.
    batch_booking = DEFAULT_BOOKING
    bd = request.form.get("booking_date", "").strip()
    if bd:
        batch_booking = format_booking(bd, request.form.get("booking_time", DEFAULT_BOOKING_TIME))

    shots_dir = os.path.join(rd, "screenshots")
    shutil.rmtree(shots_dir, ignore_errors=True)
    os.makedirs(shots_dir, exist_ok=True)

    results = []
    for _, row in df.iterrows():
        rec = row_to_record(row, includes_map, default_booking=batch_booking)
        if not rec.service_name or not rec.city:
            continue
        city_dir = os.path.join(shots_dir, safe_folder(rec.city))
        os.makedirs(city_dir, exist_ok=True)
        fname = clean_file_name(rec.service_name) + ".png"
        out = os.path.join(city_dir, fname)
        render_service_screen(rec, out)
        results.append({
            "city": safe_folder(rec.city),
            "file": fname,
            "rel": os.path.relpath(out, shots_dir).replace(os.sep, "/"),
        })

    zip_path = os.path.join(rd, "screenshots.zip")
    _zip_folder(shots_dir, zip_path)

    by_city: dict[str, list] = {}
    for r in results:
        by_city.setdefault(r["city"], []).append(r)

    return render_template("results.html", run_id=run_id, by_city=by_city,
                           count=len(results), cities=len(by_city))


# ── Manual single render ──────────────────────────────────────────────────────
@app.post("/manual")
def manual():
    f = request.form
    service_name = f.get("service_name", "").strip()
    city = f.get("city", "").strip()
    if not service_name or not city:
        return render_template("index.html", required=REQUIRED_COLUMNS,
                               default_booking=DEFAULT_BOOKING,
                               error="Service Name and City are required."), 400

    run_id = uuid.uuid4().hex[:12]
    rd = os.path.join(RUNS_DIR, run_id)
    shots_dir = os.path.join(rd, "screenshots")
    os.makedirs(shots_dir, exist_ok=True)

    booking = format_booking(
        f.get("booking_date", "").strip(),
        f.get("booking_time", DEFAULT_BOOKING_TIME).strip(),
    )
    rec = ServiceRecord(
        amount=f.get("amount", "").strip(),
        service_name=service_name,
        estimated_time=f.get("estimated_time", "").strip(),
        city=city,
        zipcode=f.get("zipcode", "").strip().zfill(5) if f.get("zipcode", "").strip().isdigit() else f.get("zipcode", "").strip(),
        customer_name=f.get("customer_name", "").strip(),
        customer_instructions=f.get("customer_instructions", "").strip(),
        booking_datetime=booking,
        includes=includes_for(service_name),
    )
    city_dir = os.path.join(shots_dir, safe_folder(city))
    os.makedirs(city_dir, exist_ok=True)
    fname = clean_file_name(service_name) + ".png"
    out = os.path.join(city_dir, fname)
    render_service_screen(rec, out)
    _zip_folder(shots_dir, os.path.join(rd, "screenshots.zip"))

    rel = os.path.relpath(out, shots_dir).replace(os.sep, "/")
    return render_template("manual_result.html", run_id=run_id,
                           city=safe_folder(city), file=fname, rel=rel)


# ── Serve generated images + zip ──────────────────────────────────────────────
@app.get("/img/<run_id>/<path:relpath>")
def img(run_id, relpath):
    rd = _run_dir(run_id)
    fp = os.path.normpath(os.path.join(rd, "screenshots", relpath))
    if not fp.startswith(os.path.join(rd, "screenshots")) or not os.path.isfile(fp):
        abort(404)
    return send_file(fp, mimetype="image/png")


@app.get("/download/<run_id>")
def download(run_id):
    rd = _run_dir(run_id)
    zip_path = os.path.join(rd, "screenshots.zip")
    if not os.path.isfile(zip_path):
        abort(404)
    return send_file(zip_path, as_attachment=True, download_name="screenshots.zip")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
