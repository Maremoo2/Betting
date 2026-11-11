# RELEASE-006 · SQLite integrity

Applied 0009 and 0010 to a disposable byte copy of archived MVP021 `originals/audit-exact.sqlite`. The input SHA-256 was `01e0432d06c04667723f528510944b16d54e1badf103cf51c07e7db0c96e5471`, identical before and after the test. The observed migrated file SHA-256 was `368358886eff27642a5d9d2b17ff086a8b1783c023a583dd3e72312d2decf6f0`. Migration timestamps vary by execution.

| Table | Rows before and after | Row snapshot SHA-256 before and after |
| --- | ---: | --- |
| shadow_decision_runs | 915 | `b7dc56eef744c7ebc02b69b70969b21433454011ffdc9f5c1fc13ec40b87b095` |
| shadow_tickets | 39 | `2723fdc770c3e7178c726eb1a54b3819a5df1ed093a8af0028b0e1b4d6790782` |

Restart reopened the copy and reapplied no migrations. SQLite integrity_check returned ok and foreign_key_check returned no rows. Migration DDL and history commit together. An injected failure tests rollback of both.

Signal inserts acquire a write transaction, compare both unique keys and compare the frozen payload before accepting a retry. The first request time remains immutable and is excluded from retry comparison. A conflicting payload raises an explicit error. SQL triggers reject UPDATE, DELETE and replacement inserts. An injected error after INSERT verifies rollback and the settlement queue stays empty. The original active database was outside the test.
