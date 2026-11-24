-- Für eine BESTEHENDE Datenbank (ohne "docker compose down -v"):
--   docker compose exec -T db psql -U fahrdienst fahrdienst < migrations/2026-11-geteilte-fahrten.sql
ALTER TABLE rides ADD COLUMN IF NOT EXISTS price_solo NUMERIC(8,2);
ALTER TABLE rides ADD COLUMN IF NOT EXISTS shared BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE rides ADD COLUMN IF NOT EXISTS pooled BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE rides ADD COLUMN IF NOT EXISTS saved_km NUMERIC(8,2);
ALTER TABLE ride_offers ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'solo';
ALTER TABLE ride_offers ADD COLUMN IF NOT EXISTS detour_km NUMERIC(8,2);
ALTER TABLE ride_offers ADD COLUMN IF NOT EXISTS saved_km NUMERIC(8,2);
DO $$ BEGIN
  ALTER TABLE ride_offers ADD CONSTRAINT ride_offers_kind_check CHECK (kind IN ('solo','pool'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
