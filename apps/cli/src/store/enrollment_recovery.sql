-- Schema 56 admits one reviewed replacement for an independently enrolled key.
-- Original contexts, credentials and delivery intents retain their identities.
CREATE TABLE native_enrollment_recovery (
    operation_id TEXT PRIMARY KEY REFERENCES operation(operation_id),
    previous_connection_id TEXT NOT NULL UNIQUE REFERENCES native_connection(connection_id),
    replacement_connection_id TEXT NOT NULL UNIQUE REFERENCES native_connection(connection_id),
    detail TEXT NOT NULL,
    confirmation TEXT,
    CHECK (previous_connection_id != replacement_connection_id)
) STRICT;
