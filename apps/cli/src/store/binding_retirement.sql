-- Schema 60 preserves original adoption evidence after local binding retirement.
-- A new request may reserve the project again; this original request cannot.
CREATE TABLE native_binding_retirement (
    binding_operation_id TEXT PRIMARY KEY REFERENCES operation(operation_id),
    request_operation_id TEXT NOT NULL UNIQUE REFERENCES operation(operation_id),
    retirement_operation_id TEXT NOT NULL UNIQUE REFERENCES operation(operation_id),
    CHECK (binding_operation_id != retirement_operation_id),
    CHECK (request_operation_id != retirement_operation_id),
    CHECK (binding_operation_id != request_operation_id)
) STRICT;
