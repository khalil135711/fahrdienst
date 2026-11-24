CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('customer','driver','admin')),
  active BOOLEAN NOT NULL DEFAULT true,          -- false = Konto gesperrt
  failed_attempts INT NOT NULL DEFAULT 0,        -- Fehlversuche beim Login
  locked_until TIMESTAMPTZ,                      -- vorübergehende Sperre
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Partnerunternehmen: bieten ihre Fahrer über uns an. Pro Fahrt zahlt die Firma eine Gebühr.
CREATE TABLE companies (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  contact TEXT NOT NULL DEFAULT '',
  address TEXT NOT NULL DEFAULT '',
  fee_per_ride NUMERIC(6,2),                    -- NULL = Standardgebühr aus den Einstellungen
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE vehicles (
  id SERIAL PRIMARY KEY,
  model TEXT NOT NULL,
  plate TEXT UNIQUE NOT NULL,
  vehicle_type TEXT NOT NULL DEFAULT 'normal' CHECK (vehicle_type IN ('normal','wheelchair'))
);

CREATE TABLE drivers (
  user_id INT PRIMARY KEY REFERENCES users(id),
  vehicle_id INT REFERENCES vehicles(id),
  company_id INT REFERENCES companies(id),       -- NULL = eigener Fahrer, sonst Fahrer einer Partnerfirma
  status TEXT NOT NULL DEFAULT 'offline' CHECK (status IN ('offline','free','busy')),
  location GEOGRAPHY(Point,4326),
  last_seen TIMESTAMPTZ,
  rating_avg NUMERIC(3,2) DEFAULT 0,
  rating_count INT DEFAULT 0
);
CREATE INDEX drivers_location_idx ON drivers USING GIST (location);

CREATE TABLE rides (
  id SERIAL PRIMARY KEY,
  customer_id INT REFERENCES users(id),
  driver_id INT REFERENCES drivers(user_id),
  status TEXT NOT NULL DEFAULT 'requested'
    CHECK (status IN ('requested','accepted','arriving','in_progress','completed','cancelled','no_driver')),
  pickup GEOGRAPHY(Point,4326) NOT NULL,
  distance_km NUMERIC(8,2),
  price NUMERIC(8,2),                            -- Preis, den der Kunde zahlt
  price_solo NUMERIC(8,2),                       -- Preis als Einzelfahrt (zum Vergleich)
  shared BOOLEAN NOT NULL DEFAULT false,         -- Kunde ist mit geteilter Fahrt einverstanden
  pooled BOOLEAN NOT NULL DEFAULT false,         -- wurde tatsächlich zu einer laufenden Fahrt hinzugefügt
  saved_km NUMERIC(8,2),                         -- geschätzte eingesparte Kilometer durch das Teilen
  vehicle_type TEXT NOT NULL DEFAULT 'normal' CHECK (vehicle_type IN ('normal','wheelchair')),
  payment_method TEXT NOT NULL DEFAULT 'km' CHECK (payment_method IN ('km','taxischein')),
  voucher_no TEXT,                               -- Nummer des Taxischeins
  allow_partner BOOLEAN NOT NULL DEFAULT false,  -- Kunde erlaubt Fahrer von Partnerfirmen
  quote JSONB,                                   -- beide Preisvarianten zum Zeitpunkt der Anfrage
  fare JSONB,                                    -- endgültige Preisaufstellung (nach Annahme durch den Fahrer)
  company_id INT REFERENCES companies(id),       -- Firma des Fahrers (NULL = eigener Fahrer)
  partner_fee NUMERIC(6,2),                      -- Gebühr, die die Partnerfirma uns für diese Fahrt zahlt
  receipt_no TEXT UNIQUE,                        -- Quittungsnummer (vergeben beim Fahrtende)
  requested_at TIMESTAMPTZ DEFAULT now(),
  accepted_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

-- Bis zu 4 Ziele pro Fahrt, in Reihenfolge. Abfahrt = rides.pickup (Standort des Kunden).
CREATE TABLE ride_stops (
  id SERIAL PRIMARY KEY,
  ride_id INT NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
  position INT NOT NULL CHECK (position BETWEEN 1 AND 4),
  address TEXT NOT NULL,
  location GEOGRAPHY(Point,4326),
  reached_at TIMESTAMPTZ,
  UNIQUE (ride_id, position)
);

-- Angebote: eine Anfrage geht nacheinander an einen Fahrer nach dem anderen (je OFFER_SECONDS)
CREATE TABLE ride_offers (
  id SERIAL PRIMARY KEY,
  ride_id INT NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
  driver_id INT NOT NULL REFERENCES drivers(user_id),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','declined','expired')),
  kind TEXT NOT NULL DEFAULT 'solo' CHECK (kind IN ('solo','pool')),  -- 'pool' = Fahrgast soll zu laufender Fahrt zusteigen
  detour_km NUMERIC(8,2),
  saved_km NUMERIC(8,2),
  offered_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  UNIQUE (ride_id, driver_id)
);

-- Musik im Fahrzeug: Bibliotheken (= Playlists) und Titel. Die Dateien liegen im Ordner MUSIC_DIR.
CREATE TABLE music_libraries (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE music_tracks (
  id SERIAL PRIMARY KEY,
  library_id INT NOT NULL REFERENCES music_libraries(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  artist TEXT NOT NULL DEFAULT '',
  filename TEXT NOT NULL UNIQUE,
  mime TEXT NOT NULL,
  duration_s INT,
  size_bytes BIGINT NOT NULL,
  license_note TEXT NOT NULL,          -- Nachweis, dass die Musik im Fahrzeug gespielt werden darf
  uploaded_by INT REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Zeitungen für Kunden während der Fahrt (RSS/Atom-Feeds, vom Admin hinterlegt)
CREATE TABLE news_sources (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  feed_url TEXT NOT NULL UNIQUE,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Laufende Nummer für Quittungen
CREATE SEQUENCE receipt_seq;

-- Einstellungen (Preise, Rabatt, Plätze), im Admin-Bereich änderbar
CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Positionsverlauf: Geschwindigkeit & Kilometer (nach Frist löschen, DSGVO!)
CREATE TABLE location_log (
  id BIGSERIAL PRIMARY KEY,
  driver_id INT REFERENCES drivers(user_id),
  ride_id INT REFERENCES rides(id),
  location GEOGRAPHY(Point,4326) NOT NULL,
  speed_kmh NUMERIC(5,1),
  recorded_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX location_log_driver_time ON location_log (driver_id, recorded_at);

CREATE TABLE ratings (
  id SERIAL PRIMARY KEY,
  ride_id INT UNIQUE REFERENCES rides(id),
  driver_id INT REFERENCES drivers(user_id),
  stars INT NOT NULL CHECK (stars BETWEEN 1 AND 5),
  comment TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Nächste freie Fahrer im Umkreis (Beispiel: 5 km um Punkt)
-- SELECT user_id, ST_Distance(location, ST_MakePoint(7.0982,50.7374)::geography) AS meter
-- FROM drivers
-- WHERE status='free' AND ST_DWithin(location, ST_MakePoint(7.0982,50.7374)::geography, 5000)
-- ORDER BY meter LIMIT 5;

-- Löschen alter Positionsdaten (täglich per Cron):
-- DELETE FROM location_log WHERE recorded_at < now() - interval '30 days';
