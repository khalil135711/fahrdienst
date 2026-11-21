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

CREATE TABLE vehicles (
  id SERIAL PRIMARY KEY,
  model TEXT NOT NULL,
  plate TEXT UNIQUE NOT NULL
);

CREATE TABLE drivers (
  user_id INT PRIMARY KEY REFERENCES users(id),
  vehicle_id INT REFERENCES vehicles(id),
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
  price NUMERIC(8,2),
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
  offered_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  UNIQUE (ride_id, driver_id)
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
