-- Testdaten für die Entwicklung (Passwort-Hash ist nur ein Platzhalter)
INSERT INTO users (id,name,email,password_hash,role) VALUES
 (1,'Test Kunde','kunde@test.de','x','customer'),
 (2,'Test Fahrer','fahrer@test.de','x','driver'),
 (3,'Admin','admin@test.de','x','admin');
INSERT INTO vehicles (id,model,plate) VALUES (1,'Mercedes E-Klasse','BN-FD 421');
INSERT INTO drivers (user_id,vehicle_id,status,location,rating_avg,rating_count)
 VALUES (2,1,'free',ST_SetSRID(ST_MakePoint(7.0982,50.7374),4326)::geography,4.9,312);
SELECT setval('users_id_seq',3);
