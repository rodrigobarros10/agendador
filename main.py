import os
import time
import uuid
import urllib.parse
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from fasthtml.common import *
from starlette.responses import RedirectResponse

from lib.availability import get_available_slots
from lib.google_calendar import auth_url, exchange_code, create_event
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
    background: #0d0d0d;
    color: #e8e8e8;
    min-height: 100vh;
}
.container {
    max-width: 560px;
    margin: 0 auto;
    padding: 1.25rem 1rem;
}
h1 { font-size: 1.4rem; font-weight: 700; }
h2 { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; }
.meta { color: #888; font-size: 0.875rem; }
.divider { border: none; border-top: 1px solid #2a2a2a; margin: 1rem 0; }

/* Cards */
.card {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 0.75rem;
}

/* Option buttons (service / barber selection) */
.opt-btn {
    display: block;
    width: 100%;
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 0.875rem 1rem;
    text-align: left;
    cursor: pointer;
    font-size: 0.95rem;
    color: #e8e8e8;
    margin-bottom: 0.5rem;
    transition: border-color 0.15s, background 0.15s;
}
.opt-btn:hover { border-color: #555; background: #222; }

/* Primary action button */
.btn-primary {
    display: block;
    width: 100%;
    background: #e8e8e8;
    color: #0d0d0d;
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
.btn-primary:hover { background: #ccc; }

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
.btn-back:hover { color: #e8e8e8; }

/* Time slots grid */
.slots-grid { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem; }
.slot-form { display: contents; }
.slot-btn {
    padding: 0.5rem 0.875rem;
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.9rem;
    color: #e8e8e8;
    transition: border-color 0.15s, background 0.15s;
}
.slot-btn:hover { border-color: #555; background: #222; }

/* Form inputs */
.field { margin-bottom: 0.875rem; }
.field label { display: block; font-size: 0.875rem; font-weight: 500; margin-bottom: 0.3rem; color: #aaa; }
.field input, .field textarea {
    width: 100%;
    padding: 0.6rem 0.75rem;
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    font-size: 0.95rem;
    font-family: inherit;
    color: #e8e8e8;
    transition: border-color 0.15s;
}
.field input:focus, .field textarea:focus {
    outline: none;
    border-color: #555;
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
    background: #1a1a1a;
    color: #555;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.prog-step.done { background: #1a2e1a; color: #4caf50; }
.prog-step.active { background: #e8e8e8; color: #0d0d0d; font-weight: 600; }

/* Error */
.error-msg {
    background: #2a1010;
    border: 1px solid #5a2020;
    border-radius: 8px;
    padding: 0.625rem 0.875rem;
    color: #ff6b6b;
    font-size: 0.875rem;
    margin-bottom: 0.75rem;
}

/* Success */
.success-box {
    background: #0f2a0f;
    border: 1px solid #1e5c1e;
    border-radius: 12px;
    padding: 1.5rem;
    text-align: center;
    margin-bottom: 1rem;
}
.success-box h2 { color: #4caf50; margin-bottom: 0; }

/* Date input */
input[type="date"] {
    width: 100%;
    padding: 0.6rem 0.75rem;
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    font-size: 0.95rem;
    color: #e8e8e8;
    color-scheme: dark;
    margin-bottom: 0.75rem;
}
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _redirect_uri() -> str:
    base = os.environ.get("APP_URL", "http://localhost:8000")
    return f"{base}/auth/callback"


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

def _step_login(slug: str):
    return (
        Div(
            H2("Entre com sua conta Google"),
            P("Para agendar, faça login com o Google. Ao confirmar o agendamento, "
              "o evento será salvo automaticamente na sua agenda.", cls="meta",
              style="margin-bottom:1.25rem"),
            A(
                "🔑 Entrar com Google",
                href=f"/{slug}/auth/google",
                cls="btn-primary",
                style="margin-top:0",
            ),
        ),
    )

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
    shop = _load_shop(slug)
    if not shop:
        return Title("Não encontrado"), P("Barbearia não encontrada ou inativa.")

    if not session.get("google_refresh_token"):
        session.clear()
        session["pending_slug"] = slug
        return Title(f"Agendamento — {shop['name']}"), *_full_page(
            shop, slug, "service", *_step_login(slug)
        )

    services = _load_services(shop["id"])
    return Title(f"Agendamento — {shop['name']}"), *_full_page(
        shop, slug, "service", *_step_service(slug, services)
    )


@rt("/{slug}/auth/google")
def google_login(slug: str, session):
    nonce = uuid.uuid4().hex
    session["oauth_nonce"] = nonce
    session["pending_slug"] = slug
    state = f"client:{slug}:{nonce}"
    return RedirectResponse(auth_url(_redirect_uri(), state), status_code=302)


@rt("/auth/callback")
def oauth_callback(session, code: str = "", state: str = "", error: str = ""):
    if error or not code:
        slug = session.get("pending_slug", "")
        return RedirectResponse(f"/{slug}", status_code=302)

    parts = state.split(":", 2)
    kind = parts[0] if parts else ""

    access_token, refresh_token = exchange_code(code, _redirect_uri())

    if kind == "client":
        slug = parts[1] if len(parts) > 1 else session.get("pending_slug", "")
        if refresh_token:
            session["google_refresh_token"] = refresh_token
        elif access_token:
            session["google_access_token"] = access_token
        return RedirectResponse(f"/{slug}", status_code=302)

    if kind == "admin":
        if access_token:
            import urllib.request, json as _json
            req = urllib.request.Request(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            with urllib.request.urlopen(req) as resp:
                info = _json.loads(resp.read())
            email = info.get("email", "")
            if email == ADMIN_EMAIL:
                session["admin_email"] = email
        return RedirectResponse("/admin", status_code=302)

    if kind == "barber":
        barber_id = parts[1] if len(parts) > 1 else ""
        if refresh_token and barber_id:
            get_supabase_admin().table("barbers").update(
                {"google_refresh_token": refresh_token}
            ).eq("id", barber_id).execute()
        return Title("Google Calendar conectado"), Style(CSS), Div(
            Div(
                H2("✅ Google Calendar conectado!"),
                cls="success-box",
            ),
            P("O Google Calendar do barbeiro foi vinculado com sucesso. "
              "Pode fechar esta janela.", cls="meta", style="margin-top:1rem"),
            cls="container",
        )

    return RedirectResponse("/", status_code=302)


@rt("/barber/{barber_id}/connect-google")
def barber_connect(barber_id: str, session):
    nonce = uuid.uuid4().hex
    session["oauth_nonce"] = nonce
    state = f"barber:{barber_id}:{nonce}"
    return RedirectResponse(auth_url(_redirect_uri(), state), status_code=302)


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

    # Google Calendar events
    start_dt = datetime.fromisoformat(slot["starts_at"])
    end_dt = datetime.fromisoformat(slot["ends_at"])
    event_summary = f"{svc['name']} — {barber['name']}"
    event_description = (
        f"Serviço: {svc['name']} ({svc['duration_min']} min)\n"
        f"Profissional: {barber['name']}\n"
        f"Valor: {format_currency(svc['price_cents'])}\n"
        f"Local: {shop['name']}"
    )

    client_token = session.get("google_refresh_token")
    if client_token:
        create_event(client_token, event_summary, event_description, start_dt, end_dt)

    barber_token = barber.get("google_refresh_token")
    if barber_token:
        barber_event_description = (
            f"Cliente: {name.strip()}\n"
            f"Telefone: {format_phone(digits)}\n"
            f"Serviço: {svc['name']} ({svc['duration_min']} min)\n"
            f"Valor: {format_currency(svc['price_cents'])}"
        )
        create_event(barber_token, f"{svc['name']} — {name.strip()}",
                     barber_event_description, start_dt, end_dt)

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

# ── Admin ─────────────────────────────────────────────────────────────────────

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

ADMIN_CSS = CSS + """
.admin-container { max-width: 900px; margin: 0 auto; padding: 1.25rem 1rem; }
.admin-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.75rem; margin-bottom: 1.5rem; }
.stat-card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px; padding: 1rem; text-align: center; }
.stat-card .value { font-size: 1.75rem; font-weight: 700; display: block; }
.stat-card .label { font-size: 0.75rem; color: #888; margin-top: 0.2rem; }
.stat-active .value { color: #4caf50; }
.stat-trial .value { color: #ff9800; }
.stat-overdue .value { color: #f44336; }
.stat-revenue .value { color: #e8e8e8; }
table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
th { text-align: left; padding: 0.5rem 0.75rem; color: #888; font-weight: 500; border-bottom: 1px solid #2a2a2a; }
td { padding: 0.625rem 0.75rem; border-bottom: 1px solid #1e1e1e; vertical-align: middle; }
tr:hover td { background: #161616; }
.badge { display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.badge-active { background: #1a3a1a; color: #4caf50; }
.badge-trial { background: #2a2000; color: #ff9800; }
.badge-overdue { background: #2a1010; color: #f44336; }
.badge-cancelled { background: #1e1e1e; color: #666; }
.btn-sm { padding: 0.3rem 0.75rem; font-size: 0.8rem; border-radius: 6px; border: 1px solid #2a2a2a;
          background: #1a1a1a; color: #e8e8e8; cursor: pointer; text-decoration: none; }
.btn-sm:hover { border-color: #555; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 1rem; }
.section-title { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; color: #666;
                 text-transform: uppercase; margin: 1.25rem 0 0.75rem; }
.nav-link { color: #888; text-decoration: none; font-size: 0.875rem; }
.nav-link:hover { color: #e8e8e8; }
select { width: 100%; padding: 0.6rem 0.75rem; background: #1a1a1a; border: 1px solid #2a2a2a;
         border-radius: 8px; font-size: 0.95rem; color: #e8e8e8; font-family: inherit; }
"""

def _admin_page(*content):
    return (
        Style(ADMIN_CSS),
        Script(src="https://unpkg.com/htmx.org@2.0.4"),
        Div(*content, cls="admin-container"),
    )

def _admin_nav(current: str = ""):
    return Div(
        Span("⚡ SaaS Admin", style="font-weight:700;font-size:1rem"),
        Div(
            A("Dashboard", href="/admin", cls="nav-link", style="margin-right:1rem"),
            A("Barbearias", href="/admin/barbershops", cls="nav-link", style="margin-right:1rem"),
            A("Nova barbearia", href="/admin/barbershops/new", cls="nav-link"),
        ),
        cls="admin-header",
    )

def _is_admin(session) -> bool:
    return bool(ADMIN_EMAIL) and session.get("admin_email") == ADMIN_EMAIL

def _status_badge(status: str):
    labels = {"active": "Ativo", "trial": "Trial", "overdue": "Inadimplente", "cancelled": "Cancelado"}
    return Span(labels.get(status, status), cls=f"badge badge-{status}")


@rt("/admin")
def admin_home(session):
    if not _is_admin(session):
        return Title("Admin"), *_admin_page(
            H1("⚡ SaaS Admin", style="margin-bottom:1rem"),
            A("🔑 Entrar com Google", href="/admin/auth/google", cls="btn-primary", style="max-width:300px;margin-top:0"),
        )

    shops = get_supabase_admin().table("barbershops").select("*").execute().data or []

    total = len(shops)
    active = sum(1 for s in shops if s.get("subscription_status") == "active")
    trial  = sum(1 for s in shops if s.get("subscription_status") == "trial")
    overdue = sum(1 for s in shops if s.get("subscription_status") == "overdue")
    revenue = sum(s.get("monthly_price_cents", 0) for s in shops if s.get("subscription_status") == "active")

    rows = [
        Tr(
            Td(s["name"]),
            Td(Code(s["slug"])),
            Td(s.get("owner_name") or "—"),
            Td(_status_badge(s.get("subscription_status", "trial"))),
            Td(s.get("next_billing_date") or "—"),
            Td(format_currency(s.get("monthly_price_cents") or 0)),
            Td(A("Editar", href=f"/admin/barbershops/{s['id']}", cls="btn-sm")),
        )
        for s in sorted(shops, key=lambda x: x.get("subscription_status", ""))
    ]

    return Title("Admin"), *_admin_page(
        _admin_nav(),
        Div(
            Div(Span(str(total), cls="value"), Span("Total", cls="label"), cls="stat-card"),
            Div(Span(str(active), cls="value"), Span("Ativas", cls="label"), cls="stat-card stat-active"),
            Div(Span(str(trial), cls="value"), Span("Trial", cls="label"), cls="stat-card stat-trial"),
            Div(Span(str(overdue), cls="value"), Span("Inadimplentes", cls="label"), cls="stat-card stat-overdue"),
            Div(Span(format_currency(revenue), cls="value"), Span("Receita mensal", cls="label"), cls="stat-card stat-revenue"),
            cls="stats-grid",
        ),
        Div(
            Div(
                Span("Barbearias", style="font-weight:600"),
                A("+ Nova", href="/admin/barbershops/new", cls="btn-sm"),
                cls="admin-header", style="margin-bottom:0.75rem",
            ),
            Div(
                Table(
                    Thead(Tr(Th("Nome"), Th("Slug"), Th("Dono"), Th("Status"), Th("Próx. cobrança"), Th("Plano"), Th(""))),
                    Tbody(*rows),
                ),
                style="overflow-x:auto",
            ),
            cls="card",
        ),
    )


@rt("/admin/auth/google")
def admin_google_auth(session):
    nonce = uuid.uuid4().hex
    session["oauth_nonce"] = nonce
    state = f"admin::{nonce}"
    return RedirectResponse(auth_url(_redirect_uri(), state), status_code=302)


@rt("/admin/barbershops/new")
def admin_new_shop(session):
    if not _is_admin(session):
        return RedirectResponse("/admin", status_code=302)

    return Title("Nova barbearia"), *_admin_page(
        _admin_nav(),
        H2("Nova barbearia", style="margin-bottom:1.5rem"),
        Form(
            P("Dados da barbearia", cls="section-title"),
            Div(
                Div(Label("Nome *"), Input(name="name", required=True, placeholder="Barbearia do João"), cls="field"),
                Div(Label("Slug * (URL)"), Input(name="slug", required=True, placeholder="barbearia-do-joao"), cls="field"),
                cls="form-grid",
            ),
            Div(Label("Descrição"), Input(name="description", placeholder="Especialistas em cortes modernos"), cls="field"),
            Div(
                Div(Label("Endereço"), Input(name="address", placeholder="Rua das Flores, 123"), cls="field"),
                Div(Label("Cidade"), Input(name="city", placeholder="São Paulo"), cls="field"),
                cls="form-grid",
            ),
            Div(Label("Telefone da barbearia"), Input(name="phone", placeholder="(11) 99999-9999"), cls="field"),

            P("Dados do dono", cls="section-title"),
            Div(
                Div(Label("Nome do dono"), Input(name="owner_name", placeholder="João Silva"), cls="field"),
                Div(Label("E-mail do dono"), Input(name="owner_email", type="email", placeholder="joao@email.com"), cls="field"),
                cls="form-grid",
            ),
            Div(Label("WhatsApp do dono"), Input(name="owner_phone", placeholder="(11) 99999-9999"), cls="field"),

            P("Assinatura", cls="section-title"),
            Div(
                Div(
                    Label("Status"),
                    Select(
                        Option("Trial", value="trial", selected=True),
                        Option("Ativo", value="active"),
                        Option("Inadimplente", value="overdue"),
                        Option("Cancelado", value="cancelled"),
                        name="subscription_status",
                    ),
                    cls="field",
                ),
                Div(Label("Valor mensal (R$)"), Input(name="monthly_price", type="number", value="99", step="0.01"), cls="field"),
                cls="form-grid",
            ),
            Div(Label("Próxima cobrança"), Input(name="next_billing_date", type="date"), cls="field"),

            Button("Criar barbearia", type="submit", cls="btn-primary"),
            A("Cancelar", href="/admin", cls="btn-back", style="display:inline-block;margin-left:1rem"),
            action="/admin/barbershops/new",
            method="post",
        ),
    )


@rt("/admin/barbershops/new", methods=["POST"])
async def admin_create_shop(session, request: Request,
                            name: str = "", slug: str = "", description: str = "",
                            address: str = "", city: str = "", phone: str = "",
                            owner_name: str = "", owner_email: str = "", owner_phone: str = "",
                            subscription_status: str = "trial", monthly_price: str = "99",
                            next_billing_date: str = ""):
    if not _is_admin(session):
        return RedirectResponse("/admin", status_code=302)

    try:
        price_cents = int(float(monthly_price) * 100)
    except ValueError:
        price_cents = 9900

    get_supabase_admin().table("barbershops").insert({
        "name": name.strip(),
        "slug": slug.strip().lower(),
        "description": description or None,
        "address": address or None,
        "city": city or None,
        "phone": phone or None,
        "owner_name": owner_name or None,
        "owner_email": owner_email or None,
        "owner_phone": owner_phone or None,
        "subscription_status": subscription_status,
        "monthly_price_cents": price_cents,
        "next_billing_date": next_billing_date or None,
        "is_active": subscription_status in ("active", "trial"),
    }).execute()

    return RedirectResponse("/admin/barbershops", status_code=302)


@rt("/admin/barbershops")
def admin_list_shops(session):
    if not _is_admin(session):
        return RedirectResponse("/admin", status_code=302)
    return RedirectResponse("/admin", status_code=302)


@rt("/admin/barbershops/{shop_id}")
def admin_edit_shop(shop_id: str, session):
    if not _is_admin(session):
        return RedirectResponse("/admin", status_code=302)

    res = get_supabase_admin().table("barbershops").select("*").eq("id", shop_id).limit(1).execute()
    if not res.data:
        return RedirectResponse("/admin", status_code=302)
    s = res.data[0]

    price_str = f"{(s.get('monthly_price_cents') or 9900) / 100:.2f}"

    return Title(f"Editar — {s['name']}"), *_admin_page(
        _admin_nav(),
        H2(f"Editar: {s['name']}", style="margin-bottom:1.5rem"),
        Form(
            P("Dados da barbearia", cls="section-title"),
            Div(
                Div(Label("Nome *"), Input(name="name", value=s["name"], required=True), cls="field"),
                Div(Label("Slug *"), Input(name="slug", value=s["slug"], required=True), cls="field"),
                cls="form-grid",
            ),
            Div(Label("Descrição"), Input(name="description", value=s.get("description") or ""), cls="field"),
            Div(
                Div(Label("Endereço"), Input(name="address", value=s.get("address") or ""), cls="field"),
                Div(Label("Cidade"), Input(name="city", value=s.get("city") or ""), cls="field"),
                cls="form-grid",
            ),
            Div(Label("Telefone"), Input(name="phone", value=s.get("phone") or ""), cls="field"),

            P("Dados do dono", cls="section-title"),
            Div(
                Div(Label("Nome do dono"), Input(name="owner_name", value=s.get("owner_name") or ""), cls="field"),
                Div(Label("E-mail"), Input(name="owner_email", type="email", value=s.get("owner_email") or ""), cls="field"),
                cls="form-grid",
            ),
            Div(Label("WhatsApp"), Input(name="owner_phone", value=s.get("owner_phone") or ""), cls="field"),

            P("Assinatura", cls="section-title"),
            Div(
                Div(
                    Label("Status"),
                    Select(
                        Option("Trial", value="trial", selected=s.get("subscription_status") == "trial"),
                        Option("Ativo", value="active", selected=s.get("subscription_status") == "active"),
                        Option("Inadimplente", value="overdue", selected=s.get("subscription_status") == "overdue"),
                        Option("Cancelado", value="cancelled", selected=s.get("subscription_status") == "cancelled"),
                        name="subscription_status",
                    ),
                    cls="field",
                ),
                Div(Label("Valor mensal (R$)"), Input(name="monthly_price", type="number", value=price_str, step="0.01"), cls="field"),
                cls="form-grid",
            ),
            Div(Label("Próxima cobrança"), Input(name="next_billing_date", type="date", value=s.get("next_billing_date") or ""), cls="field"),

            Button("Salvar alterações", type="submit", cls="btn-primary"),
            A("Cancelar", href="/admin", cls="btn-back", style="display:inline-block;margin-left:1rem"),
            action=f"/admin/barbershops/{shop_id}",
            method="post",
        ),
    )


@rt("/admin/barbershops/{shop_id}", methods=["POST"])
async def admin_update_shop(shop_id: str, session, request: Request,
                            name: str = "", slug: str = "", description: str = "",
                            address: str = "", city: str = "", phone: str = "",
                            owner_name: str = "", owner_email: str = "", owner_phone: str = "",
                            subscription_status: str = "trial", monthly_price: str = "99",
                            next_billing_date: str = ""):
    if not _is_admin(session):
        return RedirectResponse("/admin", status_code=302)

    try:
        price_cents = int(float(monthly_price) * 100)
    except ValueError:
        price_cents = 9900

    get_supabase_admin().table("barbershops").update({
        "name": name.strip(),
        "slug": slug.strip().lower(),
        "description": description or None,
        "address": address or None,
        "city": city or None,
        "phone": phone or None,
        "owner_name": owner_name or None,
        "owner_email": owner_email or None,
        "owner_phone": owner_phone or None,
        "subscription_status": subscription_status,
        "monthly_price_cents": price_cents,
        "next_billing_date": next_billing_date or None,
        "is_active": subscription_status in ("active", "trial"),
    }).eq("id", shop_id).execute()

    return RedirectResponse("/admin", status_code=302)

# ── Entry point ───────────────────────────────────────────────────────────────

serve(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
