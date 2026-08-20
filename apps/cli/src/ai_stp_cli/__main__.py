"""`python -m ai_stp_cli`, equivalent to the `ai-stp` console script.

Both entrypoints call the same `run`, so neither can behave differently from the
other. The module form is what a test can invoke without depending on a console
script being on PATH.
"""

from ai_stp_cli.app import run

run()
