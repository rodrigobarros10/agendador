# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt   # instalar dependências
streamlit run app.py              # servidor em http://localhost:8501
python -m py_compile app.py lib/utils.py lib/availability.py lib/supabase_client.py  # checar sintaxe
```

Não há test runner configurado. `py_compile` é a forma mais rápida de verificar erros de sintaxe.

## Credenciais

Ficam em `.streamlit/secrets.toml` (não versionado). Exemplo em `.streamlit/secrets.toml.example`:

```
SUPABASE_URL = "https://<projeto>.supabase.co"
SUPABASE_ANON_KEY = "<anon-key>"
```

Acessadas no código via `st.secrets["SUPABASE_URL"]`.

## Arquitetura

**Stack:** Python · Streamlit · Supabase (Postgres + RLS) · supabase-py.

### Database (`supabase/schema.sql`)

- RLS habilitado em todas as tabelas. A chave anon permite leitura pública de barbershops, barbers, services, working_hours, time_off, e INSERT em appointments. Demais escritas exigem sessão autenticada.
- Double-booking prevenido em dois níveis: `get_available_slots` filtra slots ocupados antes de inserir, e o trigger `prevent_appointment_overlap` no banco lança `APPOINTMENT_OVERLAP` em caso de race condition.

### Módulos (`lib/`)

| Arquivo | Responsabilidade |
|---|---|
| `supabase_client.py` | `get_supabase()` — singleton do cliente Supabase via `@st.cache_resource` |
| `utils.py` | `format_currency`, `format_phone`, `mask_phone`, `format_date_ptbr`, `generate_time_slots`, `day_of_week_from_date` |
| `availability.py` | `get_available_slots()` — consulta working_hours, filtra appointments e time_off, exclui slots a menos de 30 min no passado. Resultado em cache por 30 s via `@st.cache_data`. |

### Fluxo de agendamento (`app.py`)

Wizard linear de 5 etapas controlado por `st.session_state.step`:

```
service → barber → datetime → form → success
```

O slug da barbearia vem de `st.query_params.get("shop")`. Os dados da barbearia, barbeiros e serviços são carregados uma vez via `@st.cache_data(ttl=60)`. Cada etapa fica em um bloco `if/elif` no arquivo principal. Voltar nunca apaga escolhas anteriores, apenas as posteriores.

O INSERT de agendamento é feito diretamente no Supabase dentro do step `form` — não há camada de API separada.
