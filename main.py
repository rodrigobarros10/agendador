import os
import time
import urllib.parse
from datetime import date, datetime, timedelta

from fasthtml.common import *

from lib.availability import get_available_slots
from lib.supabase_client import get_supabase, get_supabase_admin
from lib.telegram import send_telegram, send_telegram_document
from lib.utils import format_currency, format_date_ptbr, format_phone, mask_phone, generate_ics

# ── App ───────────────────────────────────────────────────────────────────────

SECRET = os.environ.get("SESSION_SECRET", "dev-secret-change-in-prod")

app, rt = fast_app(
    secret_key=SECRET,
    hdrs=(
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Meta(charset="utf-8"),
    ),
    live=False,
)

# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: system-ui, -apple-system, sans-serif;
    background: #f5f5f5;
    color: #1a1a1a;
    min-height: 100vh;
}
.container {
    max-width: 560px;
    margin: 0 auto;
    padding: 1.25rem 1rem;
}
h1 { font-size: 1.4rem; font-weight: 700; }
h2 { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; }
.meta { color: #666; font-size: 0.875rem; }
.divider { border: none; border-top: 1px solid #e5e5e5; margin: 1rem 0; }

/* Cards */
.card {
    background: white;
    border: 1px solid #e5e5e5;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 0.75rem;
}

/* Option buttons (service / barber selection) */
.opt-btn {
    display: block;
    width: 100%;
    background: white;
    border: 1px solid #e5e5e5;
    border-radius: 10px;
    padding: 0.875rem 1rem;
    text-align: left;
    cursor: pointer;
    font-size: 0.95rem;
    margin-bottom: 0.5rem;
    transition: border-color 0.15s, background 0.15s;
}
.opt-btn:hover { border-color: #1a1a1a; background: #fafafa; }

/* Primary action button */
.btn-primary {
    display: block;
    width: 100%;
    background: #1a1a1a;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 0.875rem;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
    text-decoration: none;
    margin-top: 0.75rem;
    transition: background 0.15s;
}
.btn-primary:hover { background: #333; }

/* Secondary / back button */
.btn-back {
    background: none;
    border: none;
    color: #666;
    font-size: 0.875rem;
    cursor: pointer;
    padding: 0.5rem 0;
    display: inline-block;
    margin-top: 0.75rem;
}
.btn-back:hover { color: #1a1a1a; }

/* Time slots grid */
.slots-grid { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem; }
.slot-form { display: contents; }
.slot-btn {
    padding: 0.5rem 0.875rem;
    background: white;
    border: 1px solid #e5e5e5;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.9rem;
    transition: border-color 0.15s, background 0.15s;
}
.slot-btn:hover { border-color: #1a1a1a; background: #f5f5f5; }

/* Form inputs */
.field { margin-bottom: 0.875rem; }
.field label { display: block; font-size: 0.875rem; font-weight: 500; margin-bottom: 0.3rem; }
.field input, .field textarea {
    width: 100%;
    padding: 0.6rem 0.75rem;
    border: 1px solid #e5e5e5;
    border-radius: 8px;
    font-size: 0.95rem;
    font-family: inherit;
    transition: border-color 0.15s;
}
.field input:focus, .field textarea:focus {
    outline: none;
    border-color: #1a1a1a;
}
.field textarea { resize: vertical; min-height: 80px; }

/* Progress bar */
.progress { display: flex; gap: 0.4rem; margin-bottom: 1.25rem; }
.prog-step {
    flex: 1;
    text-align: center;
    font-size: 0.7rem;
    padding: 0.3rem 0.25rem;
    border-radius: 6px;
    background: #f0f0f0;
    color: #999;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.prog-step.done { background: #e8f5e9; color: #2e7d32; }
.prog-step.active { background: #1a1a1a; color: white; font-weight: 600; }

/* Error */
.error-msg {
    background: #fff0f0;
    border: 1px solid #ffcccc;
    border-radius: 8px;
    padding: 0.625rem 0.875rem;
    color: #c0392b;
    font-size: 0.875rem;
    margin-bottom: 0.75rem;
}

/* Success */
.success-box {
    background: #e8f5e9;
    border: 1px solid #c8e6c9;
    border-radius: 12px;
    padding: 1.5rem;
    text-align: center;
    margin-bottom: 1rem;
}
.success-box h2 { color: #2e7d32; margin-bottom: 0; }

/* Date input */
input[type="date"] {
    width: 100%;
    padding: 0.6rem 0.75rem;
    border: 1px solid #e5e5e5;
    border-radius: 8px;
    font-size: 0.95rem;
    margin-bottom: 0.75rem;
}
"""

# ── TTL cache for shop/barbers/services ───────────────────────────────────────

_shop_cache: dict = {}
_TTL = 60


def _cached(key: str, fn):
    now = time.time()
    if key in _shop_cache and now - _shop_cache[key][0] < _TTL:
        return _shop_cache[key][1]
    result = fn()
    _shop_cache[key] = (now, result)
    return result


def _load_shop(slug: str):
    return _cached(f"shop:{slug}", lambda: (
        get_supabase().table("barbershops").select("*")
        .eq("slug", slug).eq("is_active", True).limit(1).execute().data or [None]
    )[0])


def _load_barbers(shop_id: str):
    return _cached(f"barbers:{shop_id}", lambda:
        get_supabase().table("barbers").select("*")
        .eq("barbershop_id", shop_id).eq("is_active", True).execute().data or []
    )


def _load_services(shop_id: str):
    return _cached(f"services:{shop_id}", lambda:
        get_supabase().table("services").select("*")
        .eq("barbershop_id", shop_id).eq("is_active", True).order("sort_order").execute().data or []
    )

# ── Telegram ──────────────────────────────────────────────────────────────────

def _notify_telegram(client_name, phone_digits, svc, barber, date_str, slot):
    try:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = str(barber.get("telegram_chat_id", ""))
        if not bot_token or not chat_id:
            return
        msg = (
            f"<b>🗓 Novo agendamento!</b>\n\n"
            f"<b>Cliente:</b> {client_name}\n"
            f"<b>Telefone:</b> {format_phone(phone_digits)}\n"
            f"<b>Serviço:</b> {svc['name']} ({svc['duration_min']} min)\n"
            f"<b>Data:</b> {format_date_ptbr(date_str).capitalize()} às {slot['time']}\n"
            f"<b>Valor:</b> {format_currency(svc['price_cents'])}"
        )
        send_telegram(bot_token, chat_id, msg)
        start_dt = datetime.fromisoformat(slot["starts_at"])
        end_dt = datetime.fromisoformat(slot["ends_at"])
        ics = generate_ics(
            summary=f"{svc['name']} – {client_name}",
            description=(
                f"Cliente: {client_name}\n"
                f"Telefone: {format_phone(phone_digits)}\n"
                f"Serviço: {svc['name']} ({svc['duration_min']} min)\n"
                f"Valor: {format_currency(svc['price_cents'])}"
            ),
            start_dt=start_dt,
            end_dt=end_dt,
        )
        send_telegram_document(bot_token, chat_id, "agendamento.ics", ics)
    except Exception:
        pass

# ── UI helpers ────────────────────────────────────────────────────────────────

STEP_KEYS = ["service", "barber", "datetime", "form"]
STEP_LABELS = ["Serviço", "Profissional", "Horário", "Dados"]


def _progress(current: str):
    idx = STEP_KEYS.index(current) if current in STEP_KEYS else -1
    steps = []
    for i, label in enumerate(STEP_LABELS):
        if i < idx:
            cls = "prog-step done"
        elif i == idx:
            cls = "prog-step active"
        else:
            cls = "prog-step"
        steps.append(Div(label, cls=cls))
    return Div(*steps, cls="progress")


def _wizard(slug: str, step: str, *content):
    return Div(
        _progress(step) if step != "success" else "",
        *content,
        id="wizard",
    )


def _full_page(shop: dict, slug: str, step: str, *content):
    info = []
    if shop.get("address"):
        city = f", {shop['city']}" if shop.get("city") else ""
        info.append(f"📍 {shop['address']}{city}")
    if shop.get("phone"):
        info.append(f"📞 {mask_phone(shop['phone'])}")

    return (
        Style(CSS),
        Script(src="https://unpkg.com/htmx.org@2.0.4"),
        Div(
            H1(f"✂️ {shop['name']}"),
            P(shop["description"], cls="meta") if shop.get("description") else "",
            P("  ·  ".join(info), cls="meta") if info else "",
            Hr(cls="divider"),
            _wizard(slug, step, *content),
            cls="container",
        ),
    )

# ── Step components ───────────────────────────────────────────────────────────

def _step_service(slug: str, services: list):
    btns = [
        Form(
            Input(type="hidden", name="svc_id", value=s["id"]),
            Button(
                B(s["name"]),
                Span(f" — {format_currency(s['price_cents'])} · {s['duration_min']} min", cls="meta"),
                Br() if s.get("description") else "",
                Small(s["description"], cls="meta") if s.get("description") else "",
                type="submit", cls="opt-btn",
            ),
            hx_post=f"/{slug}/service",
            hx_target="#wizard",
            hx_swap="outerHTML",
        )
        for s in services
    ]
    return H2("Escolha o serviço"), *btns


def _step_barber(slug: str, barbers: list):
    btns = [
        Form(
            Input(type="hidden", name="barber_id", value=b["id"]),
            Button(
                B(b["name"]),
                Br() if b.get("bio") else "",
                Small(b["bio"], cls="meta") if b.get("bio") else "",
                type="submit", cls="opt-btn",
            ),
            hx_post=f"/{slug}/barber",
            hx_target="#wizard",
            hx_swap="outerHTML",
        )
        for b in barbers
    ]
    back = Button("← Voltar", hx_get=f"/{slug}/back/service",
                  hx_target="#wizard", hx_swap="outerHTML", cls="btn-back")
    return H2("Escolha o profissional"), *btns, back


def _step_datetime(slug: str, svc: dict, barber: dict, date_str: str = "", slots=None):
    today = date.today()
    date_val = date_str or today.isoformat()

    date_form = Form(
        Input(
            type="date", name="date_str", value=date_val,
            min=today.isoformat(),
            max=(today + timedelta(days=29)).isoformat(),
        ),
        Button("Ver horários →", type="submit", cls="btn-primary", style="margin-top:0"),
        hx_post=f"/{slug}/datetime",
        hx_target="#wizard",
        hx_swap="outerHTML",
    )

    slots_section = ""
    if slots is not None:
        if not slots:
            slots_section = P("Nenhum horário disponível. Tente outra data.", cls="meta",
                              style="margin-top:0.75rem")
        else:
            slot_forms = [
                Form(
                    Input(type="hidden", name="starts_at", value=s["starts_at"]),
                    Input(type="hidden", name="ends_at", value=s["ends_at"]),
                    Input(type="hidden", name="slot_time", value=s["time"]),
                    Button(s["time"], type="submit", cls="slot-btn"),
                    hx_post=f"/{slug}/slot",
                    hx_target="#wizard",
                    hx_swap="outerHTML",
                    cls="slot-form",
                )
                for s in slots
            ]
            slots_section = Div(*slot_forms, cls="slots-grid", style="margin-top:0.75rem")

    back = Button("← Voltar", hx_get=f"/{slug}/back/barber",
                  hx_target="#wizard", hx_swap="outerHTML", cls="btn-back")

    return (
        H2("Escolha a data e horário"),
        P(f"{svc['name']} · {svc['duration_min']} min · com {barber['name']}", cls="meta",
          style="margin-bottom:1rem"),
        date_form,
        slots_section,
        back,
    )


def _step_form(slug: str, svc: dict, barber: dict, date_str: str, slot: dict, errors=None):
    error_divs = [Div(e, cls="error-msg") for e in (errors or [])]
    return (
        H2("Seus dados"),
        Div(
            B(svc["name"]),
            Span(f" — {barber['name']} · {format_date_ptbr(date_str)} às {slot['time']}",
                 cls="meta"),
            Br(),
            B(format_currency(svc["price_cents"])),
            cls="card",
        ),
        *error_divs,
        Form(
            Div(Label("Nome completo *"),
                Input(type="text", name="name", placeholder="Seu nome", required=True),
                cls="field"),
            Div(Label("WhatsApp *"),
                Input(type="tel", name="phone", placeholder="(11) 99999-9999", maxlength="15"),
                cls="field"),
            Div(Label("E-mail (opcional)"),
                Input(type="email", name="email", placeholder="seuemail@exemplo.com"),
                cls="field"),
            Div(Label("Observações (opcional)"),
                Textarea(name="notes", maxlength="500", rows="3"),
                cls="field"),
            Button("Confirmar agendamento", type="submit", cls="btn-primary"),
            Button("← Voltar", hx_get=f"/{slug}/back/datetime",
                   hx_target="#wizard", hx_swap="outerHTML", cls="btn-back",
                   type="button"),
            hx_post=f"/{slug}/booking",
            hx_target="#wizard",
            hx_swap="outerHTML",
        ),
    )


def _step_success(slug: str, shop: dict, svc: dict, barber: dict, date_str: str, slot: dict):
    wa_btn = ""
    if shop.get("phone"):
        digits = "".join(c for c in shop["phone"] if c.isdigit())
        text = urllib.parse.quote(
            f"Olá! Confirmo meu agendamento na {shop['name']}:\n"
            f"Serviço: {svc['name']}\n"
            f"Profissional: {barber['name']}\n"
            f"Data: {format_date_ptbr(date_str)} às {slot['time']}"
        )
        wa_btn = A("💬 Confirmar via WhatsApp",
                   href=f"https://wa.me/{digits}?text={text}",
                   cls="btn-primary", target="_blank")

    return (
        Div(H2("✅ Agendamento confirmado!"), cls="success-box"),
        Div(
            P(f"Serviço: {svc['name']} — {format_currency(svc['price_cents'])}"),
            P(f"Profissional: {barber['name']}"),
            P(f"Data: {format_date_ptbr(date_str).capitalize()}"),
            P(f"Horário: {slot['time']} ({svc['duration_min']} min)"),
            cls="card",
        ),
        wa_btn,
        Button("Fazer novo agendamento",
               hx_get=f"/{slug}", hx_target="body", hx_swap="innerHTML",
               cls="btn-back", style="display:block;margin-top:1rem"),
    )

# ── Routes ────────────────────────────────────────────────────────────────────

@rt("/{slug}")
def get(slug: str, session):
    session.clear()
    shop = _load_shop(slug)
    if not shop:
        return Title("Não encontrado"), P("Barbearia não encontrada ou inativa.")
    services = _load_services(shop["id"])
    return Title(f"Agendamento — {shop['name']}"), *_full_page(
        shop, slug, "service", *_step_service(slug, services)
    )


@rt("/{slug}/service", methods=["POST"])
def post_service(slug: str, session, svc_id: str):
    shop = _load_shop(slug)
    services = _load_services(shop["id"])
    svc = next((s for s in services if s["id"] == svc_id), None)
    if not svc:
        return _wizard(slug, "service", P("Serviço não encontrado.", cls="error-msg"))
    session["service_id"] = svc_id
    barbers = _load_barbers(shop["id"])
    return _wizard(slug, "barber", *_step_barber(slug, barbers))


@rt("/{slug}/barber", methods=["POST"])
def post_barber(slug: str, session, barber_id: str):
    shop = _load_shop(slug)
    barbers = _load_barbers(shop["id"])
    barber = next((b for b in barbers if b["id"] == barber_id), None)
    if not barber:
        return _wizard(slug, "barber", P("Profissional não encontrado.", cls="error-msg"))
    session["barber_id"] = barber_id
    services = _load_services(shop["id"])
    svc = next((s for s in services if s["id"] == session.get("service_id")), None)
    return _wizard(slug, "datetime", *_step_datetime(slug, svc, barber))


@rt("/{slug}/datetime", methods=["POST"])
def post_datetime(slug: str, session, date_str: str):
    shop = _load_shop(slug)
    services = _load_services(shop["id"])
    barbers = _load_barbers(shop["id"])
    svc = next((s for s in services if s["id"] == session.get("service_id")), None)
    barber = next((b for b in barbers if b["id"] == session.get("barber_id")), None)
    if not svc or not barber:
        return _wizard(slug, "datetime", P("Sessão expirada. Recarregue a página.", cls="error-msg"))
    session["date_str"] = date_str
    slots = get_available_slots(
        barber_id=barber["id"],
        service_id=svc["id"],
        duration_min=svc["duration_min"],
        date_str=date_str,
    )
    return _wizard(slug, "datetime", *_step_datetime(slug, svc, barber, date_str=date_str, slots=slots))


@rt("/{slug}/slot", methods=["POST"])
def post_slot(slug: str, session, starts_at: str, ends_at: str, slot_time: str):
    shop = _load_shop(slug)
    services = _load_services(shop["id"])
    barbers = _load_barbers(shop["id"])
    svc = next((s for s in services if s["id"] == session.get("service_id")), None)
    barber = next((b for b in barbers if b["id"] == session.get("barber_id")), None)
    session.update({"slot_starts_at": starts_at, "slot_ends_at": ends_at, "slot_time": slot_time})
    slot = {"starts_at": starts_at, "ends_at": ends_at, "time": slot_time}
    return _wizard(slug, "form", *_step_form(slug, svc, barber, session["date_str"], slot))


@rt("/{slug}/booking", methods=["POST"])
async def post_booking(slug: str, session, request: Request,
                       name: str = "", phone: str = "", email: str = "", notes: str = ""):
    shop = _load_shop(slug)
    services = _load_services(shop["id"])
    barbers = _load_barbers(shop["id"])
    svc = next((s for s in services if s["id"] == session.get("service_id")), None)
    barber = next((b for b in barbers if b["id"] == session.get("barber_id")), None)
    slot = {
        "starts_at": session.get("slot_starts_at"),
        "ends_at": session.get("slot_ends_at"),
        "time": session.get("slot_time"),
    }
    date_str = session.get("date_str", "")

    errors = []
    if len(name.strip()) < 2:
        errors.append("Nome deve ter pelo menos 2 caracteres.")
    digits = "".join(c for c in phone if c.isdigit())
    if not (10 <= len(digits) <= 11):
        errors.append("Telefone inválido (DDD + 8 ou 9 dígitos).")
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        errors.append("E-mail inválido.")

    if errors:
        return _wizard(slug, "form", *_step_form(slug, svc, barber, date_str, slot, errors=errors))

    try:
        get_supabase_admin().table("appointments").insert({
            "barbershop_id": shop["id"],
            "barber_id": barber["id"],
            "service_id": svc["id"],
            "starts_at": slot["starts_at"],
            "ends_at": slot["ends_at"],
            "client_name": name.strip(),
            "client_phone": digits,
            "client_email": email or None,
            "notes": notes or None,
            "price_cents": svc["price_cents"],
            "status": "confirmed",
        }).execute()
    except Exception as exc:
        if "APPOINTMENT_OVERLAP" in str(exc):
            msg = "Este horário não está mais disponível. Escolha outro."
        else:
            msg = "Erro ao criar agendamento. Tente novamente."
        return _wizard(slug, "form", *_step_form(slug, svc, barber, date_str, slot, errors=[msg]))

    _notify_telegram(name.strip(), digits, svc, barber, date_str, slot)
    session.clear()
    return _wizard(slug, "success", *_step_success(slug, shop, svc, barber, date_str, slot))


@rt("/{slug}/back/{to_step}")
def back(slug: str, session, to_step: str):
    shop = _load_shop(slug)
    services = _load_services(shop["id"])
    barbers = _load_barbers(shop["id"])
    svc = next((s for s in services if s["id"] == session.get("service_id")), None)
    barber = next((b for b in barbers if b["id"] == session.get("barber_id")), None)

    if to_step == "service":
        return _wizard(slug, "service", *_step_service(slug, services))
    if to_step == "barber":
        return _wizard(slug, "barber", *_step_barber(slug, barbers))
    if to_step == "datetime":
        return _wizard(slug, "datetime",
                       *_step_datetime(slug, svc, barber, date_str=session.get("date_str", "")))
    return _wizard(slug, "service", *_step_service(slug, services))

# ── Entry point ───────────────────────────────────────────────────────────────

serve(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
