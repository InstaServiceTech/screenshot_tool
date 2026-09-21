"""
data.py — Excel parsing and ServiceRecord construction.

Maps the InstaService serviceDetails.xlsx schema to ServiceRecord objects and
supplies the "Service Includes" list from service_includes.json.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
from datetime import datetime, timedelta
from typing import List, Tuple

import pandas as pd

from renderer import ServiceRecord

_HERE = os.path.dirname(os.path.abspath(__file__))
_INCLUDES_PATH = os.path.join(_HERE, "service_includes.json")

# Columns the uploaded Excel must contain (matches the Appium tool's schema).
REQUIRED_COLUMNS = [
    "ServiceAmount", "ServiceName", "EstimatedTime", "City",
    "Zipcode", "CustomerName", "CustomerInstructions",
]
# Optional columns (used when present).
OPTIONAL_COLUMNS = [
    "Category", "BookingDateTime",
    "AddOn1", "AddOn1Value", "AddOn2", "AddOn2Value",
    "AddOn3", "AddOn3Value", "AddOn4", "AddOn4Value",
    "AddOn5", "AddOn5Value", "AddOn6", "AddOn6Value",
    "AddOn7", "AddOn7Value", "AddOn8", "AddOn8Value",
]

DEFAULT_BOOKING = "Mon, Aug 24, 2026, 10:30 AM"


def today_str() -> str:
    """Today's date as YYYY-MM-DD (for the date input's `min`)."""
    return datetime.now().strftime("%Y-%m-%d")


def default_booking_date() -> str:
    """Default picker value: tomorrow (a future date)."""
    return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")


DEFAULT_BOOKING_TIME = "10:30"

# Excel batch: random half-hour slots from 9:00 AM through 3:00 PM (inclusive).
BOOKING_SLOT_START_MINUTES = 9 * 60
BOOKING_SLOT_END_MINUTES = 15 * 60
BOOKING_SLOT_STEP_MINUTES = 30


def booking_time_slots() -> List[str]:
    """Half-hour clock times from 09:00 through 15:00."""
    slots = []
    minutes = BOOKING_SLOT_START_MINUTES
    while minutes <= BOOKING_SLOT_END_MINUTES:
        h, m = divmod(minutes, 60)
        slots.append(f"{h:02d}:{m:02d}")
        minutes += BOOKING_SLOT_STEP_MINUTES
    return slots


def staggered_booking_times(date_str: str, count: int) -> List[str]:
    """
    One booking datetime per row: shuffled 30-minute slots between 9 AM and 3 PM.
    Extra rows wrap to the next day and start again at 9:00.
    """
    if count <= 0:
        return []
    date_str = (date_str or "").strip() or default_booking_date()
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        day = datetime.strptime(default_booking_date(), "%Y-%m-%d")

    slots = booking_time_slots()
    out: List[str] = []
    remaining = count
    while remaining > 0:
        day_slots = slots[:]
        random.shuffle(day_slots)
        take = min(remaining, len(day_slots))
        day_key = day.strftime("%Y-%m-%d")
        for t in day_slots[:take]:
            out.append(format_booking(day_key, t))
        remaining -= take
        day += timedelta(days=1)
    return out


def format_booking(date_str: str, time_str: str = DEFAULT_BOOKING_TIME) -> str:
    """
    Turn a picked date (YYYY-MM-DD) + time (HH:MM, 24h) into the card's display
    string, e.g. 'Mon, Aug 24, 2026, 10:30 AM'. Falls back to DEFAULT_BOOKING
    if the inputs can't be parsed.
    """
    date_str = (date_str or "").strip()
    time_str = (time_str or DEFAULT_BOOKING_TIME).strip()
    if not date_str:
        return DEFAULT_BOOKING
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return DEFAULT_BOOKING
    day = str(dt.day)                       # no leading zero (24, not 04→"04")
    hour12 = dt.strftime("%I").lstrip("0") or "12"
    return f"{dt.strftime('%a')}, {dt.strftime('%b')} {day}, {dt.year}, {hour12}:{dt.strftime('%M')} {dt.strftime('%p')}"


def load_includes() -> dict:
    with open(_INCLUDES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _norm_service_key(s: str) -> str:
    return " ".join(str(s).lower().split())


def _include_entry(service_name: str, includes_map: dict | None = None):
    """Raw JSON entry for a service (list of includes, or {includes, excludes})."""
    includes_map = includes_map or load_includes()
    clean = service_name.split("*")[0].strip()
    if clean in includes_map:
        return includes_map[clean]
    target = _norm_service_key(clean)
    for key, val in includes_map.items():
        if key.startswith("_"):
            continue
        if _norm_service_key(key) == target:
            return val
    # Excel names often drop an "s" (Hourly Cleaning service) or extra words.
    if "hourly" in target and "cleaning" in target:
        return includes_map.get("Hourly Cleaning Services", includes_map.get("_default", []))
    if "handyman" in target:
        return includes_map.get("General Handyman Service", includes_map.get("_default", []))
    if "plumbing" in target:
        return includes_map.get("General Plumbing Service", includes_map.get("_default", []))
    return includes_map.get("_default", [])


def includes_for(service_name: str, includes_map: dict | None = None) -> List[str]:
    entry = _include_entry(service_name, includes_map)
    if isinstance(entry, dict):
        items = list(entry.get("includes") or [])
    elif isinstance(entry, list):
        items = list(entry)
    else:
        items = []
    name = _norm_service_key(service_name.split("*")[0])
    if any(k in name for k in ("handyman", "plumbing", "hourly")):
        return items[:3]
    return items


def excludes_for(service_name: str, includes_map: dict | None = None) -> List[str]:
    entry = _include_entry(service_name, includes_map)
    if isinstance(entry, dict):
        return list(entry.get("excludes") or [])[:2]
    return []


def _clean(v) -> str:
    """Blank out NaN/None and stringify."""
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v).strip()


def _zip5(v) -> str:
    s = _clean(v)
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(5) if s.isdigit() else s


def _amount(v) -> str:
    s = _clean(v)
    if s.endswith(".0"):
        s = s[:-2]
    return s


_ADDON_Q = re.compile(r"^addon\s*(\d+)$", re.I)
_ADDON_A = re.compile(r"^addon\s*(\d+)\s*value$", re.I)


def _row_keys(row):
    if hasattr(row, "index"):
        return [str(c) for c in row.index]
    if hasattr(row, "keys"):
        return [str(c) for c in row.keys()]
    return []


def _addons(row) -> List[Tuple[str, str]]:
    """Read every AddOnN / AddOnNValue pair on the row (any count, spacing, case)."""
    qs, ans = {}, {}
    for key in _row_keys(row):
        name = key.strip()
        mq, ma = _ADDON_Q.match(name), _ADDON_A.match(name)
        if mq:
            qs[int(mq.group(1))] = key
        elif ma:
            ans[int(ma.group(1))] = key
    pairs = []
    for i in sorted(set(qs) | set(ans)):
        q = _clean(row.get(qs.get(i, f"AddOn{i}")))
        a = _clean(row.get(ans.get(i, f"AddOn{i}Value")))
        if a.endswith(".0"):
            a = a[:-2]
        if q or a:
            pairs.append((q, a))
    return pairs


# Half bathrooms is always fixed. Square footage defaults to <=2500 but
# uses the Excel AddOn value when that question is present.
SQFT_LABEL = "What is the square footage of the house?"
SQFT_DEFAULT = "<=2500"
HALF_BATH_LABEL = "How many Half bathrooms?"
HALF_BATH_VALUE = "0"


def _pick_addon(pairs: List[Tuple[str, str]], *needles: str, exclude: str | None = None):
    """Return the first (q, a) whose question contains all needles."""
    for q, a in pairs:
        ql = q.lower()
        if exclude and exclude in ql:
            continue
        if all(n in ql for n in needles):
            return (q, a)
    return None


def _extra_house_fields(pairs: List[Tuple[str, str]],
                       sqft_override: str | None = None) -> List[Tuple[str, str]]:
    """The two extra Details rows: editable sqft, static half baths."""
    override = (sqft_override or "").strip()
    if override:
        sqft_val = override
    else:
        sqft = _pick_addon(pairs, "square footage")
        sqft_val = sqft[1].strip() if sqft and str(sqft[1]).strip() else SQFT_DEFAULT
    return [
        (SQFT_LABEL, sqft_val),
        (HALF_BATH_LABEL, HALF_BATH_VALUE),
    ]


def _full_house_addons(pairs: List[Tuple[str, str]],
                      sqft_override: str | None = None) -> List[Tuple[str, str]]:
    """
    Production Details order: Pets, bathrooms, bedrooms, then sqft (Excel or
    <=2500) and half baths (always 0), then Cleaning Type.
    """
    pets = _pick_addon(pairs, "pet")
    baths = _pick_addon(pairs, "bath", exclude="half")
    beds = _pick_addon(pairs, "bed")
    ctype = _pick_addon(pairs, "cleaning type") or _pick_addon(pairs, "cleaning")
    used = {p for p in (pets, baths, beds, ctype) if p}

    def is_extra_q(q: str) -> bool:
        ql = q.lower()
        return "square footage" in ql or "half bath" in ql

    rest = [(q, a) for q, a in pairs if (q, a) not in used and not is_extra_q(q)]

    out: List[Tuple[str, str]] = []
    for item in (pets, baths, beds):
        if item:
            out.append(item)
    out.extend(_extra_house_fields(pairs, sqft_override))
    out.extend(rest)
    if ctype:
        out.append(ctype)
    return out


def row_to_record(row, includes_map: dict | None = None,
                  default_booking: str = DEFAULT_BOOKING,
                  square_footage: str | None = None) -> ServiceRecord:
    """`row` is a dict-like (pandas Series or plain dict)."""
    def g(key, default=""):
        val = row.get(key, default) if hasattr(row, "get") else default
        return val

    service_name = _clean(g("ServiceName"))
    booking = _clean(g("BookingDateTime")) or default_booking
    category = _clean(g("Category")).lower()
    name_l = service_name.lower()
    # Full House Cleaning → stacked Q&A in Details.
    # Hourly Cleaning Service (name or Category) → Customer Instructions + Service Includes.
    is_hourly = "hourly" in name_l or "hourly" in category
    is_full_house = "full house cleaning" in name_l and not is_hourly
    excel_addons = _addons(row)
    if is_full_house:
        addons = _full_house_addons(excel_addons, sqft_override=square_footage)
    elif is_hourly:
        addons = _extra_house_fields(excel_addons, sqft_override=square_footage)
    else:
        addons = []

    return ServiceRecord(
        amount=_amount(g("ServiceAmount")),
        service_name=service_name,
        estimated_time=_clean(g("EstimatedTime")),
        city=_clean(g("City")),
        zipcode=_zip5(g("Zipcode")),
        customer_name=_clean(g("CustomerName")),
        customer_instructions=_clean(g("CustomerInstructions")),
        booking_datetime=booking,
        includes=includes_for(service_name, includes_map),
        excludes=excludes_for(service_name, includes_map),
        addons=addons,
    )


def read_excel(path: str) -> Tuple[pd.DataFrame, List[str]]:
    """Return (dataframe, missing_required_columns)."""
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    return df, missing


def clean_file_name(service_name: str) -> str:
    """Screenshot file name = service name before '*' (matches the Appium tool)."""
    name = service_name.split("*")[0].strip()
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "-")
    return name or "service"


def safe_folder(city: str) -> str:
    city = _clean(city) or "Unknown"
    for ch in '\\/:*?"<>|':
        city = city.replace(ch, "-")
    return city
