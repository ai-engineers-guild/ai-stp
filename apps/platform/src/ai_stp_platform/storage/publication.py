"""Storage provenance of a sealed catalog publication, independent of current authority."""

from __future__ import annotations

from typing import cast

from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_platform.models import CatalogMetadata, ObjectLocation


class PublicationIdentityError(ValueError):
    """The recorded passport cannot identify an immutable publication owner."""


def publication_owner(metadata: CatalogMetadata, location: ObjectLocation) -> str:
    """Bind storage to the original publisher; catalog transfers only change authority."""
    document = metadata.passport_document
    if not isinstance(document, dict):
        raise PublicationIdentityError("passport document is not an object")
    sealed = cast(dict[str, JsonValue], document)
    if (
        document.get("stable_id") != metadata.stable_id
        or document.get("version") != metadata.version
        or derive_revision_id(sealed) != document.get("revision_id")
        or digest_canonical("ai-stp:passport:v1", sealed) != metadata.passport_digest
    ):
        raise PublicationIdentityError("passport does not match its recorded identity")
    owner = document.get("owner_id")
    if not isinstance(owner, str) or not owner or "/" in owner:
        raise PublicationIdentityError("passport has no valid publication owner")
    artifact = document.get("artifact")
    if not isinstance(artifact, dict):
        raise PublicationIdentityError("passport declares no artifact")
    declared = cast(dict[str, object], artifact)
    if (
        declared.get("digest") != location.digest
        or declared.get("size_bytes") != location.size_bytes
    ):
        raise PublicationIdentityError("stored object disagrees with the declared artifact")
    return owner
