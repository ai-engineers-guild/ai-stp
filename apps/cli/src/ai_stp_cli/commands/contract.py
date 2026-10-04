"""`ai-stp contract inventory` — the coordinated standard family and every other axis."""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_contracts.inventory_record import recorded
from ai_stp_contracts.standard import StandardInventory


def inventory(_parameters: Mapping[str, object]) -> Answer[StandardInventory]:
    """Report the standard family, contract digest, and every inventoried identity."""
    return Answer(recorded())
