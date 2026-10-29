-- Schema 61 fences writers unaware of reviewed full-identity location receipts.
-- The operation journal retains immutable history; this row locates its current
-- terminal receipt without rewriting the original adoption or request.
CREATE TABLE native_checkout_location (
    binding_operation_id TEXT PRIMARY KEY REFERENCES operation(operation_id),
    location_operation_id TEXT NOT NULL UNIQUE REFERENCES operation(operation_id),
    CHECK (binding_operation_id != location_operation_id)
) STRICT;
