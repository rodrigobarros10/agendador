-- ============================================================
-- AGENDADOR - Schema Completo com RLS
-- Execute este SQL no Supabase SQL Editor
-- ============================================================

-- Habilita a extensão para geração de UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================
-- ENUMS
-- ============================================================
CREATE TYPE appointment_status AS ENUM ('pending', 'confirmed', 'cancelled', 'completed', 'no_show');
CREATE TYPE day_of_week AS ENUM ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday');

-- ============================================================
-- TABELA: barbershops
-- ============================================================
CREATE TABLE barbershops (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  owner_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  slug          TEXT NOT NULL UNIQUE,
  description   TEXT,
  phone         TEXT,
  address       TEXT,
  city          TEXT,
  logo_url      TEXT,
  cover_url     TEXT,
  timezone      TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
  is_active     BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_barbershops_slug ON barbershops(slug);
CREATE INDEX idx_barbershops_owner_id ON barbershops(owner_id);

-- ============================================================
-- TABELA: barbers (profissionais de uma barbearia)
-- ============================================================
CREATE TABLE barbers (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barbershop_id   UUID NOT NULL REFERENCES barbershops(id) ON DELETE CASCADE,
  user_id         UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  name            TEXT NOT NULL,
  bio             TEXT,
  avatar_url      TEXT,
  is_active       BOOLEAN NOT NULL DEFAULT true,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_barbers_barbershop_id ON barbers(barbershop_id);

-- ============================================================
-- TABELA: services (serviços oferecidos)
-- ============================================================
CREATE TABLE services (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barbershop_id   UUID NOT NULL REFERENCES barbershops(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  description     TEXT,
  price_cents     INTEGER NOT NULL CHECK (price_cents >= 0),
  duration_min    INTEGER NOT NULL CHECK (duration_min > 0),
  image_url       TEXT,
  is_active       BOOLEAN NOT NULL DEFAULT true,
  sort_order      INTEGER NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_services_barbershop_id ON services(barbershop_id);

-- ============================================================
-- TABELA: barber_services (quais serviços cada barbeiro faz)
-- ============================================================
CREATE TABLE barber_services (
  barber_id   UUID NOT NULL REFERENCES barbers(id) ON DELETE CASCADE,
  service_id  UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  PRIMARY KEY (barber_id, service_id)
);

-- ============================================================
-- TABELA: working_hours (horários de trabalho por barbeiro)
-- ============================================================
CREATE TABLE working_hours (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barber_id     UUID NOT NULL REFERENCES barbers(id) ON DELETE CASCADE,
  day_of_week   day_of_week NOT NULL,
  start_time    TIME NOT NULL,
  end_time      TIME NOT NULL,
  is_active     BOOLEAN NOT NULL DEFAULT true,
  CONSTRAINT valid_time_range CHECK (end_time > start_time),
  UNIQUE (barber_id, day_of_week)
);
CREATE INDEX idx_working_hours_barber_id ON working_hours(barber_id);

-- ============================================================
-- TABELA: time_off (folgas e bloqueios)
-- ============================================================
CREATE TABLE time_off (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barber_id     UUID NOT NULL REFERENCES barbers(id) ON DELETE CASCADE,
  start_at      TIMESTAMPTZ NOT NULL,
  end_at        TIMESTAMPTZ NOT NULL,
  reason        TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT valid_timeoff_range CHECK (end_at > start_at)
);
CREATE INDEX idx_time_off_barber_id_start ON time_off(barber_id, start_at);

-- ============================================================
-- TABELA: appointments (agendamentos)
-- ============================================================
CREATE TABLE appointments (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barbershop_id   UUID NOT NULL REFERENCES barbershops(id) ON DELETE CASCADE,
  barber_id       UUID NOT NULL REFERENCES barbers(id) ON DELETE CASCADE,
  service_id      UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  client_name     TEXT NOT NULL,
  client_phone    TEXT NOT NULL,
  client_email    TEXT,
  starts_at       TIMESTAMPTZ NOT NULL,
  ends_at         TIMESTAMPTZ NOT NULL,
  status          appointment_status NOT NULL DEFAULT 'confirmed',
  notes           TEXT,
  price_cents     INTEGER NOT NULL CHECK (price_cents >= 0),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT valid_appointment_range CHECK (ends_at > starts_at)
);
CREATE INDEX idx_appointments_barbershop_id ON appointments(barbershop_id);
CREATE INDEX idx_appointments_barber_id_starts ON appointments(barber_id, starts_at);
CREATE INDEX idx_appointments_starts_at ON appointments(starts_at);
CREATE INDEX idx_appointments_status ON appointments(status);

-- ============================================================
-- FUNÇÃO: updated_at automático
-- ============================================================
CREATE OR REPLACE FUNCTION handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at_barbershops
  BEFORE UPDATE ON barbershops
  FOR EACH ROW EXECUTE FUNCTION handle_updated_at();

CREATE TRIGGER set_updated_at_barbers
  BEFORE UPDATE ON barbers
  FOR EACH ROW EXECUTE FUNCTION handle_updated_at();

CREATE TRIGGER set_updated_at_services
  BEFORE UPDATE ON services
  FOR EACH ROW EXECUTE FUNCTION handle_updated_at();

CREATE TRIGGER set_updated_at_appointments
  BEFORE UPDATE ON appointments
  FOR EACH ROW EXECUTE FUNCTION handle_updated_at();

-- ============================================================
-- FUNÇÃO: verificar sobreposição de agendamentos
-- Previne double-booking no banco de dados
-- ============================================================
CREATE OR REPLACE FUNCTION check_appointment_overlap()
RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM appointments
    WHERE barber_id = NEW.barber_id
      AND status NOT IN ('cancelled', 'no_show')
      AND id != COALESCE(NEW.id, uuid_generate_v4())
      AND (NEW.starts_at, NEW.ends_at) OVERLAPS (starts_at, ends_at)
  ) THEN
    RAISE EXCEPTION 'APPOINTMENT_OVERLAP: Conflito de horário para este barbeiro';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER prevent_appointment_overlap
  BEFORE INSERT OR UPDATE ON appointments
  FOR EACH ROW EXECUTE FUNCTION check_appointment_overlap();

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================

ALTER TABLE barbershops   ENABLE ROW LEVEL SECURITY;
ALTER TABLE barbers        ENABLE ROW LEVEL SECURITY;
ALTER TABLE services       ENABLE ROW LEVEL SECURITY;
ALTER TABLE barber_services ENABLE ROW LEVEL SECURITY;
ALTER TABLE working_hours  ENABLE ROW LEVEL SECURITY;
ALTER TABLE time_off       ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments   ENABLE ROW LEVEL SECURITY;

-- ---- barbershops ----
-- Leitura pública (para página de agendamento do cliente)
CREATE POLICY "barbershops_public_read"
  ON barbershops FOR SELECT
  USING (is_active = true);

-- Apenas o dono pode criar/editar/deletar sua barbearia
CREATE POLICY "barbershops_owner_all"
  ON barbershops FOR ALL
  USING (auth.uid() = owner_id)
  WITH CHECK (auth.uid() = owner_id);

-- ---- barbers ----
CREATE POLICY "barbers_public_read"
  ON barbers FOR SELECT
  USING (is_active = true);

CREATE POLICY "barbers_owner_all"
  ON barbers FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM barbershops
      WHERE id = barbers.barbershop_id
        AND owner_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM barbershops
      WHERE id = barbers.barbershop_id
        AND owner_id = auth.uid()
    )
  );

-- ---- services ----
CREATE POLICY "services_public_read"
  ON services FOR SELECT
  USING (is_active = true);

CREATE POLICY "services_owner_all"
  ON services FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM barbershops
      WHERE id = services.barbershop_id
        AND owner_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM barbershops
      WHERE id = services.barbershop_id
        AND owner_id = auth.uid()
    )
  );

-- ---- barber_services ----
CREATE POLICY "barber_services_public_read"
  ON barber_services FOR SELECT
  USING (true);

CREATE POLICY "barber_services_owner_all"
  ON barber_services FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM barbers b
      JOIN barbershops bs ON bs.id = b.barbershop_id
      WHERE b.id = barber_services.barber_id
        AND bs.owner_id = auth.uid()
    )
  );

-- ---- working_hours ----
CREATE POLICY "working_hours_public_read"
  ON working_hours FOR SELECT
  USING (true);

CREATE POLICY "working_hours_owner_all"
  ON working_hours FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM barbers b
      JOIN barbershops bs ON bs.id = b.barbershop_id
      WHERE b.id = working_hours.barber_id
        AND bs.owner_id = auth.uid()
    )
  );

-- ---- time_off ----
CREATE POLICY "time_off_public_read"
  ON time_off FOR SELECT
  USING (true);

CREATE POLICY "time_off_owner_all"
  ON time_off FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM barbers b
      JOIN barbershops bs ON bs.id = b.barbershop_id
      WHERE b.id = time_off.barber_id
        AND bs.owner_id = auth.uid()
    )
  );

-- ---- appointments ----
-- Clientes podem inserir (anon ou autenticado)
CREATE POLICY "appointments_insert_public"
  ON appointments FOR INSERT
  WITH CHECK (true);

-- Dono da barbearia lê todos os agendamentos da sua barbearia
CREATE POLICY "appointments_owner_read"
  ON appointments FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM barbershops
      WHERE id = appointments.barbershop_id
        AND owner_id = auth.uid()
    )
  );

-- Dono pode atualizar status dos agendamentos
CREATE POLICY "appointments_owner_update"
  ON appointments FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM barbershops
      WHERE id = appointments.barbershop_id
        AND owner_id = auth.uid()
    )
  );

-- ============================================================
-- DADOS DE SEED (exemplo para desenvolvimento)
-- ============================================================
-- Descomente após criar seu usuário no Supabase Auth

-- INSERT INTO barbershops (owner_id, name, slug, description, phone, address, city)
-- VALUES (
--   '<SEU_USER_ID_AQUI>',
--   'Barbearia Exemplo',
--   'barbearia-exemplo',
--   'A melhor barbearia da cidade',
--   '(11) 99999-9999',
--   'Rua das Flores, 123',
--   'São Paulo'
-- );
