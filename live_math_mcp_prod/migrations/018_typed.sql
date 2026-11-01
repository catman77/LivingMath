-- 018 additive guards; runner validates schema5 and supplies BEGIN IMMEDIATE.
CREATE TRIGGER lm018_typed011_configuration_update BEFORE UPDATE ON typed011_configuration BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_configuration'); END;
CREATE TRIGGER lm018_typed011_configuration_delete BEFORE DELETE ON typed011_configuration BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_configuration'); END;
CREATE TRIGGER lm018_typed011_scopes_update BEFORE UPDATE ON typed011_scopes BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_scopes'); END;
CREATE TRIGGER lm018_typed011_scopes_delete BEFORE DELETE ON typed011_scopes BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_scopes'); END;
CREATE TRIGGER lm018_typed011_precommits_update BEFORE UPDATE ON typed011_precommits BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_precommits'); END;
CREATE TRIGGER lm018_typed011_precommits_delete BEFORE DELETE ON typed011_precommits BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_precommits'); END;
CREATE TRIGGER lm018_typed011_moves_update BEFORE UPDATE ON typed011_moves BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_moves'); END;
CREATE TRIGGER lm018_typed011_moves_delete BEFORE DELETE ON typed011_moves BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_moves'); END;
CREATE TRIGGER lm018_typed011_activations_update BEFORE UPDATE ON typed011_activations BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_activations'); END;
CREATE TRIGGER lm018_typed011_activations_delete BEFORE DELETE ON typed011_activations BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_activations'); END;
CREATE TRIGGER lm018_typed011_executions_update BEFORE UPDATE ON typed011_executions BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_executions'); END;
CREATE TRIGGER lm018_typed011_executions_delete BEFORE DELETE ON typed011_executions BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_executions'); END;
CREATE TRIGGER lm018_typed011_receipts_update BEFORE UPDATE ON typed011_receipts BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_receipts'); END;
CREATE TRIGGER lm018_typed011_receipts_delete BEFORE DELETE ON typed011_receipts BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_receipts'); END;
CREATE TRIGGER lm018_typed011_journal_update BEFORE UPDATE ON typed011_journal BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_journal'); END;
CREATE TRIGGER lm018_typed011_journal_delete BEFORE DELETE ON typed011_journal BEGIN SELECT RAISE(ABORT,'018 append-only:typed011_journal'); END;
