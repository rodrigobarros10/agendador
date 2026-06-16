import uuid as _uuid
from datetime import datetime, timedelta, date as date_type

DAYS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MONTHS_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

# Python weekday(): 0=Mon … 6=Sun  →  nossa enum: monday … sunday
DAY_OF_WEEK_MAP = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def format_currency(cents: int) -> str:
    return f"R$ {cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_phone(value: str) -> str:
    digits = "".join(c for c in value if c.isdigit())[:11]
    if len(digits) <= 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}" if len(digits) > 6 else digits
    return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"


def mask_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"


def format_date_ptbr(date_str: str) -> str:
    d = datetime.fromisoformat(date_str) if isinstance(date_str, str) else date_str
    day_name = DAYS_PT[d.weekday()]
    month_name = MONTHS_PT[d.month - 1]
    return f"{day_name}, {d.day} de {month_name}"


def day_of_week_from_date(d: date_type) -> str:
    return DAY_OF_WEEK_MAP[d.weekday()]


def generate_time_slots(
    start_time: str,
    end_time: str,
    duration_min: int,
    date_str: str,
) -> list[dict]:
    start_h, start_m = map(int, start_time[:5].split(":"))
    end_h, end_m = map(int, end_time[:5].split(":"))

    base = datetime.fromisoformat(date_str)
    current = base.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = base.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

    slots = []
    while current < end:
        slot_end = current + timedelta(minutes=duration_min)
        if slot_end > end:
            break
        slots.append({
            "time": current.strftime("%H:%M"),
            "starts_at": current.isoformat(),
            "ends_at": slot_end.isoformat(),
        })
        current = slot_end

    return slots


def generate_ics(summary: str, description: str, start_dt: datetime, end_dt: datetime) -> bytes:
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Agendador//PT",
        "BEGIN:VEVENT",
        f"UID:{_uuid.uuid4()}",
        f"DTSTAMP:{now}",
        f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_esc(summary)}",
        f"DESCRIPTION:{_esc(description)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines).encode("utf-8")
