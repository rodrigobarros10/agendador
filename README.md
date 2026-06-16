# Agendador

Sistema de agendamento para barbearias. Clientes acessam uma página pública com o slug da barbearia e fazem o agendamento em 4 etapas: serviço → profissional → horário → dados pessoais.

## Stack

- **Python + Streamlit** — interface web
- **Supabase** — banco de dados Postgres com RLS e Auth

## Configuração

Copie o arquivo de segredos e preencha com as chaves do seu projeto Supabase (**Project Settings → API**):

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Execute o schema SQL no **Supabase SQL Editor**:

```
supabase/schema.sql
```

## Instalação e execução

```bash
pip install -r requirements.txt
streamlit run app.py
```

Acesse `http://localhost:8501?shop=<slug-da-barbearia>`.
