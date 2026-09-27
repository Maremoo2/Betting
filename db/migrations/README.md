# Database migrations

New databases are created from `db/schema.sql`.

Future schema changes must be added here as ordered `*.sql` migration files.
`SQLiteStore.apply_migrations()` records each applied filename in
`schema_migrations` and will not apply it twice.

Do not edit historical migration files after they have been used on a persistent
database. Add a new migration instead.
