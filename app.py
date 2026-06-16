import urllib.parse
from datetime import date, timedelta

import streamlit as st

from lib.availability import get_available_slots
from lib.supabase_client import get_supabase
from lib.telegram import send_telegram
from lib.utils import format_currency, format_date_ptbr, format_phone, mask_phone

st.set_page_config(
    page_title="Agendamento",
    page_icon="✂️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Session state ──────────────────────────────────────────────────────────────

def _init_state() -> None:
    defaults = {
        "step": "service",
        "service": None,
        "barber": None,
        "date": None,
        "slot": None,
        "appointment_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

_init_state()

def _notify_telegram(client_name, phone_digits, svc, barber, date_str, slot) -> None:
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = barber.get("telegram_chat_id", "")
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
    except Exception:
        pass


def _reset() -> None:
    for key in ["step", "service", "barber", "date", "slot", "appointment_id"]:
        st.session_state.pop(key, None)
    _init_state()

def _go(step: str) -> None:
    st.session_state.step = step
    st.rerun()

# ── Data loaders ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def _load_shop(slug: str) -> dict | None:
    res = (
        get_supabase()
        .table("barbershops")
        .select("*")
        .eq("slug", slug)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None

@st.cache_data(ttl=60, show_spinner=False)
def _load_barbers(barbershop_id: str) -> list[dict]:
    res = (
        get_supabase()
        .table("barbers")
        .select("*")
        .eq("barbershop_id", barbershop_id)
        .eq("is_active", True)
        .execute()
    )
    return res.data or []

@st.cache_data(ttl=60, show_spinner=False)
def _load_services(barbershop_id: str) -> list[dict]:
    res = (
        get_supabase()
        .table("services")
        .select("*")
        .eq("barbershop_id", barbershop_id)
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    return res.data or []

# ── Slug from URL ──────────────────────────────────────────────────────────────

slug = st.query_params.get("shop", "").strip()
if not slug:
    st.warning("Informe o slug da barbearia na URL: `?shop=nome-da-barbearia`")
    st.stop()

# ── Load shop ──────────────────────────────────────────────────────────────────

with st.spinner("Carregando..."):
    shop = _load_shop(slug)

if not shop:
    st.error("Barbearia não encontrada ou inativa.")
    st.stop()

barbers = _load_barbers(shop["id"])
services = _load_services(shop["id"])

# ── Header ─────────────────────────────────────────────────────────────────────

st.title(f"✂️ {shop['name']}")
if shop.get("description"):
    st.caption(shop["description"])

info_parts = []
if shop.get("address"):
    info_parts.append(f"📍 {shop['address']}{', ' + shop['city'] if shop.get('city') else ''}")
if shop.get("phone"):
    info_parts.append(f"📞 {mask_phone(shop['phone'])}")
if info_parts:
    st.caption("  ·  ".join(info_parts))

st.divider()

# ── Progress indicator ─────────────────────────────────────────────────────────

STEPS = ["service", "barber", "datetime", "form", "success"]
STEP_LABELS = ["Serviço", "Profissional", "Horário", "Dados", "✅ Pronto"]

if st.session_state.step != "success":
    current_idx = STEPS.index(st.session_state.step)
    cols = st.columns(4)
    for i, (label, col) in enumerate(zip(STEP_LABELS[:4], cols)):
        with col:
            if i < current_idx:
                st.markdown(f"<small>✔ {label}</small>", unsafe_allow_html=True)
            elif i == current_idx:
                st.markdown(f"**{label}**")
            else:
                st.markdown(f"<small style='color:#aaa'>{label}</small>", unsafe_allow_html=True)
    st.divider()

# ── Step: service ──────────────────────────────────────────────────────────────

if st.session_state.step == "service":
    st.subheader("Escolha o serviço")

    if not services:
        st.info("Nenhum serviço disponível no momento.")
    else:
        for svc in services:
            price = format_currency(svc["price_cents"])
            label = f"**{svc['name']}** — {price} · {svc['duration_min']} min"
            if svc.get("description"):
                label += f"  \n{svc['description']}"
            if st.button(label, key=f"svc_{svc['id']}", use_container_width=True):
                st.session_state.service = svc
                st.session_state.barber = None
                st.session_state.date = None
                st.session_state.slot = None
                _go("barber")

# ── Step: barber ───────────────────────────────────────────────────────────────

elif st.session_state.step == "barber":
    st.subheader("Escolha o profissional")

    if not barbers:
        st.info("Nenhum profissional disponível no momento.")
    else:
        for barber in barbers:
            label = f"**{barber['name']}**"
            if barber.get("bio"):
                label += f"  \n{barber['bio']}"
            if st.button(label, key=f"barber_{barber['id']}", use_container_width=True):
                st.session_state.barber = barber
                st.session_state.date = None
                st.session_state.slot = None
                _go("datetime")

    if st.button("← Voltar"):
        _go("service")

# ── Step: datetime ─────────────────────────────────────────────────────────────

elif st.session_state.step == "datetime":
    svc = st.session_state.service
    barber = st.session_state.barber

    st.subheader("Escolha a data e horário")
    st.caption(f"{svc['name']} · {svc['duration_min']} min · com **{barber['name']}**")

    today = date.today()
    initial_date = (
        date.fromisoformat(st.session_state.date)
        if st.session_state.date
        else today
    )

    chosen_date = st.date_input(
        "Data",
        value=initial_date,
        min_value=today,
        max_value=today + timedelta(days=29),
        format="DD/MM/YYYY",
    )

    with st.spinner("Buscando horários..."):
        slots = get_available_slots(
            barber_id=barber["id"],
            service_id=svc["id"],
            duration_min=svc["duration_min"],
            date_str=chosen_date.isoformat(),
        )

    if not slots:
        st.info("Nenhum horário disponível neste dia. Tente outra data.")
    else:
        slot_times = [s["time"] for s in slots]
        slot_map = {s["time"]: s for s in slots}

        chosen_time = st.radio(
            "Horário disponível",
            slot_times,
            horizontal=True,
            index=0,
        )

        st.write("")
        if st.button("Confirmar horário →", type="primary", use_container_width=True):
            st.session_state.date = chosen_date.isoformat()
            st.session_state.slot = slot_map[chosen_time]
            _go("form")

    if st.button("← Voltar"):
        _go("barber")

# ── Step: form ─────────────────────────────────────────────────────────────────

elif st.session_state.step == "form":
    svc = st.session_state.service
    barber = st.session_state.barber
    slot = st.session_state.slot
    date_str = st.session_state.date

    st.subheader("Seus dados")

    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        col1.markdown(f"**{svc['name']}**  \n{barber['name']} · {format_date_ptbr(date_str)} às {slot['time']}")
        col2.markdown(f"**{format_currency(svc['price_cents'])}**")

    with st.form("booking_form", border=False):
        name = st.text_input("Nome completo *", placeholder="Seu nome")
        phone_raw = st.text_input("WhatsApp *", placeholder="(11) 99999-9999", max_chars=15)
        email = st.text_input("E-mail (opcional)", placeholder="seuemail@exemplo.com")
        notes = st.text_area("Observações (opcional)", max_chars=500, height=80)

        col_back, col_submit = st.columns([1, 3])
        submitted = col_submit.form_submit_button(
            "Confirmar agendamento", type="primary", use_container_width=True
        )
        back = col_back.form_submit_button("← Voltar", use_container_width=True)

    if back:
        _go("datetime")

    if submitted:
        errors = []
        if len(name.strip()) < 2:
            errors.append("Nome deve ter pelo menos 2 caracteres.")
        digits = "".join(c for c in phone_raw if c.isdigit())
        if not (10 <= len(digits) <= 11):
            errors.append("Telefone inválido (DDD + 8 ou 9 dígitos).")
        if email and ("@" not in email or "." not in email.split("@")[-1]):
            errors.append("E-mail inválido.")

        if errors:
            for msg in errors:
                st.error(msg)
        else:
            try:
                res = (
                    get_supabase()
                    .table("appointments")
                    .insert({
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
                    })
                    .execute()
                )
                st.session_state.appointment_id = res.data[0]["id"]
                _notify_telegram(name.strip(), digits, svc, barber, date_str, slot)
                _go("success")
            except Exception as exc:
                if "APPOINTMENT_OVERLAP" in str(exc):
                    st.error("Este horário não está mais disponível. Escolha outro.")
                else:
                    st.error("Erro ao criar agendamento. Tente novamente.")

# ── Step: success ──────────────────────────────────────────────────────────────

elif st.session_state.step == "success":
    svc = st.session_state.service
    barber = st.session_state.barber
    slot = st.session_state.slot
    date_str = st.session_state.date

    st.success("Agendamento confirmado com sucesso!")

    with st.container(border=True):
        st.markdown("### Resumo")
        st.markdown(f"**Serviço:** {svc['name']} — {format_currency(svc['price_cents'])}")
        st.markdown(f"**Profissional:** {barber['name']}")
        st.markdown(f"**Data:** {format_date_ptbr(date_str).capitalize()}")
        st.markdown(f"**Horário:** {slot['time']} ({svc['duration_min']} min)")

    if shop.get("phone"):
        phone_digits = "".join(c for c in shop["phone"] if c.isdigit())
        wa_text = (
            f"Olá! Confirmo meu agendamento na {shop['name']}:\n"
            f"Serviço: {svc['name']}\n"
            f"Profissional: {barber['name']}\n"
            f"Data: {format_date_ptbr(date_str)} às {slot['time']}"
        )
        wa_url = f"https://wa.me/{phone_digits}?text={urllib.parse.quote(wa_text)}"
        st.link_button("💬 Confirmar via WhatsApp", wa_url, use_container_width=True)

    st.write("")
    if st.button("Fazer novo agendamento", use_container_width=True):
        _reset()
        st.rerun()
