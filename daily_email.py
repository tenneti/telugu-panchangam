"""
daily_email.py — Computes today's Panchangam and sends an HTML email.

Run manually:  python daily_email.py
Run via CI:    triggered by GitHub Actions every morning

Required environment variables (set as GitHub Secrets):
    GMAIL_USER     — your Gmail address (sender)
    GMAIL_APP_PASS — Gmail App Password (not your login password)
    EMAIL_TO       — recipient email address
"""

import os
import smtplib
import sys
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jhora.panchanga import drik
from jhora import utils

from telugu_panchangam_db_generator import (
    AppPlace,
    NAKSHATRA_NAMES,
    TARA_CATEGORIES,
    compute_one_day,
    tara_bala,
    AYANAMSA_MODE,
)
from app import (
    get_samvatsara,
    get_ayana,
    RITU_NAMES,
    MASA_NAMES,
    TITHI_SHORT,
)

# -------------------------------------------------------------------
# CONFIG  (edit these or override via environment variables)
# -------------------------------------------------------------------

CITY    = AppPlace("Bangalore", 12.9716, 77.5946, 5.5)
BIRTH_NAK = 11          # 11 = Purva Phalguni

GMAIL_USER     = os.environ.get("GMAIL_USER",     "")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "")
EMAIL_TO       = os.environ.get("EMAIL_TO",       "")

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

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
        if parts[0] != base_date.isoformat():
            try:
                from datetime import date as _date
                d = _date.fromisoformat(parts[0])
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


VERDICT_STYLE = {
    "Very Good":   "color:#1b5e20;font-weight:bold",
    "Good":        "color:#2e7d32;font-weight:bold",
    "Bad":         "color:#b71c1c;font-weight:bold",
    "Totally Bad": "color:#7f0000;font-weight:bold",
    "Not Good":    "color:#e65100;font-weight:bold",
}


def row(label: str, value: str) -> str:
    return (
        f"<tr>"
        f"<td style='padding:4px 12px 4px 0;color:#555;white-space:nowrap'>{label}</td>"
        f"<td style='padding:4px 0;font-weight:600'>{value}</td>"
        f"</tr>"
    )


def section(title: str, rows_html: str) -> str:
    return (
        f"<h3 style='margin:16px 0 4px;color:#333;border-bottom:1px solid #ddd;padding-bottom:4px'>{title}</h3>"
        f"<table style='border-collapse:collapse;width:100%'>{rows_html}</table>"
    )


# -------------------------------------------------------------------
# Build data
# -------------------------------------------------------------------

def get_vedic_line(d: date, tithi_num: int) -> str:
    """Builds the traditional sankalpa header line."""
    pj_place = CITY.to_pyjhora_place()
    jd = utils.julian_day_number((d.year, d.month, d.day), (12, 0, 0))

    masa_num = None
    try:
        result = drik.lunar_month(jd, pj_place)
        idx = result[0] if isinstance(result, (list, tuple)) else int(result)
        masa_num = 12 if idx == 0 else idx
    except Exception:
        pass

    samvat = get_samvatsara(d, masa_num)
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


def get_today_data(d: date) -> dict:
    data = compute_one_day(d, CITY)

    # Tarabala for primary nakshatra
    if data.get("nakshatra_num"):
        tb = tara_bala(data["nakshatra_num"], BIRTH_NAK)
        data.update(tb)

    # Check for nakshatra transition during the day
    from datetime import datetime, time
    nak_end = data.get("nakshatra_end_dt")
    if nak_end:
        nak_end_dt = datetime.fromisoformat(nak_end)
        day_midnight = datetime.combine(d, time(23, 59, 59))
        if nak_end_dt < day_midnight:
            tomorrow = compute_one_day(d + timedelta(days=1), CITY)
            if tomorrow.get("nakshatra_num"):
                tb2 = tara_bala(tomorrow["nakshatra_num"], BIRTH_NAK)
                data["nakshatra2_num"]      = tomorrow["nakshatra_num"]
                data["nakshatra2_name"]     = tomorrow["nakshatra_name"]
                data["nakshatra2_start_dt"] = nak_end
                data["tara2_index"]         = tb2["tara_index"]
                data["tara2_name"]          = tb2["tara_name"]
                data["tara2_verdict"]       = tb2["tara_verdict"]

    return data


# -------------------------------------------------------------------
# Build HTML email
# -------------------------------------------------------------------

def build_html(d: date, data: dict) -> str:
    birth_nak_name = NAKSHATRA_NAMES.get(BIRTH_NAK, "")

    # Nakshatra display
    nak_name = data.get("nakshatra_name", "—")
    nak_end  = fmt(data.get("nakshatra_end_dt"))
    if data.get("nakshatra2_name"):
        nak_cell = f"{nak_name} (until {nak_end}), then {data['nakshatra2_name']} (from {nak_end})"
    else:
        nak_cell = f"{nak_name} (until {nak_end})"

    # Tarabala display
    verdict  = data.get("tara_verdict", "")
    vstyle   = VERDICT_STYLE.get(verdict, "")
    tb_line  = (
        f"{nak_name} → {data.get('tara_index','')}.{data.get('tara_name','')} "
        f"<span style='{vstyle}'>{verdict}</span>"
    )
    if data.get("nakshatra2_name"):
        v2      = data.get("tara2_verdict", "")
        vs2     = VERDICT_STYLE.get(v2, "")
        tb_line += (
            f"<br>{data['nakshatra2_name']} → {data.get('tara2_index','')}.{data.get('tara2_name','')} "
            f"<span style='{vs2}'>{v2}</span>"
        )

    pancha_rows = (
        row("Tithi",     f"{data.get('tithi_name','—')}  {time_range(data.get('tithi_start_dt'), data.get('tithi_end_dt'))}")
        + row("Nakshatra", nak_cell)
        + row("Yoga",      f"{data.get('yoga_name','—')}  {time_range(data.get('yoga_start_dt'), data.get('yoga_end_dt'))}")
        + row("Karana",    f"{data.get('karana_name','—')}  {time_range(data.get('karana_start_dt'), data.get('karana_end_dt'))}")
    )

    sun_moon_rows = (
        row("Sunrise",  fmt(data.get("sunrise_dt")))
        + row("Sunset",   fmt(data.get("sunset_dt")))
        + row("Moonrise", fmt(data.get("moonrise_dt")))
        + row("Moonset",  fmt(data.get("moonset_dt")))
    )

    dur_cell = time_range(data.get("durmuhurtham1_start_dt"), data.get("durmuhurtham1_end_dt"))
    if data.get("durmuhurtham2_start_dt"):
        dur_cell += f"<br>{time_range(data.get('durmuhurtham2_start_dt'), data.get('durmuhurtham2_end_dt'))}"

    inauspicious_rows = (
        row("Rahu Kalam",   time_range(data.get("rahu_start_dt"),      data.get("rahu_end_dt")))
        + row("Yamaganda",    time_range(data.get("yamaganda_start_dt"), data.get("yamaganda_end_dt")))
        + row("Gulika Kalam", time_range(data.get("gulika_start_dt"),    data.get("gulika_end_dt")))
        + row("Durmuhurtham", dur_cell)
    )

    auspicious_rows = (
        row("Amrita Ghadiyalu", time_range_aware(data.get("amrita_ghadiya_start_dt"), data.get("amrita_ghadiya_end_dt"), d))
        + row("Varjyam",        time_range_aware(data.get("varjyam1_start_dt"),       data.get("varjyam1_end_dt"), d))
    )

    vedic_line = get_vedic_line(d, data.get("tithi_num"))

    html = f"""
    <html><body style='font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#222'>

    <h2 style='margin-bottom:2px'>🌅 Telugu Panchangam</h2>
    <p style='margin:0;color:#555'>
        {data.get('weekday_name','')}, {d.strftime('%d %B %Y')} &nbsp;|&nbsp; {CITY.name}
    </p>
    <p style='margin:6px 0 0;font-size:0.82rem;color:#666;font-style:italic'>{vedic_line}</p>

    {section("Sun & Moon", sun_moon_rows)}
    {section("Pancha Anga", pancha_rows)}

    <h3 style='margin:16px 0 4px;color:#333;border-bottom:1px solid #ddd;padding-bottom:4px'>
        Tarabala for {birth_nak_name}
    </h3>
    <p style='margin:4px 0'>{tb_line}</p>

    {section("🔴 Inauspicious Periods", inauspicious_rows)}
    {section("🟢 Auspicious Periods",   auspicious_rows)}

    <p style='margin-top:20px;font-size:0.8rem;color:#aaa'>
        Generated by Telugu Panchangam · Lahiri ayanamsa
    </p>
    </body></html>
    """
    return html


# -------------------------------------------------------------------
# Send email
# -------------------------------------------------------------------

def send_email(subject: str, html: str) -> None:
    if not GMAIL_USER or not GMAIL_APP_PASS or not EMAIL_TO:
        print("ERROR: Set GMAIL_USER, GMAIL_APP_PASS, EMAIL_TO env vars.")
        sys.exit(1)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, EMAIL_TO, msg.as_string())
    print(f"Email sent to {EMAIL_TO}")


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

if __name__ == "__main__":
    today = date.today()
    data  = get_today_data(today)
    html  = build_html(today, data)
    subj  = f"Panchangam {today.strftime('%d %b %Y')} · {CITY.name}"
    send_email(subj, html)
