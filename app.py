"""
app.py — Telugu Panchangam daily viewer

Run with:
    streamlit run app.py
"""

import sqlite3
from datetime import date
from pathlib import Path

import streamlit as st
from jhora.panchanga import drik
from jhora import utils

from telugu_panchangam_db_generator import (
    CITIES,
    NAKSHATRA_NAMES,
    START_YEAR,
    END_YEAR,
    get_day_for_user,
)

# -------------------------------------------------------------------
# Vedic calendar constants
# -------------------------------------------------------------------

SAMVATSARA_NAMES = [
    "Prabhava", "Vibhava", "Shukla", "Pramodoota", "Prajotpatti",
    "Aangirasa", "Shreemukha", "Bhaava", "Yuva", "Dhaatri",
    "Eeshwara", "Bahudhanya", "Pramathi", "Vikrama", "Vrisha",
    "Chitrabhanu", "Svabhanu", "Tarana", "Paarthiva", "Vyaya",
    "Sarvajit", "Sarvadharin", "Virodhi", "Vikriti", "Khara",
    "Nandana", "Vijaya", "Jaya", "Manmatha", "Durmukhi",
    "Hevilambi", "Vilambi", "Vikari", "Sharvari", "Plava",
    "Shubhakrit", "Shobhakrit", "Krodhi", "Vishvavasu", "Parabhava",
    "Plavanga", "Keelaka", "Saumya", "Sadharana", "Virodhikrit",
    "Paridhavi", "Pramaadi", "Aananda", "Raakshasa", "Anala",
    "Pingala", "Kaalayukti", "Siddharthi", "Raudri", "Durmati",
    "Dundubhi", "Rudhirodgari", "Raktaakshi", "Krodhana", "Akshaya",
]

MASA_NAMES = {
    1: "Chaitra", 2: "Vaishakha", 3: "Jyeshtha", 4: "Ashadha",
    5: "Shravana", 6: "Bhadrapada", 7: "Ashwina", 8: "Kartika",
    9: "Margashirsha", 10: "Pausha", 11: "Magha", 12: "Phalguna",
}

# Ritu (season) per masa number — two masas per ritu
RITU_NAMES = {
    1: "Vasanta", 2: "Vasanta",
    3: "Greeshma", 4: "Greeshma",
    5: "Varsha",   6: "Varsha",
    7: "Sharad",   8: "Sharad",
    9: "Hemantha", 10: "Hemantha",
    11: "Sisira",  12: "Sisira",
}

# Short tithi name (without Shukla/Krishna prefix — paksha covers that)
TITHI_SHORT = {
    1: "Pratipada", 2: "Dwitiya", 3: "Tritiya", 4: "Chaturthi",
    5: "Panchami",  6: "Shashthi", 7: "Saptami", 8: "Ashtami",
    9: "Navami",    10: "Dashami", 11: "Ekadashi", 12: "Dwadashi",
    13: "Trayodashi", 14: "Chaturdashi", 15: "Pournami",
    16: "Pratipada", 17: "Dwitiya", 18: "Tritiya", 19: "Chaturthi",
    20: "Panchami",  21: "Shashthi", 22: "Saptami", 23: "Ashtami",
    24: "Navami",    25: "Dashami", 26: "Ekadashi", 27: "Dwadashi",
    28: "Trayodashi", 29: "Chaturdashi", 30: "Amavasya",
}


def get_samvatsara(d: date) -> str:
    """Returns the 60-year cycle samvatsara name for the given date."""
    # Ugadi (Telugu new year) falls roughly in March/April.
    # Saka year increments at Ugadi; use month >= 4 as a safe proxy.
    saka_year = (d.year - 78) if d.month >= 4 else (d.year - 79)
    return SAMVATSARA_NAMES[(saka_year + 11) % 60]


def get_ayana(d: date) -> str:
    """Uttarayana: Makara Sankranti (~Jan 14) to Karka Sankranti (~Jul 16)."""
    doy = d.timetuple().tm_yday
    return "Uttarayana" if 14 <= doy <= 197 else "Dakshinayana"


def get_vedic_line(d: date, city_name: str, tithi_num: int) -> str:
    """Builds the traditional sankalpa header line."""
    city = next(c for c in CITIES if c["name"] == city_name)
    place = drik.Place(city["name"], city["latitude"], city["longitude"], city["timezone"])
    jd = utils.julian_day_number((d.year, d.month, d.day), (12, 0, 0))

    # Masa via PyJHora
    masa_num = None
    try:
        result = drik.lunar_month(jd, place)
        idx = result[0] if isinstance(result, (list, tuple)) else int(result)
        masa_num = 12 if idx == 0 else idx   # 0 = Phalguna (12th month)
    except Exception:
        pass

    samvat = get_samvatsara(d)
    ayana  = get_ayana(d)
    ritu   = RITU_NAMES.get(masa_num, "—") if masa_num else "—"
    masa   = MASA_NAMES.get(masa_num, "—") if masa_num else "—"
    paksha = "Shukla" if tithi_num and tithi_num <= 15 else "Krishna"
    tithi  = TITHI_SHORT.get(tithi_num, "—") if tithi_num else "—"

    return (
        f"{samvat} naama samvatsarae"
        f"  »  {ayana}e"
        f"  »  {ritu} rutou"
        f"  »  {masa} Maasae"
        f"  »  {paksha} Pakshae"
        f"  »  {tithi} Thithou"
    )

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

CITY_DB = {
    city["name"]: f"telugu_panchangam_{city['name'].lower().replace(' ', '_')}_{START_YEAR}_{END_YEAR}.sqlite"
    for city in CITIES
}


def load_data(city_name: str, query_date: date, birth_nak: int) -> dict:
    db_path = CITY_DB[city_name]
    if not Path(db_path).exists():
        st.error(f"Database not found: {db_path}\nRun telugu_panchangam_db_generator.py first.")
        st.stop()
    conn = sqlite3.connect(db_path)
    try:
        return get_day_for_user(conn, query_date.isoformat(), birth_nak, city_name)
    finally:
        conn.close()


def fmt(val) -> str:
    if not val:
        return "—"
    parts = str(val).split(" ")
    return parts[1][:5] if len(parts) == 2 else str(val)


def fmt_aware(val, base_date) -> str:
    """Like fmt() but appends '(next day)' when the datetime falls on a different date."""
    if not val:
        return "—"
    parts = str(val).split(" ")
    if len(parts) == 2:
        time_str = parts[1][:5]
        val_date = parts[0]
        if val_date != base_date.isoformat():
            from datetime import date as _date
            try:
                d = _date.fromisoformat(val_date)
                diff = (d - base_date).days
                suffix = " (next day)" if diff == 1 else f" (+{diff}d)"
                return f"{time_str}{suffix}"
            except ValueError:
                pass
        return time_str
    return str(val)


def time_range(start, end) -> str:
    return f"{fmt(start)} – {fmt(end)}"


def time_range_aware(start, end, base_date) -> str:
    return f"{fmt_aware(start, base_date)} – {fmt_aware(end, base_date)}"


def cell(label: str, value: str, caption: str = "") -> str:
    """Compact HTML cell: small grey label, bold value, optional caption."""
    cap = f"<br><span style='font-size:0.72rem;color:#888'>{caption}</span>" if caption else ""
    return (
        f"<div style='padding:4px 8px;'>"
        f"<div style='font-size:0.72rem;color:#888;margin-bottom:1px'>{label}</div>"
        f"<div style='font-weight:600;font-size:0.95rem'>{value}</div>"
        f"{cap}</div>"
    )


def verdict_html(name: str, verdict: str, tara_index: int = None, tara_name: str = None) -> str:
    colour = {"Very Good": "#2e7d32", "Good": "#388e3c",
              "Bad": "#c62828", "Totally Bad": "#b71c1c", "Not Good": "#e65100"}.get(verdict, "#555")
    tara_label = f"  <span style='color:#555;font-size:0.85rem'>{tara_index}. {tara_name}</span>" if tara_index and tara_name else ""
    return (
        f"<span style='font-weight:600'>{name}</span>{tara_label} "
        f"<span style='color:{colour};font-weight:600'>— {verdict}</span>"
    )


# -------------------------------------------------------------------
# Page config + CSS
# -------------------------------------------------------------------

st.set_page_config(page_title="Tara Veda", page_icon="🌅", layout="wide")

st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600&display=swap" rel="stylesheet">
<style>
  .block-container { padding-top: 1rem !important; padding-bottom: 0 !important; }
  h3 { margin-top: 0.4rem !important; margin-bottom: 0.2rem !important; font-size: 1rem !important; }
  hr { margin: 0.4rem 0 !important; }
  [data-testid="stSidebar"] { display: none; }
  .text-logo {
      font-family: 'Cinzel', serif;
      font-size: 2.6rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-align: center;
      padding: 0.6rem 0 0.4rem 0;
      color: #2c2c2c;
  }
  .controls-bar {
      background-color: #f0f0f0;
      border-radius: 8px;
      padding: 0.6rem 1rem;
      margin-bottom: 0.8rem;
  }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# Text logo
# -------------------------------------------------------------------

st.markdown('<div class="text-logo">Tara Veda</div>', unsafe_allow_html=True)

# -------------------------------------------------------------------
# Controls bar
# -------------------------------------------------------------------

st.markdown('<div class="controls-bar">', unsafe_allow_html=True)
c1, c2, c3 = st.columns([1, 2, 1])
with c1:
    city_name = st.selectbox("City", list(CITY_DB.keys()), index=2)
with c2:
    birth_nak = st.selectbox(
        "Birth Nakshatra",
        options=list(NAKSHATRA_NAMES.keys()),
        format_func=lambda n: f"{n}. {NAKSHATRA_NAMES[n]}",
        index=10,  # 11. Purva Phalguni
    )
with c3:
    query_date = st.date_input(
        "Date",
        value=date.today(),
        min_value=date(START_YEAR, 1, 1),
        max_value=date(END_YEAR, 12, 31),
    )
st.markdown('</div>', unsafe_allow_html=True)

# -------------------------------------------------------------------
# Load data
# -------------------------------------------------------------------

data = load_data(city_name, query_date, birth_nak)

# -------------------------------------------------------------------
# Title row
# -------------------------------------------------------------------

st.subheader(f"{data['weekday_name']}, {query_date.strftime('%d %B %Y')} — {city_name}")

vedic_line = get_vedic_line(query_date, city_name, data.get("tithi_num"))
st.caption(vedic_line)

# -------------------------------------------------------------------
# Sun / Moon row  (8 compact cells in one line)
# -------------------------------------------------------------------

cols = st.columns(6)
for col, label, key in zip(cols, [
    "Sunrise", "Sunset", "Moonrise", "Moonset",
    "Tithi", "Weekday",
], [
    "sunrise_dt", "sunset_dt", "moonrise_dt", "moonset_dt",
    "tithi_name", "weekday_name",
]):
    col.markdown(cell(label, fmt(data[key]) if key.endswith("_dt") else (data.get(key) or "—")), unsafe_allow_html=True)

st.markdown("---")

# -------------------------------------------------------------------
# Nakshatra + Tarabala row
# -------------------------------------------------------------------

nc1, nc2 = st.columns([2, 3])

with nc1:
    st.markdown("**Nakshatra**")
    nak_label = data.get("nakshatra_name") or "—"
    pada = data.get("nakshatra_pada")
    nak_str = f"{nak_label}" + (f" (Pada {pada})" if pada else "")
    nak_end = fmt(data.get("nakshatra_end_dt"))
    st.markdown(cell("", nak_str, f"until {nak_end}"), unsafe_allow_html=True)
    if data.get("nakshatra2_name"):
        st.markdown(cell("", data["nakshatra2_name"], f"from {fmt(data.get('nakshatra2_start_dt'))}"), unsafe_allow_html=True)

with nc2:
    st.markdown(f"**Tarabala** for {NAKSHATRA_NAMES[birth_nak]}")
    lines = [verdict_html(
        f"{data.get('nakshatra_name', '')}{'  (until ' + nak_end + ')' if data.get('nakshatra2_name') else ''}",
        data.get("tara_verdict", ""),
        data.get("tara_index"),
        data.get("tara_name"),
    )]
    if data.get("nakshatra2_name"):
        lines.append(verdict_html(
            f"{data['nakshatra2_name']}  (from {fmt(data.get('nakshatra2_start_dt'))})",
            data.get("tara2_verdict", ""),
            data.get("tara2_index"),
            data.get("tara2_name"),
        ))
    st.markdown("<br>".join(lines), unsafe_allow_html=True)

st.markdown("---")

# -------------------------------------------------------------------
# Inauspicious + Auspicious in one row (6 columns)
# -------------------------------------------------------------------

p1, p2, p3 = st.columns(3)

p1.markdown(cell("🔴 Rahu Kalam",   time_range(data.get("rahu_start_dt"),       data.get("rahu_end_dt"))),      unsafe_allow_html=True)
p2.markdown(cell("🔴 Yamaganda",    time_range(data.get("yamaganda_start_dt"),  data.get("yamaganda_end_dt"))), unsafe_allow_html=True)

dur1 = time_range(data.get("durmuhurtham1_start_dt"), data.get("durmuhurtham1_end_dt"))
dur2 = time_range(data.get("durmuhurtham2_start_dt"), data.get("durmuhurtham2_end_dt"))
dur_str = dur1 if not data.get("durmuhurtham2_start_dt") else f"{dur1} | {dur2}"
p3.markdown(cell("🔴 Durmuhurtham", dur_str), unsafe_allow_html=True)

st.markdown(cell("🟢 Amrita", time_range_aware(data.get("amrita_ghadiya_start_dt"), data.get("amrita_ghadiya_end_dt"), query_date)), unsafe_allow_html=True)

# -------------------------------------------------------------------
# Advice (compact, only if present)
# -------------------------------------------------------------------

advice = data.get("app_advice", [])
if advice:
    st.markdown("---")
    st.markdown("\n".join(f"- {note}" for note in advice))
