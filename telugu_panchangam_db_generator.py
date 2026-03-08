"""
telugu_panchangam_db_generator.py

Generates a location-specific Telugu Panchangam SQLite database for 200 years.

What it stores per day:
- sunrise / sunset / moonrise / moonset
- tithi + start/end
- nakshatra + pada + start/end
- yoga + start/end
- karana + start/end
- Rahu Kalam / Yamaganda / Gulika Kalam
- Durmuhurtam (1 or 2 windows)
- Abhijit Muhurta
- Varjyam
- Amrita Ghadiyalu (Amrita Gadiya / Amrit Kalam)
- helper function for Tarabala-based user evaluation

Tested conceptually against the public PyJHora API/docs.
Depending on your installed version, you may need tiny import/signature adjustments.

Install:
    pip install PyJHora pyswisseph pandas

IMPORTANT:
1. PyJHora requires Swiss ephemeris data files. See its README.
2. Panchangam is location-specific. Generate one DB per city, or add city_id and loop cities.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

import pandas as pd

# PyJHora imports
from jhora import utils, const
from jhora.panchanga import drik

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

CITIES = [
    {"name": "Hyderabad",      "latitude": 17.3850, "longitude": 78.4867, "timezone": 5.5},
    {"name": "Visakhapatnam",  "latitude": 17.6868, "longitude": 83.2185, "timezone": 5.5},
    {"name": "Bangalore",      "latitude": 12.9716, "longitude": 77.5946, "timezone": 5.5},
]

START_YEAR = 1952
END_YEAR = 2082  # inclusive; 130 years total

# If you want closer traditional Lahiri-style handling, test with this.
# PyJHora versions differ in defaults, so pin and validate on sample dates.
AYANAMSA_MODE = "LAHIRI"

# -------------------------------------------------------------------
# LOOKUPS
# -------------------------------------------------------------------

TITHI_NAMES = {
    1: "Shukla Pratipada", 2: "Shukla Dwitiya", 3: "Shukla Tritiya", 4: "Shukla Chaturthi",
    5: "Shukla Panchami", 6: "Shukla Shashthi", 7: "Shukla Saptami", 8: "Shukla Ashtami",
    9: "Shukla Navami", 10: "Shukla Dashami", 11: "Shukla Ekadashi", 12: "Shukla Dwadashi",
    13: "Shukla Trayodashi", 14: "Shukla Chaturdashi", 15: "Pournami",
    16: "Krishna Pratipada", 17: "Krishna Dwitiya", 18: "Krishna Tritiya", 19: "Krishna Chaturthi",
    20: "Krishna Panchami", 21: "Krishna Shashthi", 22: "Krishna Saptami", 23: "Krishna Ashtami",
    24: "Krishna Navami", 25: "Krishna Dashami", 26: "Krishna Ekadashi", 27: "Krishna Dwadashi",
    28: "Krishna Trayodashi", 29: "Krishna Chaturdashi", 30: "Amavasya",
}

NAKSHATRA_NAMES = {
    1: "Ashwini", 2: "Bharani", 3: "Krittika", 4: "Rohini", 5: "Mrigashira", 6: "Ardra",
    7: "Punarvasu", 8: "Pushya", 9: "Ashlesha", 10: "Magha", 11: "Purva Phalguni",
    12: "Uttara Phalguni", 13: "Hasta", 14: "Chitra", 15: "Swati", 16: "Vishakha",
    17: "Anuradha", 18: "Jyeshtha", 19: "Mula", 20: "Purva Ashadha", 21: "Uttara Ashadha",
    22: "Shravana", 23: "Dhanishtha", 24: "Shatabhisha", 25: "Purva Bhadrapada",
    26: "Uttara Bhadrapada", 27: "Revati",
}

YOGA_NAMES = {
    1: "Vishkambha", 2: "Priti", 3: "Ayushman", 4: "Saubhagya", 5: "Shobhana", 6: "Atiganda",
    7: "Sukarma", 8: "Dhriti", 9: "Shoola", 10: "Ganda", 11: "Vriddhi", 12: "Dhruva",
    13: "Vyaghata", 14: "Harshana", 15: "Vajra", 16: "Siddhi", 17: "Vyatipata", 18: "Variyan",
    19: "Parigha", 20: "Shiva", 21: "Siddha", 22: "Sadhya", 23: "Shubha", 24: "Shukla",
    25: "Brahma", 26: "Indra", 27: "Vaidhriti",
}

# PyJHora returns karana as 1..60. This is the repeating cycle.
# For app display, it is often enough to map the active karana by cycle name.
KARANA_CYCLE_NAMES = [
    "Kimstughna", "Bava", "Balava", "Kaulava", "Taitila", "Garaja", "Vanija", "Vishti",
    "Bava", "Balava", "Kaulava", "Taitila", "Garaja", "Vanija", "Vishti",
]
# Final four fixed karanas appear at the end of Krishna Paksha:
# Shakuni, Chatushpada, Naga, Kimstughna
# We keep a helper below.

TARA_CATEGORIES = {
    1: ("Janma", "Not Good"),
    2: ("Sampat", "Very Good"),
    3: ("Vipat", "Bad"),
    4: ("Kshema", "Good"),
    5: ("Pratyak", "Bad"),
    6: ("Sadhana", "Very Good"),
    7: ("Naidhana", "Totally Bad"),
    8: ("Mitra", "Good"),
    9: ("Parama Mitra", "Good"),
}

# -------------------------------------------------------------------
# DATA CLASSES
# -------------------------------------------------------------------

@dataclass(frozen=True)
class AppPlace:
    name: str
    latitude: float
    longitude: float
    timezone: float

    def to_pyjhora_place(self):
        # PyJHora Place signature: Place('Place', latitude, longitude, timezone)
        return drik.Place(self.name, self.latitude, self.longitude, self.timezone)

# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------

def daterange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)

def local_noon_tuple() -> Tuple[int, int, int]:
    return (12, 0, 0)

def local_hours_to_dt(base_date: date, hours_value: Optional[float]) -> Optional[str]:
    """
    PyJHora often returns floating local hours, and some timings can be:
    - negative => previous day
    - > 24 => next day
    Convert to ISO local datetime string.
    """
    if hours_value is None:
        return None
    whole_seconds = round(hours_value * 3600)
    dt = datetime.combine(base_date, time(0, 0, 0)) + timedelta(seconds=whole_seconds)
    return dt.isoformat(sep=" ")

def dms_to_hours(dms_value: Any) -> Optional[float]:
    """
    utils.to_dms() style values often come back like [hh, mm, ss].
    """
    if dms_value is None:
        return None
    if isinstance(dms_value, (int, float)):
        return float(dms_value)
    if isinstance(dms_value, str):
        # trikalam/durmuhurtam return 'HH:MM:SS' strings
        parts = dms_value.split(':')
        if len(parts) == 3:
            try:
                h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                return h + m / 60.0 + s / 3600.0
            except (ValueError, TypeError):
                return None
    if isinstance(dms_value, (list, tuple)) and len(dms_value) >= 3:
        h, m, s = dms_value[:3]
        sign = -1 if h < 0 else 1
        h = abs(h)
        return sign * (h + m / 60.0 + s / 3600.0)
    return None

def normalize_time_window(base_date: date, start_val: Any, end_val: Any) -> Tuple[Optional[str], Optional[str]]:
    start_hours = dms_to_hours(start_val)
    end_hours = dms_to_hours(end_val)
    return local_hours_to_dt(base_date, start_hours), local_hours_to_dt(base_date, end_hours)

def karana_display_name(karana_no: Optional[int]) -> Optional[str]:
    if karana_no is None:
        return None

    # Traditional practical mapping for display.
    # PyJHora docs mention 1..60 sequence, but app users usually want the cycle name.
    if karana_no == 1:
        return "Kimstughna"
    if 2 <= karana_no <= 57:
        cycle = ["Bava", "Balava", "Kaulava", "Taitila", "Garaja", "Vanija", "Vishti"]
        return cycle[(karana_no - 2) % 7]
    if karana_no == 58:
        return "Shakuni"
    if karana_no == 59:
        return "Chatushpada"
    if karana_no == 60:
        return "Naga"
    return f"Karana-{karana_no}"

def tara_bala(day_nakshatra_num: int, birth_nakshatra_num: int) -> Dict[str, Any]:
    """
    Inclusive counting from Janma Nakshatra.
    Formula:
        distance = ((day - birth) % 27) + 1
        tara_index = ((distance - 1) % 9) + 1
    """
    distance = ((day_nakshatra_num - birth_nakshatra_num) % 27) + 1
    tara_index = ((distance - 1) % 9) + 1
    tara_name, verdict = TARA_CATEGORIES[tara_index]
    return {
        "tara_index": tara_index,
        "tara_name": tara_name,
        "tara_verdict": verdict,
        "is_favourable": tara_index in {2, 4, 6, 8, 9},
    }

def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    PRAGMA journal_mode=WAL;

    CREATE TABLE IF NOT EXISTS panchang_day (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_name TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        timezone_hours REAL NOT NULL,
        gregorian_date TEXT NOT NULL,

        weekday_num INTEGER,
        weekday_name TEXT,

        sunrise_dt TEXT,
        sunset_dt TEXT,
        moonrise_dt TEXT,
        moonset_dt TEXT,

        tithi_num INTEGER,
        tithi_name TEXT,
        tithi_start_dt TEXT,
        tithi_end_dt TEXT,

        nakshatra_num INTEGER,
        nakshatra_name TEXT,
        nakshatra_pada INTEGER,
        nakshatra_start_dt TEXT,
        nakshatra_end_dt TEXT,

        yoga_num INTEGER,
        yoga_name TEXT,
        yoga_start_dt TEXT,
        yoga_end_dt TEXT,

        karana_num INTEGER,
        karana_name TEXT,
        karana_start_dt TEXT,
        karana_end_dt TEXT,

        rahu_start_dt TEXT,
        rahu_end_dt TEXT,
        yamaganda_start_dt TEXT,
        yamaganda_end_dt TEXT,
        gulika_start_dt TEXT,
        gulika_end_dt TEXT,

        durmuhurtham1_start_dt TEXT,
        durmuhurtham1_end_dt TEXT,
        durmuhurtham2_start_dt TEXT,
        durmuhurtham2_end_dt TEXT,

        abhijit_start_dt TEXT,
        abhijit_end_dt TEXT,

        varjyam1_start_dt TEXT,
        varjyam1_end_dt TEXT,
        varjyam2_start_dt TEXT,
        varjyam2_end_dt TEXT,

        amrita_ghadiya_start_dt TEXT,
        amrita_ghadiya_end_dt TEXT,

        created_at TEXT DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(location_name, gregorian_date)
    );

    CREATE INDEX IF NOT EXISTS idx_panchang_day_date
        ON panchang_day(gregorian_date);

    CREATE INDEX IF NOT EXISTS idx_panchang_day_location_date
        ON panchang_day(location_name, gregorian_date);
    """)

def compute_jd_for_local_date(d: date) -> float:
    """
    PyJHora utility usually expects local date and local time tuple.
    """
    return utils.julian_day_number((d.year, d.month, d.day), local_noon_tuple())

def safe_get(fn, *args, default=None, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default

def weekday_name_from_pyjhora(weekday_num: Optional[int]) -> Optional[str]:
    names = {
        0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday",
        4: "Thursday", 5: "Friday", 6: "Saturday"
    }
    return names.get(weekday_num)

# -------------------------------------------------------------------
# CORE COMPUTATION
# -------------------------------------------------------------------

def compute_one_day(d: date, place: AppPlace) -> Dict[str, Any]:
    pj_place = place.to_pyjhora_place()
    jd = compute_jd_for_local_date(d)

    # amrita_gadiya and varjyam must be called BEFORE set_ayanamsa_mode —
    # PyJHora bug: LAHIRI ayanamsa causes both to return identical wrong values.
    amrita = safe_get(drik.amrita_gadiya, jd, pj_place, default=None)
    varjyam = safe_get(drik.varjyam, jd, pj_place, default=None)

    # Strongly recommended for reproducible output
    safe_get(drik.set_ayanamsa_mode, AYANAMSA_MODE, None, jd)

    weekday_num = safe_get(drik.vaara, jd, default=None)
    weekday_name = weekday_name_from_pyjhora(weekday_num)

    sunrise = safe_get(drik.sunrise, jd, pj_place, default=None)
    sunset = safe_get(drik.sunset, jd, pj_place, default=None)
    moonrise = safe_get(drik.moonrise, jd, pj_place, default=None)
    moonset = safe_get(drik.moonset, jd, pj_place, default=None)

    tithi = safe_get(drik.tithi, jd, pj_place, default=None)
    nak = safe_get(drik.nakshatra, jd, pj_place, default=None)
    yoga = safe_get(drik.yogam, jd, pj_place, default=None)
    karana = safe_get(drik.karana, jd, pj_place, default=None)

    rahu = safe_get(drik.trikalam, jd, pj_place, "raahu kaalam", default=None)
    yamaganda = safe_get(drik.trikalam, jd, pj_place, "yamagandam", default=None)
    gulika = safe_get(drik.trikalam, jd, pj_place, "gulikai", default=None)

    durmuhurtham = safe_get(drik.durmuhurtam, jd, pj_place, default=None)
    abhijit = safe_get(drik.abhijit_muhurta, jd, pj_place, default=None)

    # Sunrise, sunset, moonrise, moonset
    sunrise_dt = local_hours_to_dt(d, sunrise[0]) if sunrise else None
    sunset_dt = local_hours_to_dt(d, sunset[0]) if sunset else None
    moonrise_dt = local_hours_to_dt(d, moonrise[0]) if moonrise else None
    moonset_dt = local_hours_to_dt(d, moonset[0]) if moonset else None

    # Tithi
    tithi_num = tithi[0] if tithi else None
    tithi_name = TITHI_NAMES.get(tithi_num)
    tithi_start_dt = local_hours_to_dt(d, tithi[1]) if tithi and len(tithi) > 2 else None
    tithi_end_dt = local_hours_to_dt(d, tithi[2]) if tithi and len(tithi) > 2 else None

    # Nakshatra
    nak_num = nak[0] if nak else None
    nak_pada = nak[1] if nak and len(nak) > 1 else None
    nak_name = NAKSHATRA_NAMES.get(nak_num)
    nak_start_dt = local_hours_to_dt(d, nak[2]) if nak and len(nak) > 3 else None
    nak_end_dt = local_hours_to_dt(d, nak[3]) if nak and len(nak) > 3 else None

    # Yoga
    yoga_num = yoga[0] if yoga else None
    yoga_name = YOGA_NAMES.get(yoga_num)
    yoga_start_dt = local_hours_to_dt(d, yoga[1]) if yoga and len(yoga) > 2 else None
    yoga_end_dt = local_hours_to_dt(d, yoga[2]) if yoga and len(yoga) > 2 else None

    # Karana
    karana_num = karana[0] if karana else None
    karana_name = karana_display_name(karana_num)
    karana_start_dt = local_hours_to_dt(d, karana[1]) if karana and len(karana) > 2 else None
    karana_end_dt = local_hours_to_dt(d, karana[2]) if karana and len(karana) > 2 else None

    # Trikalam
    rahu_start_dt, rahu_end_dt = normalize_time_window(d, rahu[0], rahu[1]) if rahu else (None, None)
    yamaganda_start_dt, yamaganda_end_dt = normalize_time_window(d, yamaganda[0], yamaganda[1]) if yamaganda else (None, None)
    gulika_start_dt, gulika_end_dt = normalize_time_window(d, gulika[0], gulika[1]) if gulika else (None, None)

    # Durmuhurtham can return 2 or 4 values
    dur1_start = dur1_end = dur2_start = dur2_end = None
    if durmuhurtham:
        if len(durmuhurtham) >= 2:
            dur1_start, dur1_end = normalize_time_window(d, durmuhurtham[0], durmuhurtham[1])
        if len(durmuhurtham) >= 4:
            dur2_start, dur2_end = normalize_time_window(d, durmuhurtham[2], durmuhurtham[3])

    # Abhijit
    abhijit_start_dt, abhijit_end_dt = normalize_time_window(d, abhijit[0], abhijit[1]) if abhijit else (None, None)

    # Varjyam can return 2 or 4 values (Mula special case)
    varjyam1_start = varjyam1_end = varjyam2_start = varjyam2_end = None
    if varjyam:
        if len(varjyam) >= 2:
            varjyam1_start, varjyam1_end = normalize_time_window(d, varjyam[0], varjyam[1])
        if len(varjyam) >= 4:
            varjyam2_start, varjyam2_end = normalize_time_window(d, varjyam[2], varjyam[3])

    # Amrita Ghadiyalu — returns hours from midnight (same unit as varjyam), may exceed 24 for next day
    amrita_start_dt, amrita_end_dt = normalize_time_window(d, amrita[0], amrita[1]) if amrita and len(amrita) >= 2 else (None, None)

    return {
        "location_name": place.name,
        "latitude": place.latitude,
        "longitude": place.longitude,
        "timezone_hours": place.timezone,
        "gregorian_date": d.isoformat(),

        "weekday_num": weekday_num,
        "weekday_name": weekday_name,

        "sunrise_dt": sunrise_dt,
        "sunset_dt": sunset_dt,
        "moonrise_dt": moonrise_dt,
        "moonset_dt": moonset_dt,

        "tithi_num": tithi_num,
        "tithi_name": tithi_name,
        "tithi_start_dt": tithi_start_dt,
        "tithi_end_dt": tithi_end_dt,

        "nakshatra_num": nak_num,
        "nakshatra_name": nak_name,
        "nakshatra_pada": nak_pada,
        "nakshatra_start_dt": nak_start_dt,
        "nakshatra_end_dt": nak_end_dt,

        "yoga_num": yoga_num,
        "yoga_name": yoga_name,
        "yoga_start_dt": yoga_start_dt,
        "yoga_end_dt": yoga_end_dt,

        "karana_num": karana_num,
        "karana_name": karana_name,
        "karana_start_dt": karana_start_dt,
        "karana_end_dt": karana_end_dt,

        "rahu_start_dt": rahu_start_dt,
        "rahu_end_dt": rahu_end_dt,
        "yamaganda_start_dt": yamaganda_start_dt,
        "yamaganda_end_dt": yamaganda_end_dt,
        "gulika_start_dt": gulika_start_dt,
        "gulika_end_dt": gulika_end_dt,

        "durmuhurtham1_start_dt": dur1_start,
        "durmuhurtham1_end_dt": dur1_end,
        "durmuhurtham2_start_dt": dur2_start,
        "durmuhurtham2_end_dt": dur2_end,

        "abhijit_start_dt": abhijit_start_dt,
        "abhijit_end_dt": abhijit_end_dt,

        "varjyam1_start_dt": varjyam1_start,
        "varjyam1_end_dt": varjyam1_end,
        "varjyam2_start_dt": varjyam2_start,
        "varjyam2_end_dt": varjyam2_end,

        "amrita_ghadiya_start_dt": amrita_start_dt,
        "amrita_ghadiya_end_dt": amrita_end_dt,
    }

def insert_day(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    cols = list(row.keys())
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"""
        INSERT OR REPLACE INTO panchang_day ({", ".join(cols)})
        VALUES ({placeholders})
    """
    conn.execute(sql, [row[c] for c in cols])

# -------------------------------------------------------------------
# USER-FACING QUERY LAYER
# -------------------------------------------------------------------

def get_day_for_user(
    conn: sqlite3.Connection,
    query_date: str,
    user_birth_nakshatra_num: int,
    location_name: str = CITIES[0]["name"],
) -> Dict[str, Any]:
    cur = conn.execute("""
        SELECT *
        FROM panchang_day
        WHERE location_name = ? AND gregorian_date = ?
    """, (location_name, query_date))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No panchang data found for {query_date} / {location_name}")

    col_names = [d[0] for d in cur.description]
    data = dict(zip(col_names, row))

    if data["nakshatra_num"]:
        tb = tara_bala(data["nakshatra_num"], user_birth_nakshatra_num)
        data.update(tb)

    # Check if nakshatra transitions during the day (ends before midnight)
    nak_end = data.get("nakshatra_end_dt")
    if nak_end:
        nak_end_dt = datetime.fromisoformat(nak_end)
        day_midnight = datetime.combine(date.fromisoformat(query_date), time(23, 59, 59))
        if nak_end_dt < day_midnight:
            next_date = (date.fromisoformat(query_date) + timedelta(days=1)).isoformat()
            cur2 = conn.execute("""
                SELECT nakshatra_num, nakshatra_name, nakshatra_start_dt, nakshatra_end_dt
                FROM panchang_day
                WHERE location_name = ? AND gregorian_date = ?
            """, (location_name, next_date))
            next_row = cur2.fetchone()
            if next_row:
                data["nakshatra2_num"] = next_row[0]
                data["nakshatra2_name"] = next_row[1]
                data["nakshatra2_start_dt"] = nak_end
                data["nakshatra2_end_dt"] = next_row[3]
                if next_row[0]:
                    tb2 = tara_bala(next_row[0], user_birth_nakshatra_num)
                    data["tara2_index"] = tb2["tara_index"]
                    data["tara2_name"] = tb2["tara_name"]
                    data["tara2_verdict"] = tb2["tara_verdict"]
                    data["is_favourable2"] = tb2["is_favourable"]

    # Simple advice summary for app UX
    warnings = []
    if data.get("rahu_start_dt") and data.get("rahu_end_dt"):
        warnings.append("Avoid starting major new activities during Rahu Kalam.")
    if data.get("durmuhurtham1_start_dt"):
        warnings.append("Avoid auspicious starts during Durmuhurtham.")
    if data.get("tara_verdict") in {"Bad", "Totally Bad", "Not Good"}:
        warnings.append(f"Nakshatra-wise, today is {data['tara_verdict']} for the user's birth star.")
    if data.get("tara2_verdict") in {"Bad", "Totally Bad", "Not Good"}:
        warnings.append(f"Second nakshatra ({data.get('nakshatra2_name')}) is also {data['tara2_verdict']} for the user's birth star.")

    data["app_advice"] = warnings
    return data

# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------

def build_database(city: Dict[str, Any]) -> None:
    place = AppPlace(
        name=city["name"],
        latitude=city["latitude"],
        longitude=city["longitude"],
        timezone=city["timezone"],
    )

    city_slug = city["name"].lower().replace(" ", "_")
    output_db = f"telugu_panchangam_{city_slug}_{START_YEAR}_{END_YEAR}.sqlite"
    output_csv = f"telugu_panchangam_{city_slug}_{START_YEAR}_{END_YEAR}.csv"

    start_date = date(START_YEAR, 1, 1)
    end_date = date(END_YEAR, 12, 31)

    db_path = Path(output_db)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)

        batch_rows: List[Dict[str, Any]] = []
        total = 0

        for d in daterange(start_date, end_date):
            row = compute_one_day(d, place)
            insert_day(conn, row)
            batch_rows.append(row)
            total += 1

            if total % 500 == 0:
                conn.commit()
                print(f"[{city['name']}] Inserted {total} days... latest={d.isoformat()}")

        conn.commit()
        print(f"[{city['name']}] Done. Inserted {total} days into {output_db}")

        # Optional CSV export
        df = pd.read_sql_query(
            "SELECT * FROM panchang_day ORDER BY gregorian_date",
            conn
        )
        df.to_csv(output_csv, index=False)
        print(f"[{city['name']}] CSV exported to {output_csv}")

        # Demo query: user born in Rohini (4)
        demo = get_day_for_user(conn, "2026-03-08", user_birth_nakshatra_num=4, location_name=city["name"])
        print(f"[{city['name']}] Sample user-facing response:")
        for k in [
            "gregorian_date",
            "nakshatra_name", "nakshatra_end_dt", "tara_name", "tara_verdict",
            "nakshatra2_name", "nakshatra2_start_dt", "tara2_name", "tara2_verdict",
            "rahu_start_dt", "rahu_end_dt",
            "yamaganda_start_dt", "yamaganda_end_dt",
            "durmuhurtham1_start_dt", "durmuhurtham1_end_dt",
            "amrita_ghadiya_start_dt", "amrita_ghadiya_end_dt"
        ]:
            print(f"  {k}: {demo.get(k)}")

    finally:
        conn.close()

if __name__ == "__main__":
    for city in CITIES:
        print(f"\n=== Generating database for {city['name']} ===")
        build_database(city)