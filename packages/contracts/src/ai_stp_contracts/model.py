"""The base of every model in this package."""

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """A wire model whose validator and serializer are built on first use.

    The package defines about seven hundred models, and the CLI imports most of
    them before it runs any command. Building every core schema at import was
    about half a second of each invocation (docs/engineering/cli-performance.md);
    a deferred model builds the first time it validates or serializes, so a
    command pays only for the models it uses. Subclasses merge their own
    `model_config` with this one.
    """

    model_config = ConfigDict(defer_build=True)
