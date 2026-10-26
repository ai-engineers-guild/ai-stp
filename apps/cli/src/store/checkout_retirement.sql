-- Schema 58 fences older writers after a reviewed checkout intent is retired.
-- The original journal and actor are retained; only a settled reservation may go.
CREATE TABLE native_checkout_retirement (
    source_operation_id TEXT PRIMARY KEY REFERENCES operation(operation_id),
    request_operation_id TEXT NOT NULL UNIQUE REFERENCES operation(operation_id),
    retirement_operation_id TEXT NOT NULL UNIQUE REFERENCES operation(operation_id),
    CHECK (source_operation_id != retirement_operation_id)
) STRICT;
