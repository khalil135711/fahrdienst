-- Für eine BESTEHENDE Datenbank (ohne "docker compose down -v"), nach 2026-11-geteilte-fahrten.sql:
--   docker compose exec -T db psql -U fahrdienst fahrdienst < migrations/2026-12-tarife-partner-quittung.sql
CREATE TABLE IF NOT EXISTS companies (
  id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, contact TEXT NOT NULL DEFAULT '',
  address TEXT NOT NULL DEFAULT '', fee_per_ride NUMERIC(6,2), active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now());
ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS vehicle_type TEXT NOT NULL DEFAULT 'normal';
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS company_id INT REFERENCES companies(id);
ALTER TABLE rides ADD COLUMN IF NOT EXISTS vehicle_type TEXT NOT NULL DEFAULT 'normal';
ALTER TABLE rides ADD COLUMN IF NOT EXISTS payment_method TEXT NOT NULL DEFAULT 'km';
ALTER TABLE rides ADD COLUMN IF NOT EXISTS voucher_no TEXT;
ALTER TABLE rides ADD COLUMN IF NOT EXISTS allow_partner BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE rides ADD COLUMN IF NOT EXISTS quote JSONB;
ALTER TABLE rides ADD COLUMN IF NOT EXISTS fare JSONB;
ALTER TABLE rides ADD COLUMN IF NOT EXISTS company_id INT REFERENCES companies(id);
ALTER TABLE rides ADD COLUMN IF NOT EXISTS partner_fee NUMERIC(6,2);
ALTER TABLE rides ADD COLUMN IF NOT EXISTS receipt_no TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS rides_receipt_no_key ON rides (receipt_no) WHERE receipt_no IS NOT NULL;
CREATE SEQUENCE IF NOT EXISTS receipt_seq;
DO $$ BEGIN
  ALTER TABLE vehicles ADD CONSTRAINT vehicles_type_check CHECK (vehicle_type IN ('normal','wheelchair'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE rides ADD CONSTRAINT rides_vehicle_type_check CHECK (vehicle_type IN ('normal','wheelchair'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE rides ADD CONSTRAINT rides_payment_check CHECK (payment_method IN ('km','taxischein'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
