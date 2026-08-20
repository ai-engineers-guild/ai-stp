"""Command handlers.

A handler takes parsed parameters and returns the payload model that goes into
the envelope's `data`. It never writes to a stream, never chooses an exit code
and never formats anything: rendering belongs to `output.py`, and the exit class
belongs to the error registry. `ADR-0013` keeps the parser a thin application
layer, and this is the other half of that — a handler that printed would make
the machine contract depend on where it was called from.
"""
