"""Exact references (docs/contracts/canonical-data.md, SPEC-015 REQ-1506).

A stored reference is structured and exact: stable ID, version and passport
digest. Only a component reference may carry an optional native realization;
a setup reference has no variant axis (ADR-0014). Floating branches, tags,
ranges and ``latest`` are not representable.

Every wire constraint is expressed as a regex pattern so the generated JSON
Schema rejects exactly what the Python model rejects. References are hashed
and persisted structures, so unknown fields stay forbidden on the wire.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.versioning import VERSION_PATTERN

type Version = Annotated[str, Field(pattern=VERSION_PATTERN)]
type PassportDigest = Annotated[str, Field(pattern=DIGEST_PATTERN)]


class ComponentRef(BaseModel):
    """Exact reference to a component version, optionally to one realization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stable_id: Annotated[str, Field(pattern=stable_id_pattern("component"))]
    variant_id: Annotated[str, Field(pattern=stable_id_pattern("variant"))] | None = None
    version: Version
    passport_digest: PassportDigest


class SetupRef(BaseModel):
    """Exact reference to a setup version; a setup has no variant axis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stable_id: Annotated[str, Field(pattern=stable_id_pattern("setup"))]
    version: Version
    passport_digest: PassportDigest
