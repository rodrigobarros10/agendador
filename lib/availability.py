from datetime import datetime, timedelta, date as date_type

import streamlit as st

from lib.supabase_client import get_supabase
from lib.utils import generate_time_slots, day_of_week_from_date


def _overlaps(s1: datetime, e1: datetime, s2: datetime, e2: datetime) -> bool:
    return s1 < e2 and e1 > s2


@st.cache_data(ttl=30, show_spinner=False)
def get_available_slots(
    barber_id: str,
    service_id: str,
    duration_min: int,
    date_str: str,
) -> list[dict]:
    sb = get_supabase()
    date_obj = datetime.fromisoformat(date_str).date()
    day_of_week = day_of_week_from_date(date_obj)

    wh_res = (
        sb.table("working_hours")
        .select("start_time, end_time")
        .eq("barber_id", barber_id)
        .eq("day_of_week", day_of_week)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not wh_res.data:
        return []
    wh = wh_res.data[0]

    day_start = datetime.fromisoformat(date_str).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start.replace(hour=23, minute=59, second=59, microsecond=999999)

    existing_res = sb.rpc(
        "get_booked_slots",
        {"p_barber_id": barber_id, "p_date": date_str},
    ).execute()

    time_off_res = (
        sb.table("time_off")
        .select("start_at, end_at")
        .eq("barber_id", barber_id)
        .lte("start_at", day_end.isoformat())
        .gte("end_at", day_start.isoformat())
        .execute()
    )

    all_slots = generate_time_slots(wh["start_time"], wh["end_time"], duration_min, date_str)
    cutoff = datetime.now() + timedelta(minutes=30)

    available = []
    for slot in all_slots:
        slot_start = datetime.fromisoformat(slot["starts_at"])
        slot_end = datetime.fromisoformat(slot["ends_at"])

        if slot_start <= cutoff:
            continue

        appointment_conflict = any(
            _overlaps(
                slot_start, slot_end,
                datetime.fromisoformat(a["starts_at"]),
                datetime.fromisoformat(a["ends_at"]),
            )
            for a in (existing_res.data or [])
        )
        time_off_conflict = any(
            _overlaps(
                slot_start, slot_end,
                datetime.fromisoformat(t["start_at"]),
                datetime.fromisoformat(t["end_at"]),
            )
            for t in (time_off_res.data or [])
        )

        if not appointment_conflict and not time_off_conflict:
            available.append(slot)

    return available
