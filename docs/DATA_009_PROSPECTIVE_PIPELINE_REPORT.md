# DATA-009 prospective PIT pipeline — research-only

Date 2026-11-09. Source module `hbi.data009_prospective_bridge.audit` validates source bytes with SHA256, UTC observation times, pre/post event separation, race and full-field IDs, complete WIN/model vectors, scratches and candidate T-4 clock. It NEVER issues a PIT certificate or BET authority. Even a fully synthetic passing software test returns PIT_UNPROVEN pending independent source and actual-start verification.

Previous DATA-007 original 7-Nov program contained 180 runners and 900 prior-start rows. These PDF records are not qualified actual T-4 WIN. DEV-013 had 8/10 selected in-freeze full WIN vectors but no separately retained raw WIN HTTP SHA in that selected sample. No new live capture has been executed. Collector has an opt-in private original response archive, but the manual A-WATCH workflow is not an automatically qualified T-4 cohort.

Local isolated tests passed; GH branch CI at exact HEAD must be reviewed separately. Run:
```sh
python -m pytest -q tests/test_data009_prospective_bridge.py
```

Missing real operational link: exact version raw WIN + roster + pre-race frozen model at the same cutoff; verified actual start, scratches and individual identities; official complete result/dividend and append-only source readback. Strategy, Pre-Watch, Champion and production workflows unchanged.