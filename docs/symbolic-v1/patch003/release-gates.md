# PATCH003 release gates

| Gate | Actual status | Evidence |
|---|---|---|
| P0 exact SP complex + independent verifier + negatives | ACCEPTED_P0 / PASS | sp_complex_exact_counts.json; sp_path_coherence_certificate.json; production-qa/transcript.json |
| P1 origin/ablation/real operator traces/finite grammar | ACCEPTED_P1 / PASS | observer_feature_provenance.json; feature_ablation_report.json; synthetic_grammar_holdout.json |
| P2 authentic blinded13-config corpus comparison | RESEARCH_COMPLETED_P2 / PASS | nostradamus_pairwise_holdout.json; RESULTS.csv |
| P2 transfer superiority | NOT_SUPPORTED | global-alpha0/1/183/16; punctuation77/28/0/95 |
| Public HTTPS/OAuth MCP | PASS | 769+252 checks;82 tools;75 legacy schemas exact |
| SQLite, objects, audit and original chain prefixes | PASS | integrity_results.json |
| Offline replay without network | PASS | privacy_sandbox_report.json; OFFLINE_REPLAY.json |
| Unit/integration tests | PASS |302 source +302 wheel;1066 legacy;12 reference |
| Historical tests marked skipped | SKIPPED |20 legacy tests, retained original reasons |
| Unique grammar / arbitrary-history pi1 / semantic theorem | NOT_PROVED | Explicitly outside finite evidence |
| Independent external operator R3 replay | PENDING | No external witness claimed |
| Native SUTI runtime | NOT_EXECUTED | No new implementation or claim |
| Full pentest / hosted CI | NOT_RUN | Bounded existing gates only |

No test label enters inference. No result grants execution permission or assigns mathematical verified. Negative scientific results are retained and do not prevent this engineering release.
