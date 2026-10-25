-- Schema 55 extends the existing authority registry. Credentials stay in the vault.

CREATE TABLE native_connection (
    connection_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL UNIQUE,
    origin TEXT NOT NULL,
    public_key TEXT UNIQUE,
    state TEXT NOT NULL CHECK (state IN ('creating','ready')),
    detail TEXT NOT NULL,
    CHECK ((state = 'creating' AND public_key IS NULL)
        OR (state = 'ready' AND public_key IS NOT NULL))
) STRICT;

CREATE TABLE native_context (
    context_id TEXT PRIMARY KEY,
    connection_id TEXT REFERENCES native_connection(connection_id),
    detail TEXT NOT NULL
) STRICT;

CREATE TABLE native_context_selection (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    revision TEXT NOT NULL,
    context_id TEXT NOT NULL REFERENCES native_context(context_id)
) STRICT;
