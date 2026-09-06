"""`ai-stp contract inventory` — the coordinated standard family and every other axis."""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_contracts.schemas import current_inventory
from ai_stp_contracts.standard import StandardInventory


def inventory(_parameters: Mapping[str, object]) -> Answer[StandardInventory]:
    """Report the standard family, contract digest, and every inventoried identity."""
    return Answer(current_inventory())
