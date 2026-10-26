-- Schema 57 reserves a physical checkout before an uncertain confirmation.
-- Original intent and effects remain in the append-only operation journal.
CREATE TABLE native_checkout_reservation (
    request_operation_id TEXT PRIMARY KEY REFERENCES operation(operation_id),
    local_project_id TEXT NOT NULL UNIQUE REFERENCES entity(stable_id),
    root_device TEXT NOT NULL,
    root_inode TEXT NOT NULL,
    confirmation_operation_id TEXT UNIQUE REFERENCES operation(operation_id),
    binding_operation_id TEXT UNIQUE REFERENCES operation(operation_id),
    context_id TEXT REFERENCES native_context(context_id),
    UNIQUE (root_device, root_inode),
    CHECK (confirmation_operation_id IS NOT NULL OR binding_operation_id IS NOT NULL),
    CHECK ((binding_operation_id IS NULL AND context_id IS NULL)
        OR (binding_operation_id IS NOT NULL AND context_id IS NOT NULL)),
    CHECK (request_operation_id != coalesce(confirmation_operation_id, '')),
    CHECK (request_operation_id != coalesce(binding_operation_id, '')),
    CHECK (confirmation_operation_id IS NULL OR binding_operation_id IS NULL
        OR confirmation_operation_id != binding_operation_id)
) STRICT;
