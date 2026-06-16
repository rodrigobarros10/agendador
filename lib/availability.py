import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, date as date_type

from lib.supabase_client import get_supabase
from lib.utils import generate_time_slots, day_of_week_from_date

_cache: dict = {}
_TTL = 60  # slots ficam em cache por 60s


def _overlaps(s1: datetime, e1: datetime, s2: datetime, e2: datetime) -> bool:
    return s1 < e2 and e1 > s2


def get_available_slots(
    barber_id: str,
    service_id: str,
    duration_min: int,
    date_str: str,
) -> list[dict]:
    key = (barber_id, service_id, duration_min, date_str)
    now = time.time()
    if key in _cache and now - _cache[key][0] < _TTL:
        return _cache[key][1]

    result = _compute(barber_id, service_id, duration_min, date_str)
    _cache[key] = (now, result)
    return result


def _compute(barber_id: str, service_id: str, duration_min: int, date_str: str) -> list[dict]:
    sb = get_supabase()
    date_obj = datetime.fromisoformat(date_str).date()
    day_of_week = day_of_week_from_date(date_obj)
    day_start = datetime.fromisoformat(date_str).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Executa as 3 queries em paralelo
    def fetch_working_hours():
        return sb.table("working_hours").select("start_time, end_time") \
            .eq("barber_id", barber_id).eq("day_of_week", day_of_week) \
            .eq("is_active", True).limit(1).execute().data

    def fetch_booked():
        return sb.rpc("get_booked_slots",
                      {"p_barber_id": barber_id, "p_date": date_str}).execute().data or []

    def fetch_time_off():
        return sb.table("time_off").select("start_at, end_at") \
            .eq("barber_id", barber_id) \
            .lte("start_at", day_end.isoformat()) \
            .gte("end_at", day_start.isoformat()).execute().data or []

    with ThreadPoolExecutor(max_workers=3) as ex:
        wh_f      = ex.submit(fetch_working_hours)
        booked_f  = ex.submit(fetch_booked)
        time_off_f = ex.submit(fetch_time_off)
        wh_data      = wh_f.result()
        booked_data  = booked_f.result()
        time_off_data = time_off_f.result()

    if not wh_data:
        return []

    wh = wh_data[0]
    all_slots = generate_time_slots(wh["start_time"], wh["end_time"], duration_min, date_str)
    cutoff = datetime.now() + timedelta(minutes=30)

    available = []
    for slot in all_slots:
        slot_start = datetime.fromisoformat(slot["starts_at"])
        slot_end   = datetime.fromisoformat(slot["ends_at"])

        if slot_start <= cutoff:
            continue

        if any(_overlaps(slot_start, slot_end,
                         datetime.fromisoformat(a["starts_at"]).replace(tzinfo=None),
                         datetime.fromisoformat(a["ends_at"]).replace(tzinfo=None))
               for a in booked_data):
            continue

        if any(_overlaps(slot_start, slot_end,
                         datetime.fromisoformat(t["start_at"]).replace(tzinfo=None),
                         datetime.fromisoformat(t["end_at"]).replace(tzinfo=None))
               for t in time_off_data):
            continue

        available.append(slot)

    return available
