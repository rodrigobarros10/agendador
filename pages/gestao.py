import urllib.parse
from datetime import date, datetime, timedelta

import streamlit as st
from supabase import create_client

from lib.telegram import send_telegram
from lib.utils import format_currency, format_date_ptbr, format_phone

st.set_page_config(
    page_title="Gestão – Agendador",
    page_icon="✂️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DAYS_EN = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAYS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

STATUS_LABELS: dict[str, str] = {
    "pending": "⏳ Pendente",
    "confirmed": "✅ Confirmado",
    "cancelled": "❌ Cancelado",
    "completed": "🏁 Concluído",
    "no_show": "👻 Não veio",
}

# ── Supabase client (separado do público) ─────────────────────────────────────

@st.cache_resource
def _mgmt_client():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])


def _sb():
    c = _mgmt_client()
    if token := st.session_state.get("mgmt_token"):
        c.postgrest.auth(token)
    return c

# ── Auth ───────────────────────────────────────────────────────────────────────

def _login(email: str, password: str) -> bool:
    try:
        res = _mgmt_client().auth.sign_in_with_password({"email": email, "password": password})
        if res.session:
            st.session_state.mgmt_token = res.session.access_token
            st.session_state.mgmt_user_id = res.user.id
            return True
    except Exception:
        pass
    return False


def _logout() -> None:
    try:
        _mgmt_client().auth.sign_out()
    except Exception:
        pass
    st.session_state.pop("mgmt_token", None)
    st.session_state.pop("mgmt_user_id", None)

# ── Login gate ─────────────────────────────────────────────────────────────────

if "mgmt_token" not in st.session_state:
    st.title("✂️ Gestão da Barbearia")
    with st.form("login_form"):
        email_in = st.text_input("E-mail")
        pwd_in = st.text_input("Senha", type="password")
        login_btn = st.form_submit_button("Entrar", type="primary", use_container_width=True)
    if login_btn:
        if _login(email_in, pwd_in):
            st.rerun()
        else:
            st.error("E-mail ou senha incorretos.")
    st.stop()

# ── Data loaders ───────────────────────────────────────────────────────────────

def _load_shop() -> dict | None:
    res = _sb().table("barbershops").select("*").eq("owner_id", st.session_state.mgmt_user_id).limit(1).execute()
    return res.data[0] if res.data else None


def _load_barbers(shop_id: str) -> list[dict]:
    res = _sb().table("barbers").select("*").eq("barbershop_id", shop_id).order("name").execute()
    return res.data or []


def _load_services(shop_id: str) -> list[dict]:
    res = _sb().table("services").select("*").eq("barbershop_id", shop_id).order("sort_order").execute()
    return res.data or []


def _load_appointments(
    shop_id: str,
    starts_after: str | None = None,
    starts_before: str | None = None,
) -> list[dict]:
    q = (
        _sb()
        .table("appointments")
        .select("*, barbers(name), services(name, duration_min)")
        .eq("barbershop_id", shop_id)
        .order("starts_at", desc=True)
    )
    if starts_after:
        q = q.gte("starts_at", starts_after)
    if starts_before:
        q = q.lte("starts_at", starts_before)
    return q.execute().data or []


def _load_working_hours(barber_id: str) -> dict[str, dict]:
    res = _sb().table("working_hours").select("*").eq("barber_id", barber_id).execute()
    return {row["day_of_week"]: row for row in (res.data or [])}


def _load_time_off(barber_ids: list[str]) -> list[dict]:
    if not barber_ids:
        return []
    res = (
        _sb()
        .table("time_off")
        .select("*, barbers(name)")
        .in_("barber_id", barber_ids)
        .gte("end_at", datetime.now().isoformat())
        .order("start_at")
        .execute()
    )
    return res.data or []

# ── Load shop ──────────────────────────────────────────────────────────────────

shop = _load_shop()
if not shop:
    st.error("Nenhuma barbearia vinculada a esta conta.")
    if st.button("Sair"):
        _logout()
        st.rerun()
    st.stop()

barbers = _load_barbers(shop["id"])
services = _load_services(shop["id"])
barber_ids = [b["id"] for b in barbers]

# ── Header e métricas ─────────────────────────────────────────────────────────

col_title, col_logout = st.columns([6, 1])
col_title.title(f"✂️ {shop['name']}")
if col_logout.button("Sair", use_container_width=True):
    _logout()
    st.rerun()

now = datetime.now()
today_str = now.date().isoformat()
week_mon = now.date() - timedelta(days=now.weekday())
week_sun = week_mon + timedelta(days=6)

today_appts = _load_appointments(
    shop["id"],
    starts_after=f"{today_str}T00:00:00",
    starts_before=f"{today_str}T23:59:59",
)
week_appts = _load_appointments(
    shop["id"],
    starts_after=f"{week_mon.isoformat()}T00:00:00",
    starts_before=f"{week_sun.isoformat()}T23:59:59",
)

confirmed_today = [a for a in today_appts if a["status"] not in ("cancelled", "no_show")]
confirmed_week = [a for a in week_appts if a["status"] not in ("cancelled", "no_show")]
revenue_week = sum(a["price_cents"] for a in week_appts if a["status"] == "completed")

m1, m2, m3 = st.columns(3)
m1.metric("Hoje", len(confirmed_today))
m2.metric("Esta semana", len(confirmed_week))
m3.metric("Faturado (semana)", format_currency(revenue_week))

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_agenda, tab_cal, tab_svc, tab_hours, tab_off, tab_cfg = st.tabs([
    "📋 Agendamentos", "📅 Calendário", "✂️ Serviços", "⏰ Horários", "🚫 Folgas", "⚙️ Configurações",
])

# ── Tab: Agendamentos ─────────────────────────────────────────────────────────

with tab_agenda:
    col_f1, col_f2, col_f3 = st.columns(3)

    period = col_f1.selectbox(
        "Período",
        ["Hoje", "Esta semana", "Próximos 30 dias", "Todos"],
        key="ag_period",
    )
    barber_filter = col_f2.selectbox(
        "Profissional",
        ["Todos"] + [b["name"] for b in barbers],
        key="ag_barber",
    )
    status_filter = col_f3.selectbox(
        "Status",
        ["Todos"] + list(STATUS_LABELS.values()),
        key="ag_status",
    )

    if period == "Hoje":
        after = f"{today_str}T00:00:00"
        before = f"{today_str}T23:59:59"
    elif period == "Esta semana":
        after = f"{week_mon.isoformat()}T00:00:00"
        before = f"{week_sun.isoformat()}T23:59:59"
    elif period == "Próximos 30 dias":
        after = now.isoformat()
        before = (now + timedelta(days=30)).isoformat()
    else:
        after = before = None

    appts = _load_appointments(shop["id"], after, before)

    if barber_filter != "Todos":
        target_id = next((b["id"] for b in barbers if b["name"] == barber_filter), None)
        appts = [a for a in appts if a["barber_id"] == target_id]

    if status_filter != "Todos":
        status_key = next((k for k, v in STATUS_LABELS.items() if v == status_filter), None)
        appts = [a for a in appts if a["status"] == status_key]

    st.caption(f"{len(appts)} agendamento(s)")

    if not appts:
        st.info("Nenhum agendamento encontrado.")

    for appt in appts:
        dt = datetime.fromisoformat(appt["starts_at"])
        barber_name = (appt.get("barbers") or {}).get("name", "")
        svc_name = (appt.get("services") or {}).get("name", "")
        status_lbl = STATUS_LABELS.get(appt["status"], appt["status"])

        with st.expander(f"{dt.strftime('%d/%m %H:%M')} · **{appt['client_name']}** · {svc_name} · {barber_name} · {status_lbl}"):
            col_info, col_action = st.columns([3, 2])

            with col_info:
                st.markdown(f"**Cliente:** {appt['client_name']}")
                st.markdown(f"**Telefone:** {format_phone(appt['client_phone'])}")
                if appt.get("client_email"):
                    st.markdown(f"**E-mail:** {appt['client_email']}")
                dur = (appt.get("services") or {}).get("duration_min", "")
                st.markdown(f"**Serviço:** {svc_name}{f' ({dur} min)' if dur else ''}")
                st.markdown(f"**Profissional:** {barber_name}")
                st.markdown(f"**Valor:** {format_currency(appt['price_cents'])}")
                if appt.get("notes"):
                    st.markdown(f"**Obs:** {appt['notes']}")

            with col_action:
                status_keys = list(STATUS_LABELS.keys())
                cur_idx = status_keys.index(appt["status"]) if appt["status"] in status_keys else 0
                new_status = st.selectbox(
                    "Status",
                    status_keys,
                    index=cur_idx,
                    format_func=lambda s: STATUS_LABELS[s],
                    key=f"sel_{appt['id']}",
                )
                if st.button("Atualizar", key=f"upd_{appt['id']}", type="primary", use_container_width=True):
                    _sb().table("appointments").update({"status": new_status}).eq("id", appt["id"]).execute()
                    st.success("Atualizado!")
                    st.rerun()

                digits = appt["client_phone"]
                wa_text = (
                    f"Olá {appt['client_name']}! "
                    f"Confirmando seu agendamento na {shop['name']} "
                    f"em {dt.strftime('%d/%m às %H:%M')}."
                )
                wa_url = f"https://wa.me/55{digits}?text={urllib.parse.quote(wa_text)}"
                st.link_button("💬 WhatsApp", wa_url, use_container_width=True)

# ── Tab: Calendário ───────────────────────────────────────────────────────────

with tab_cal:
    if "cal_offset" not in st.session_state:
        st.session_state.cal_offset = 0

    cal_mon = now.date() - timedelta(days=now.weekday()) + timedelta(weeks=st.session_state.cal_offset)
    cal_sun = cal_mon + timedelta(days=6)

    col_prev, col_range, col_next, col_today = st.columns([1, 5, 1, 1])
    if col_prev.button("◀", key="cal_prev"):
        st.session_state.cal_offset -= 1
        st.rerun()
    col_range.markdown(f"**{cal_mon.strftime('%d/%m/%Y')} – {cal_sun.strftime('%d/%m/%Y')}**")
    if col_next.button("▶", key="cal_next"):
        st.session_state.cal_offset += 1
        st.rerun()
    if col_today.button("Hoje", key="cal_today"):
        st.session_state.cal_offset = 0
        st.rerun()

    cal_appts = _load_appointments(
        shop["id"],
        starts_after=f"{cal_mon.isoformat()}T00:00:00",
        starts_before=f"{cal_sun.isoformat()}T23:59:59",
    )

    by_date: dict[date, list] = {}
    for appt in cal_appts:
        d = datetime.fromisoformat(appt["starts_at"]).date()
        by_date.setdefault(d, []).append(appt)

    for offset in range(7):
        d = cal_mon + timedelta(days=offset)
        day_appts = sorted(
            [a for a in by_date.get(d, []) if a["status"] not in ("cancelled", "no_show")],
            key=lambda a: a["starts_at"],
        )
        today_mark = " ◀ hoje" if d == now.date() else ""
        label = f"**{DAYS_PT[offset]}, {d.strftime('%d/%m')}**{today_mark} — {len(day_appts)} agend."

        with st.expander(label, expanded=(d == now.date())):
            if not day_appts:
                st.caption("Sem agendamentos.")
                continue
            for appt in day_appts:
                dt_s = datetime.fromisoformat(appt["starts_at"])
                dt_e = datetime.fromisoformat(appt["ends_at"])
                barber_name = (appt.get("barbers") or {}).get("name", "")
                svc_name = (appt.get("services") or {}).get("name", "")
                st.markdown(
                    f"🕐 **{dt_s.strftime('%H:%M')}–{dt_e.strftime('%H:%M')}** "
                    f"· {appt['client_name']} · {svc_name} · {barber_name} "
                    f"· {STATUS_LABELS.get(appt['status'], '')}"
                )

# ── Tab: Serviços ─────────────────────────────────────────────────────────────

with tab_svc:
    with st.expander("➕ Novo serviço", expanded=not services):
        with st.form("form_new_svc"):
            n_name = st.text_input("Nome *")
            n_desc = st.text_area("Descrição", height=80)
            c1, c2 = st.columns(2)
            n_price = c1.number_input("Preço (R$) *", min_value=0.0, step=0.5, format="%.2f")
            n_dur = c2.number_input("Duração (min) *", min_value=5, max_value=480, step=5, value=30)
            n_order = c1.number_input("Ordem", min_value=0, value=len(services))
            n_active = c2.checkbox("Ativo", value=True)
            add_svc = st.form_submit_button("Adicionar", type="primary", use_container_width=True)

        if add_svc:
            if not n_name.strip():
                st.error("Nome é obrigatório.")
            else:
                _sb().table("services").insert({
                    "barbershop_id": shop["id"],
                    "name": n_name.strip(),
                    "description": n_desc.strip() or None,
                    "price_cents": int(n_price * 100),
                    "duration_min": int(n_dur),
                    "sort_order": int(n_order),
                    "is_active": n_active,
                }).execute()
                st.success("Serviço adicionado!")
                st.rerun()

    st.divider()

    if not services:
        st.info("Nenhum serviço cadastrado.")

    for svc in services:
        icon = "✅" if svc["is_active"] else "❌"
        with st.expander(f"{icon} {svc['name']} — {format_currency(svc['price_cents'])} · {svc['duration_min']} min"):
            with st.form(f"form_svc_{svc['id']}"):
                e_name = st.text_input("Nome", value=svc["name"])
                e_desc = st.text_area("Descrição", value=svc.get("description") or "", height=80)
                c1, c2 = st.columns(2)
                e_price = c1.number_input("Preço (R$)", value=svc["price_cents"] / 100, min_value=0.0, step=0.5, format="%.2f")
                e_dur = c2.number_input("Duração (min)", value=svc["duration_min"], min_value=5, step=5)
                e_order = c1.number_input("Ordem", value=svc["sort_order"], min_value=0)
                e_active = c2.checkbox("Ativo", value=svc["is_active"])
                c_save, c_del = st.columns([3, 1])
                save_svc = c_save.form_submit_button("Salvar", type="primary", use_container_width=True)
                del_svc = c_del.form_submit_button("Excluir", use_container_width=True)

            if save_svc:
                _sb().table("services").update({
                    "name": e_name.strip(),
                    "description": e_desc.strip() or None,
                    "price_cents": int(e_price * 100),
                    "duration_min": int(e_dur),
                    "sort_order": int(e_order),
                    "is_active": e_active,
                }).eq("id", svc["id"]).execute()
                st.success("Salvo!")
                st.rerun()

            if del_svc:
                _sb().table("services").delete().eq("id", svc["id"]).execute()
                st.rerun()

# ── Tab: Horários ─────────────────────────────────────────────────────────────

with tab_hours:
    if not barbers:
        st.info("Cadastre profissionais primeiro (aba Configurações).")

    for barber in barbers:
        st.subheader(barber["name"])
        wh = _load_working_hours(barber["id"])

        upserts = []
        for i, day_en in enumerate(DAYS_EN):
            existing = wh.get(day_en, {})
            c_day, c_chk, c_start, c_end = st.columns([2, 1, 2, 2])
            c_day.markdown(f"**{DAYS_PT[i]}**")

            active = c_chk.checkbox(
                "ativo", value=existing.get("is_active", False),
                key=f"wh_{barber['id']}_{day_en}",
                label_visibility="collapsed",
            )
            default_start = datetime.strptime(existing.get("start_time", "09:00:00")[:5], "%H:%M").time()
            default_end = datetime.strptime(existing.get("end_time", "18:00:00")[:5], "%H:%M").time()

            start_t = c_start.time_input(
                "início", value=default_start,
                key=f"whs_{barber['id']}_{day_en}",
                label_visibility="collapsed",
                disabled=not active,
            )
            end_t = c_end.time_input(
                "fim", value=default_end,
                key=f"whe_{barber['id']}_{day_en}",
                label_visibility="collapsed",
                disabled=not active,
            )
            upserts.append({
                "barber_id": barber["id"],
                "day_of_week": day_en,
                "start_time": start_t.strftime("%H:%M"),
                "end_time": end_t.strftime("%H:%M"),
                "is_active": active,
            })

        if st.button("Salvar horários", key=f"save_wh_{barber['id']}", type="primary"):
            _sb().table("working_hours").upsert(
                upserts, on_conflict="barber_id,day_of_week"
            ).execute()
            st.success(f"Horários de {barber['name']} salvos!")
            st.rerun()

        st.divider()

# ── Tab: Folgas ───────────────────────────────────────────────────────────────

with tab_off:
    with st.expander("➕ Adicionar folga / bloqueio"):
        if not barbers:
            st.warning("Cadastre profissionais primeiro.")
        else:
            with st.form("form_add_off"):
                barber_opts = {b["name"]: b["id"] for b in barbers}
                sel_b = st.selectbox("Profissional", list(barber_opts.keys()))
                c1, c2 = st.columns(2)
                off_start_d = c1.date_input("Início — data", value=now.date(), key="off_sd")
                off_start_t = c1.time_input("Início — hora", value=datetime.strptime("09:00", "%H:%M").time(), key="off_st")
                off_end_d = c2.date_input("Fim — data", value=now.date(), key="off_ed")
                off_end_t = c2.time_input("Fim — hora", value=datetime.strptime("18:00", "%H:%M").time(), key="off_et")
                off_reason = st.text_input("Motivo (opcional)")
                add_off = st.form_submit_button("Adicionar", type="primary", use_container_width=True)

            if add_off:
                start_dt = datetime.combine(off_start_d, off_start_t)
                end_dt = datetime.combine(off_end_d, off_end_t)
                if end_dt <= start_dt:
                    st.error("A data/hora de fim deve ser após o início.")
                else:
                    _sb().table("time_off").insert({
                        "barber_id": barber_opts[sel_b],
                        "start_at": start_dt.isoformat(),
                        "end_at": end_dt.isoformat(),
                        "reason": off_reason.strip() or None,
                    }).execute()
                    st.success("Bloqueio adicionado!")
                    st.rerun()

    st.divider()

    time_offs = _load_time_off(barber_ids)
    if not time_offs:
        st.info("Nenhum bloqueio futuro.")

    for to in time_offs:
        s = datetime.fromisoformat(to["start_at"])
        e = datetime.fromisoformat(to["end_at"])
        barber_name = (to.get("barbers") or {}).get("name", "")
        reason_txt = f" · {to['reason']}" if to.get("reason") else ""

        c_info, c_del = st.columns([6, 1])
        c_info.markdown(
            f"**{barber_name}** — {s.strftime('%d/%m/%Y %H:%M')} até {e.strftime('%d/%m/%Y %H:%M')}{reason_txt}"
        )
        if c_del.button("🗑️", key=f"del_off_{to['id']}"):
            _sb().table("time_off").delete().eq("id", to["id"]).execute()
            st.rerun()

# ── Tab: Configurações ────────────────────────────────────────────────────────

with tab_cfg:
    # Link de agendamento
    st.subheader("🔗 Link de agendamento")
    st.code(f"http://localhost:8501/?shop={shop['slug']}")
    st.caption("Após deploy, substitua pelo domínio do Streamlit Community Cloud.")

    st.divider()

    # Telegram
    st.subheader("🤖 Telegram Bot")

    bot_ok = bool(st.secrets.get("TELEGRAM_BOT_TOKEN"))
    if bot_ok:
        st.success("✅ TELEGRAM_BOT_TOKEN configurado")
    else:
        st.warning("⚠️ TELEGRAM_BOT_TOKEN não encontrado em secrets.toml")
        st.markdown(
            "**Como configurar:**\n"
            "1. Converse com [@BotFather](https://t.me/BotFather) e crie um bot com `/newbot`\n"
            "2. Copie o token gerado\n"
            "3. Adicione em `.streamlit/secrets.toml`:\n"
            "   ```\n   TELEGRAM_BOT_TOKEN = \"seu_token_aqui\"\n   ```\n"
            "4. Reinicie o app"
        )

    st.subheader("Chat IDs dos profissionais")
    st.caption(
        "Cada profissional deve enviar qualquer mensagem para o bot. "
        "Para descobrir o Chat ID, peça que envie `/start` para [@userinfobot](https://t.me/userinfobot)."
    )

    for barber in barbers:
        with st.form(f"tg_{barber['id']}"):
            c1, c2 = st.columns([4, 1])
            chat_id_val = c1.text_input(
                barber["name"],
                value=barber.get("telegram_chat_id") or "",
                placeholder="Ex: 123456789",
            )
            save_tg = c2.form_submit_button("Salvar", use_container_width=True)
        if save_tg:
            _sb().table("barbers").update(
                {"telegram_chat_id": chat_id_val.strip() or None}
            ).eq("id", barber["id"]).execute()
            st.success(f"Chat ID de {barber['name']} salvo!")
            st.rerun()

    if bot_ok:
        st.divider()
        st.subheader("Testar notificação")
        with_chat = [b for b in barbers if b.get("telegram_chat_id")]
        if not with_chat:
            st.info("Configure o Chat ID de ao menos um profissional acima.")
        else:
            test_name = st.selectbox("Profissional", [b["name"] for b in with_chat], key="test_tg")
            if st.button("Enviar mensagem de teste"):
                target = next(b for b in with_chat if b["name"] == test_name)
                ok = send_telegram(
                    st.secrets["TELEGRAM_BOT_TOKEN"],
                    target["telegram_chat_id"],
                    f"✅ Teste de notificação da <b>{shop['name']}</b>!",
                )
                if ok:
                    st.success("Enviado com sucesso!")
                else:
                    st.error("Falha — verifique token e Chat ID.")

    st.divider()

    # Gerenciar profissionais
    st.subheader("👤 Profissionais")

    for barber in barbers:
        c1, c2 = st.columns([5, 1])
        icon = "✅" if barber["is_active"] else "❌"
        c1.markdown(f"{icon} **{barber['name']}**")
        label = "Desativar" if barber["is_active"] else "Ativar"
        if c2.button(label, key=f"tog_{barber['id']}"):
            _sb().table("barbers").update({"is_active": not barber["is_active"]}).eq("id", barber["id"]).execute()
            st.rerun()

    st.write("")
    with st.expander("➕ Adicionar profissional"):
        with st.form("form_add_barber"):
            nb_name = st.text_input("Nome *")
            nb_bio = st.text_area("Bio (opcional)", height=80)
            add_barber = st.form_submit_button("Adicionar", type="primary", use_container_width=True)
        if add_barber:
            if not nb_name.strip():
                st.error("Nome é obrigatório.")
            else:
                _sb().table("barbers").insert({
                    "barbershop_id": shop["id"],
                    "name": nb_name.strip(),
                    "bio": nb_bio.strip() or None,
                }).execute()
                st.success(f"{nb_name} adicionado!")
                st.rerun()
