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
# Tithi nature reference (from thithi-reference.md)
# Key = tithi position within paksha (1-15); 30 = Amavasya.
# Tithis 16-29 share the same nature as 1-14 respectively.
# -------------------------------------------------------------------

TITHI_NATURE = {
    1:  {"nature": "Initiation & new beginnings",       "good": ["Starting routines, setting intentions", "Reorganizing personal life or workspace"],     "avoid": ["Large financial commitments", "Major travel decisions"],          "shukla": "Fresh beginnings and enthusiasm.",  "krishna": "Reflection, correcting past mistakes."},
    2:  {"nature": "Balance & cooperation",              "good": ["Partnerships, agreements, travel",      "Building trust between individuals"],           "avoid": ["Aggressive negotiations",           "Conflict-driven decisions"],        "shukla": "Supports new collaborations.",      "krishna": "Repairing relationships."},
    3:  {"nature": "Creativity & expansion",             "good": ["Artistic work, writing, learning",      "Skill development"],                            "avoid": ["Overconfidence in decisions",        "High-risk financial speculation"],  "shukla": "Excellent for creative pursuits.",  "krishna": "Improving existing skills."},
    4:  {"nature": "Overcoming obstacles",               "good": ["Problem-solving, complex analysis",     "Addressing pending difficulties"],              "avoid": ["Travel",                            "Starting new ventures or jobs"],    "shukla": "Good for confronting challenges.",  "krishna": "Removing internal obstacles."},
    5:  {"nature": "Learning & healing",                 "good": ["Education, spiritual study",            "Health-related decisions"],                     "avoid": ["Confrontational discussions",        "Legal disputes"],                  "shukla": "Supports intellectual growth.",     "krishna": "Healing and introspection."},
    6:  {"nature": "Discipline & structured progress",  "good": ["Organizing projects, routines",         "Physical health practices"],                    "avoid": ["Impulsive decisions",               "Emotional arguments"],             "shukla": "Building new systems.",             "krishna": "Strengthening existing habits."},
    7:  {"nature": "Vitality & movement",                "good": ["Travel, career decisions",              "Initiating public activities"],                 "avoid": ["Overworking yourself",              "Risky financial decisions"],        "shukla": "Strong energy for progress.",       "krishna": "Reviewing and adjusting direction."},
    8:  {"nature": "Intensity & transformation",         "good": ["Research, deep analysis",               "Confronting hidden issues"],                    "avoid": ["Beginning major ventures",          "Financial commitments"],           "shukla": "Strong transformative energy.",     "krishna": "Psychologically introspective."},
    9:  {"nature": "Courage & action",                   "good": ["Leadership, competitive environments",  "Overcoming fear"],                              "avoid": ["Peaceful negotiations",             "Sensitive relationship talks"],     "shukla": "Supports decisive action.",         "krishna": "Internal courage, self-discipline."},
    10: {"nature": "Success & achievement",              "good": ["Launching initiatives, career moves",   "Public announcements"],                         "avoid": ["Complacency",                       "Ignoring contract details"],        "shukla": "Excellent for visible achievements.", "krishna": "Consolidating success."},
    11: {"nature": "Purification & spiritual clarity",  "good": ["Fasting, meditation, reflection",       "Reducing mental distractions"],                 "avoid": ["Heavy material pursuits",           "Indulgence"],                      "shukla": "Spiritual upliftment and clarity.",  "krishna": "Deep introspection and discipline."},
    12: {"nature": "Recovery & restoration",             "good": ["Resuming normal activities",            "Family gatherings, balanced work"],             "avoid": ["Extreme actions or decisions"],                                       "shukla": "Supports social harmony.",          "krishna": "Gentle transitions."},
    13: {"nature": "Refinement & improvement",           "good": ["Correcting mistakes, negotiations",     "Preparing for important events"],               "avoid": ["Impulsive emotional reactions"],                                      "shukla": "Preparing for success.",            "krishna": "Introspective improvement."},
    14: {"nature": "Intense transformation",             "good": ["Spiritual practices",                   "Completing unfinished work"],                   "avoid": ["Major beginnings, business launches", "Travel"],                     "shukla": "Energy building toward completion.", "krishna": "Strong spiritual transformation."},
    15: {"nature": "Fullness & illumination",            "good": ["Celebrations, community gatherings",    "Creative expression, teaching"],                "avoid": ["Emotionally sensitive decisions",   "Impulsive reactions"],             "shukla": "Energy is emotionally heightened.",  "krishna": None},
    30: {"nature": "Closure & renewal",                  "good": ["Meditation, honoring ancestors",        "Releasing old patterns, introspection"],        "avoid": ["Starting new jobs",                 "Financial commitments, long journeys"], "shukla": None, "krishna": "Energy is inward and quiet."},
}


def tithi_nature_key(tithi_num):
    """Map DB tithi number (1-30) to TITHI_NATURE key."""
    if tithi_num is None:
        return None
    if tithi_num == 30:
        return 30
    if tithi_num == 15:
        return 15
    if tithi_num > 15:
        return tithi_num - 15
    return tithi_num


# -------------------------------------------------------------------
# Nakshatra wisdom (Feature 4 data)
# -------------------------------------------------------------------

NAKSHATRA_WISDOM = {
    1:  {"theme": "New Beginnings & Healing",          "advice": ["Favorable for starting new ventures and travel", "Good for medical treatments and physical activity", "Move swiftly — Ashwini energy rewards quick action"]},
    2:  {"theme": "Transformation & Discipline",        "advice": ["Good for completing tasks and taking responsibility", "Avoid hasty decisions or shortcuts", "A day for disciplined effort and long-term thinking"]},
    3:  {"theme": "Clarity & Courage",                  "advice": ["Good day to confront challenges directly", "Favorable for cutting away what no longer serves", "Speak your truth — clarity brings results today"]},
    4:  {"theme": "Growth & Abundance",                 "advice": ["Excellent for creative work, relationships, and planting seeds", "Favorable for financial matters and agriculture", "Nurture what matters — Rohini blesses steady growth"]},
    5:  {"theme": "Curiosity & Exploration",            "advice": ["Good for research, travel, and new connections", "Keep an open mind — seek before concluding", "Favorable for learning and intellectual pursuits"]},
    6:  {"theme": "Transformation Through Storm",       "advice": ["Good for letting go of the old", "Avoid major new beginnings today", "Inner transformation is possible — reflect deeply"]},
    7:  {"theme": "Renewal & Return",                   "advice": ["Good for revisiting old projects and reconciliation", "Favorable for restoring relationships and trust", "What was lost can be regained today"]},
    8:  {"theme": "Nourishment & Prosperity",           "advice": ["Excellent for financial matters and family decisions", "Favorable for spiritual practice and religious ceremonies", "One of the most auspicious nakshatras — plan important work today"]},
    9:  {"theme": "Introspection & Mysticism",          "advice": ["Good for research, inner work, and independent projects", "Avoid public confrontations and unnecessary arguments", "Trust your intuition — hidden insights are accessible today"]},
    10: {"theme": "Authority & Ancestry",               "advice": ["Good for ceremonial work and leadership decisions", "Favorable for honoring elders and family traditions", "Act with dignity — Magha rewards those with integrity"]},
    11: {"theme": "Creativity & Enjoyment",             "advice": ["Good for leisure, relationships, and artistic pursuits", "Favorable for celebrations and social gatherings", "Enjoy the moment — Purva Phalguni blesses rest and pleasure"]},
    12: {"theme": "Service & Stability",                "advice": ["Good for long-term commitments and contracts", "Favorable for partnerships and cooperative work", "Build for the future — steady effort brings lasting results"]},
    13: {"theme": "Skill & Craftsmanship",              "advice": ["Excellent for detailed work, negotiations, and trade", "Favorable for hands-on tasks and technical work", "Precision matters today — take care with the details"]},
    14: {"theme": "Artistry & Brilliance",              "advice": ["Good for creative projects, architecture, and design", "Favorable for making things beautiful and impactful", "Express yourself — Chitra rewards bold creativity"]},
    15: {"theme": "Independence & Flexibility",         "advice": ["Good for business, trading, and independent decisions", "Avoid rigidity — adapt to what the day brings", "Swati favors those who move with the wind, not against it"]},
    16: {"theme": "Focus & Ambition",                   "advice": ["Good for goal-setting and finishing pending work", "Favorable for intense focus and achieving targets", "Push through obstacles — Vishakha energy sustains effort"]},
    17: {"theme": "Devotion & Friendship",              "advice": ["Good for teamwork, spiritual practice, and relationships", "Favorable for group activities and social bonding", "Loyalty is rewarded — show up for those who matter"]},
    18: {"theme": "Seniority & Protection",             "advice": ["Good for leadership roles and protecting others", "Avoid unnecessary rivalry or competitive behavior", "Take responsibility — Jyeshtha rewards the elder mind"]},
    19: {"theme": "Root & Investigation",               "advice": ["Good for research, uncovering truth, and deep analysis", "Avoid destruction or abrupt endings without reflection", "Go to the root cause — Mula energy reveals what is hidden"]},
    20: {"theme": "Perseverance & Purification",        "advice": ["Good for sustained effort and water-related activities", "Favorable for cleansing, purification, and long projects", "Stay the course — Purva Ashadha rewards those who persist"]},
    21: {"theme": "Victory & Achievement",              "advice": ["Excellent for important launches and difficult tasks", "Favorable for pushing through final obstacles", "Act boldly — Uttara Ashadha carries the energy of final victory"]},
    22: {"theme": "Listening & Learning",               "advice": ["Good for education, spiritual learning, and communication", "Favorable for listening carefully before responding", "Knowledge gathered today can guide you for years"]},
    23: {"theme": "Wealth & Rhythm",                    "advice": ["Good for music, property matters, and financial planning", "Favorable for celebrations and social harmony", "Dhanishtha blesses those who give generously"]},
    24: {"theme": "Healing & Mystery",                  "advice": ["Good for medical treatment, research, and solitude", "Favorable for unconventional approaches to problems", "Look beyond the obvious — answers come from deeper sources"]},
    25: {"theme": "Intensity & Transformation",         "advice": ["Good for spiritual work and inner transformation", "Avoid anger, impulsive speech, and conflict", "Channel intensity constructively — today's fire can forge or destroy"]},
    26: {"theme": "Wisdom & Depth",                     "advice": ["Excellent for teaching, meditation, and long-term planning", "Favorable for philosophical reflection and writing", "Go slow and deep — Uttara Bhadrapada rewards patience"]},
    27: {"theme": "Completion & Compassion",            "advice": ["Good for endings, new beginnings, and acts of charity", "Favorable for letting go gracefully and starting fresh", "Revati closes one cycle and opens another — honor both"]},
}

# -------------------------------------------------------------------
# Tara descriptions (for 7-day forecast detail lines)
# -------------------------------------------------------------------

TARA_INFO = {
    1: {"desc1": "Birth-star energy — stay alert and present.",   "desc2": "Good for self-awareness, less ideal for risks."},
    2: {"desc1": "Wealth tara — excellent for gains and growth.", "desc2": "Favorable for financial and material matters."},
    3: {"desc1": "Danger tara — avoid risky actions today.",      "desc2": "Delays and obstacles are likely; plan conservatively."},
    4: {"desc1": "Prosperity tara — supports important work.",    "desc2": "Good for investments, key decisions, and planning."},
    5: {"desc1": "Obstruction tara — patience is advised.",       "desc2": "Focus on inner work; avoid forcing outcomes."},
    6: {"desc1": "Achievement tara — sustained effort pays off.", "desc2": "Good for completing projects and pushing forward."},
    7: {"desc1": "Inauspicious — delay major decisions today.",   "desc2": "Rest, reflect, and avoid irreversible commitments."},
    8: {"desc1": "Friendly star — good for collaborations.",      "desc2": "Partnerships and teamwork are especially favored."},
    9: {"desc1": "Best-friend star — highly auspicious day.",     "desc2": "Excellent for all important and auspicious work."},
}

# -------------------------------------------------------------------
# Feature helpers
# -------------------------------------------------------------------

def dt_to_min(dt_str):
    """Convert 'YYYY-MM-DD HH:MM:SS' to minutes from midnight (same day only)."""
    if not dt_str:
        return None
    parts = str(dt_str).split(" ")
    if len(parts) == 2:
        t = parts[1].split(":")
        mins = int(t[0]) * 60 + int(t[1])
        return mins if mins < 1440 else None   # ignore next-day values
    return None


def get_good_windows(data):
    """Return free (start_min, end_min) windows within sunrise–sunset."""
    day_start = dt_to_min(data.get("sunrise_dt"))
    day_end   = dt_to_min(data.get("sunset_dt"))
    if not day_start or not day_end:
        return []
    blocked = []
    for s_key, e_key in [
        ("rahu_start_dt",          "rahu_end_dt"),
        ("durmuhurtham1_start_dt", "durmuhurtham1_end_dt"),
        ("durmuhurtham2_start_dt", "durmuhurtham2_end_dt"),
        ("varjyam1_start_dt",      "varjyam1_end_dt"),
        ("varjyam2_start_dt",      "varjyam2_end_dt"),
    ]:
        s = dt_to_min(data.get(s_key))
        e = dt_to_min(data.get(e_key))
        if s and e and s < e:
            blocked.append((s, e))
    blocked.sort()
    free, current = [], day_start
    for bs, be in blocked:
        if bs > current:
            free.append((current, min(bs, day_end)))
        current = max(current, be)
    if current < day_end:
        free.append((current, day_end))
    return [(s, e) for s, e in free if e - s >= 20]


def min_to_hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def get_day_score(verdict):
    return {"Very Good": 90, "Good": 70, "Not Good": 40, "Bad": 25, "Totally Bad": 10}.get(verdict or "", 50)


def score_label(score):
    if score >= 80: return "Excellent", "🟢"
    if score >= 60: return "Good",      "🟡"
    if score >= 40: return "Neutral",   "🟠"
    return "Avoid major decisions", "🔴"


def load_week_data(city_name, start_date, birth_nak, days=7):
    from datetime import timedelta
    results = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        if date(START_YEAR, 1, 1) <= d <= date(END_YEAR, 12, 31):
            try:
                row = load_data(city_name, d, birth_nak)
                results.append((d, row))
            except Exception:
                pass
    return results


# -------------------------------------------------------------------
# Page config + CSS
# -------------------------------------------------------------------

st.set_page_config(page_title="Tara Veda", page_icon="🌅", layout="wide")

st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600&display=swap" rel="stylesheet">
<style>
  .stApp { background-color: #fdf8f2 !important; }
  .block-container { padding-top: 1rem !important; padding-bottom: 0 !important; }
  h3 { margin-top: 0.4rem !important; margin-bottom: 0.2rem !important;
       font-size: 1rem !important; color: #5a2d00 !important; }
  hr { margin: 0.4rem 0 !important; border-color: #e8d5b5 !important; }
  [data-testid="stSidebar"] { display: none; }
  [data-testid="stVerticalBlockBorderWrapper"] {
      border: 1.5px solid #c8903a !important;
      border-radius: 10px !important;
      padding: 0.5rem !important;
      background-color: #fffdf8 !important;
  }
  .stCaption p { color: #8b6020 !important; }
  .text-logo {
      font-family: 'Cinzel', serif;
      font-size: 2.6rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-align: center;
      padding: 0.6rem 0 0.4rem 0;
      color: #8b2500;
      text-shadow: 0 1px 2px rgba(180,80,0,0.12);
  }
  .controls-bar {
      background-color: #f5e8d0;
      border: 1px solid #ddb87a;
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

# ===================================================================
# TWO OUTER COLUMNS — left: Today + Planner | right: Forecast + Wisdom
# ===================================================================

col_left, col_right = st.columns(2)

# ----- LEFT COLUMN -------------------------------------------------
with col_left:

    with st.container(border=True):
        st.subheader(f"{data['weekday_name']}, {query_date.strftime('%d %B %Y')} — {city_name}")
        vedic_line = get_vedic_line(query_date, city_name, data.get("tithi_num"))
        st.caption(vedic_line)

        cols = st.columns(6)
        for col, label, key in zip(cols, [
            "Sunrise", "Sunset", "Moonrise", "Moonset", "Tithi", "Weekday",
        ], [
            "sunrise_dt", "sunset_dt", "moonrise_dt", "moonset_dt", "tithi_name", "weekday_name",
        ]):
            col.markdown(cell(label, fmt(data[key]) if key.endswith("_dt") else (data.get(key) or "—")), unsafe_allow_html=True)

        st.markdown("---")

        nc1, nc2 = st.columns([2, 3])
        with nc1:
            st.markdown("**Nakshatra**")
            nak_label = data.get("nakshatra_name") or "—"
            pada = data.get("nakshatra_pada")
            nak_str = nak_label + (f" (Pada {pada})" if pada else "")
            nak_end = fmt(data.get("nakshatra_end_dt"))
            st.markdown(cell("", nak_str, f"until {nak_end}"), unsafe_allow_html=True)
            if data.get("nakshatra2_name"):
                st.markdown(cell("", data["nakshatra2_name"], f"from {fmt(data.get('nakshatra2_start_dt'))}"), unsafe_allow_html=True)

        with nc2:
            st.markdown(f"**Tarabala** for {NAKSHATRA_NAMES[birth_nak]}")
            lines = [verdict_html(
                f"{data.get('nakshatra_name', '')}{'  (until ' + nak_end + ')' if data.get('nakshatra2_name') else ''}",
                data.get("tara_verdict", ""), data.get("tara_index"), data.get("tara_name"),
            )]
            if data.get("nakshatra2_name"):
                lines.append(verdict_html(
                    f"{data['nakshatra2_name']}  (from {fmt(data.get('nakshatra2_start_dt'))})",
                    data.get("tara2_verdict", ""), data.get("tara2_index"), data.get("tara2_name"),
                ))
            st.markdown("<br>".join(lines), unsafe_allow_html=True)

        st.markdown("---")

        p1, p2, p3 = st.columns(3)
        p1.markdown(cell("🔴 Rahu Kalam",  time_range(data.get("rahu_start_dt"),      data.get("rahu_end_dt"))),      unsafe_allow_html=True)
        p2.markdown(cell("🔴 Yamaganda",   time_range(data.get("yamaganda_start_dt"), data.get("yamaganda_end_dt"))), unsafe_allow_html=True)
        dur1 = time_range(data.get("durmuhurtham1_start_dt"), data.get("durmuhurtham1_end_dt"))
        dur2 = time_range(data.get("durmuhurtham2_start_dt"), data.get("durmuhurtham2_end_dt"))
        p3.markdown(cell("🔴 Durmuhurtham", dur1 if not data.get("durmuhurtham2_start_dt") else f"{dur1} | {dur2}"), unsafe_allow_html=True)
        st.markdown(cell("🟢 Amrita", time_range_aware(data.get("amrita_ghadiya_start_dt"), data.get("amrita_ghadiya_end_dt"), query_date)), unsafe_allow_html=True)

        advice = data.get("app_advice", [])
        if advice:
            st.markdown("---")
            st.markdown("\n".join(f"- {note}" for note in advice))

    with st.container(border=True):
        st.subheader("Activity Planner")
        st.caption("Avoids Rahu Kalam, Durmuhurtham, Varjyam")

        st.selectbox("Select activity", [
            "Travel", "Business Decisions", "Financial Transactions",
            "Medical Appointments", "Important Meetings", "Starting New Projects",
        ], key="activity_select")

        windows = get_good_windows(data)
        sunrise_min = dt_to_min(data.get("sunrise_dt"))
        sunset_min  = dt_to_min(data.get("sunset_dt"))
        if sunrise_min and sunset_min:
            st.markdown(f"**Daytime:** {min_to_hhmm(sunrise_min)} – {min_to_hhmm(sunset_min)}")

        if windows:
            st.markdown("**Good windows:**")
            for s, e in windows:
                st.markdown(f"🟢 **{min_to_hhmm(s)} – {min_to_hhmm(e)}** · _{e - s} min_")
        else:
            st.warning("No clear windows today.")

        st.markdown("**Avoid:**")
        for label, sk, ek in [
            ("Rahu Kalam",   "rahu_start_dt",         "rahu_end_dt"),
            ("Durmuhurtham", "durmuhurtham1_start_dt", "durmuhurtham1_end_dt"),
            ("Varjyam",      "varjyam1_start_dt",      "varjyam1_end_dt"),
        ]:
            if data.get(sk):
                st.markdown(f"🔴 **{label}:** {time_range(data.get(sk), data.get(ek))}")
        if data.get("amrita_ghadiya_start_dt"):
            st.markdown(f"🟢 **Amrita:** {time_range_aware(data.get('amrita_ghadiya_start_dt'), data.get('amrita_ghadiya_end_dt'), query_date)}")

# ----- RIGHT COLUMN ------------------------------------------------
with col_right:

    with st.container(border=True):
        st.subheader("7-Day Forecast")

        week = load_week_data(city_name, query_date, birth_nak, days=7)

        fc_tara, fc_tithi = st.columns(2)

        with fc_tara:
            st.caption(f"Tarabala — {NAKSHATRA_NAMES[birth_nak]}")
            for d, row in week:
                score = get_day_score(row.get("tara_verdict"))
                label, icon = score_label(score)
                nak = row.get("nakshatra_name", "—")
                tara_idx = row.get("tara_index")
                tara_nm  = row.get("tara_name", "")
                tinfo    = TARA_INFO.get(tara_idx, {})
                is_today = (d == query_date)
                day_label = "Today" if is_today else d.strftime("%a %d %b")
                tara_line = f"Tara {tara_idx} · {tara_nm}" if tara_idx and tara_nm else ""
                st.markdown(
                    f"{icon} **{day_label} · {nak}** — {label}<br>"
                    + (f"<span style='font-size:0.78rem;color:#555;margin-left:1.2rem'>{tara_line}</span><br>" if tara_line else "")
                    + (f"<span style='font-size:0.78rem;color:#555;margin-left:1.2rem'>{tinfo.get('desc1','')}</span><br>" if tinfo.get('desc1') else "")
                    + (f"<span style='font-size:0.78rem;color:#888;margin-left:1.2rem'>{tinfo.get('desc2','')}</span>" if tinfo.get('desc2') else ""),
                    unsafe_allow_html=True,
                )
                st.markdown("<div style='margin-bottom:0.4rem'></div>", unsafe_allow_html=True)
            st.markdown("---")
            st.caption("🟢 Excellent &nbsp; 🟡 Good &nbsp; 🟠 Neutral &nbsp; 🔴 Avoid")

        with fc_tithi:
            st.caption("Tithi Nature")
            for d, row in week:
                tnum = row.get("tithi_num")
                tname = row.get("tithi_name", "—")
                is_today = (d == query_date)
                day_label = "Today" if is_today else d.strftime("%a %d")
                paksha = "Shukla" if tnum and tnum <= 15 else "Krishna"
                key = tithi_nature_key(tnum)
                info = TITHI_NATURE.get(key)
                if info:
                    paksha_note = info.get(paksha.lower(), "") or ""
                    good_first = info["good"][0] if info["good"] else ""
                    avoid_first = info["avoid"][0] if info["avoid"] else ""
                    st.markdown(
                        f"**{day_label}** — {tname}<br>"
                        f"<span style='font-size:0.8rem;color:#555'>{info['nature']}</span><br>"
                        f"<span style='font-size:0.78rem;color:#2e7d32'>✔ {good_first}</span><br>"
                        f"<span style='font-size:0.78rem;color:#c62828'>✘ {avoid_first}</span>"
                        + (f"<br><span style='font-size:0.76rem;color:#888;font-style:italic'>{paksha_note}</span>" if paksha_note else ""),
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(f"**{day_label}** — {tname}")
                st.markdown("<div style='margin-bottom:0.4rem'></div>", unsafe_allow_html=True)

    with st.container(border=True):
        nak_num  = data.get("nakshatra_num")
        nak_name = data.get("nakshatra_name", "—")
        wisdom   = NAKSHATRA_WISDOM.get(nak_num)

        st.subheader(f"Daily Wisdom — {nak_name}")
        if data.get("nakshatra2_name"):
            st.caption(f"Transitions to {data['nakshatra2_name']} at {fmt(data.get('nakshatra2_start_dt'))}")

        if wisdom:
            st.markdown(f"**Theme:** {wisdom['theme']}")
            st.markdown("---")
            for line in wisdom["advice"]:
                st.markdown(f"- {line}")
        else:
            st.info("Wisdom not available for today's nakshatra.")

        if data.get("nakshatra2_name"):
            nak2_num = next((k for k, v in NAKSHATRA_NAMES.items() if v == data["nakshatra2_name"]), None)
            wisdom2  = NAKSHATRA_WISDOM.get(nak2_num)
            if wisdom2:
                st.markdown("---")
                st.markdown(f"**After transition — {data['nakshatra2_name']}**")
                st.markdown(f"**Theme:** {wisdom2['theme']}")
                for line in wisdom2["advice"]:
                    st.markdown(f"- {line}")

st.markdown("""
<hr style='border-color:#e8d5b5;margin-top:1.5rem;margin-bottom:0.6rem'>
<div style='text-align:center;font-size:0.8rem;color:#8b6020;padding-bottom:1rem'>
    &copy; 2026 Bhavani Technologies. All rights reserved.
</div>
""", unsafe_allow_html=True)
