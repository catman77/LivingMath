-- Private operator extension; schema5 is retained. Transaction owned by installer.
CREATE TABLE deploy018_leases(move_id INTEGER PRIMARY KEY REFERENCES typed011_activations(move_id), nonce TEXT NOT NULL UNIQUE, expires REAL NOT NULL, payload_json TEXT NOT NULL);
CREATE TRIGGER lm018_deploy018_leases_update BEFORE UPDATE ON deploy018_leases BEGIN SELECT RAISE(ABORT,'018 append-only:deploy018_leases'); END;
CREATE TRIGGER lm018_deploy018_leases_delete BEFORE DELETE ON deploy018_leases BEGIN SELECT RAISE(ABORT,'018 append-only:deploy018_leases'); END;
CREATE TABLE deploy018_attempts(move_id INTEGER PRIMARY KEY REFERENCES deploy018_leases(move_id), payload_json TEXT NOT NULL);
CREATE TRIGGER lm018_deploy018_attempts_update BEFORE UPDATE ON deploy018_attempts BEGIN SELECT RAISE(ABORT,'018 append-only:deploy018_attempts'); END;
CREATE TRIGGER lm018_deploy018_attempts_delete BEFORE DELETE ON deploy018_attempts BEGIN SELECT RAISE(ABORT,'018 append-only:deploy018_attempts'); END;
CREATE TABLE deploy018_attestations(move_id INTEGER PRIMARY KEY REFERENCES deploy018_attempts(move_id), event_id INTEGER NOT NULL UNIQUE REFERENCES events(id), payload_json TEXT NOT NULL);
CREATE TRIGGER lm018_deploy018_attestations_update BEFORE UPDATE ON deploy018_attestations BEGIN SELECT RAISE(ABORT,'018 append-only:deploy018_attestations'); END;
CREATE TRIGGER lm018_deploy018_attestations_delete BEFORE DELETE ON deploy018_attestations BEGIN SELECT RAISE(ABORT,'018 append-only:deploy018_attestations'); END;
CREATE TABLE deploy018_consumptions(move_id INTEGER PRIMARY KEY REFERENCES deploy018_leases(move_id), receipt_id INTEGER NOT NULL UNIQUE REFERENCES typed011_receipts(id));
CREATE TRIGGER lm018_deploy018_consumptions_update BEFORE UPDATE ON deploy018_consumptions BEGIN SELECT RAISE(ABORT,'018 append-only:deploy018_consumptions'); END;
CREATE TRIGGER lm018_deploy018_consumptions_delete BEFORE DELETE ON deploy018_consumptions BEGIN SELECT RAISE(ABORT,'018 append-only:deploy018_consumptions'); END;
CREATE TABLE deploy018_revocations(move_id INTEGER PRIMARY KEY REFERENCES typed011_activations(move_id), reason TEXT NOT NULL);
CREATE TRIGGER lm018_deploy018_revocations_update BEFORE UPDATE ON deploy018_revocations BEGIN SELECT RAISE(ABORT,'018 append-only:deploy018_revocations'); END;
CREATE TRIGGER lm018_deploy018_revocations_delete BEFORE DELETE ON deploy018_revocations BEGIN SELECT RAISE(ABORT,'018 append-only:deploy018_revocations'); END;
