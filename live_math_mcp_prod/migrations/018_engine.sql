-- 018 additive guards; runner validates schema5 and supplies BEGIN IMMEDIATE.
CREATE TRIGGER lm018_engine017_sources_update BEFORE UPDATE ON engine017_sources BEGIN SELECT RAISE(ABORT,'018 append-only:engine017_sources'); END;
CREATE TRIGGER lm018_engine017_sources_delete BEFORE DELETE ON engine017_sources BEGIN SELECT RAISE(ABORT,'018 append-only:engine017_sources'); END;
CREATE TRIGGER lm018_engine017_requests_update BEFORE UPDATE ON engine017_requests BEGIN SELECT RAISE(ABORT,'018 append-only:engine017_requests'); END;
CREATE TRIGGER lm018_engine017_requests_delete BEFORE DELETE ON engine017_requests BEGIN SELECT RAISE(ABORT,'018 append-only:engine017_requests'); END;
CREATE TRIGGER lm018_engine017_projections_update BEFORE UPDATE ON engine017_projections BEGIN SELECT RAISE(ABORT,'018 append-only:engine017_projections'); END;
CREATE TRIGGER lm018_engine017_projections_delete BEFORE DELETE ON engine017_projections BEGIN SELECT RAISE(ABORT,'018 append-only:engine017_projections'); END;
