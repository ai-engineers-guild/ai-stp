"""Install editable taxonomy defaults without replacing tenant-owned records."""

from collections.abc import Collection

from sqlalchemy import Connection, Integer, String, column, select, table, update
from sqlalchemy.dialects.postgresql import insert

from ai_stp_contracts.technology import normalize_technology_name
from ai_stp_contracts.technology_seed import SEED_TECHNOLOGIES
from ai_stp_contracts.technology_taxonomy import (
    TAXONOMY_AREAS,
    TAXONOMY_CATEGORIES,
    TAXONOMY_CLASSIFICATIONS,
    TAXONOMY_PROVENANCE,
)


def _registry(name: str):
    return table(
        name,
        *(
            column(key, String())
            for key in (
                "organization_id",
                "id",
                "name",
                "normalized_name",
                "description",
                "provenance",
                "state",
            )
        ),
        column("revision", Integer()),
        *((column("area_id", String()),) if name == "technology_category" else ()),
    )


def install_technology_taxonomy(connection: Connection, organization_id: str) -> bool:
    """Migration/bootstrap share one idempotent insert-only default installer.

    A preexisting ID wins over its default name. A same-name tenant record is
    reused, including its owner-selected area, state, description, and revision.
    """
    areas = _registry("technology_area")
    categories = _registry("technology_category")
    changed = False
    area_ids: dict[str, str] = {}
    for identifier, name, _localized in TAXONOMY_AREAS:
        result = connection.execute(
            insert(areas)
            .values(
                organization_id=organization_id,
                id=identifier,
                name=name,
                normalized_name=normalize_technology_name(name),
                description="",
                revision=1,
                provenance=TAXONOMY_PROVENANCE,
                state="active",
            )
            .on_conflict_do_nothing()
            .returning(areas.c.id)
        ).scalar_one_or_none()
        changed |= result is not None
        area_ids[identifier] = connection.execute(
            select(areas.c.id)
            .where(
                areas.c.organization_id == organization_id,
                (areas.c.id == identifier)
                | (areas.c.normalized_name == normalize_technology_name(name)),
            )
            .order_by((areas.c.id == identifier).desc())
            .limit(1)
        ).scalar_one()
    for identifier, _code, name, _localized, area_id in TAXONOMY_CATEGORIES:
        result = connection.execute(
            insert(categories)
            .values(
                organization_id=organization_id,
                id=identifier,
                name=name,
                normalized_name=normalize_technology_name(name),
                description="",
                revision=1,
                provenance=TAXONOMY_PROVENANCE,
                state="active",
                area_id=area_ids[area_id],
            )
            .on_conflict_do_nothing()
            .returning(categories.c.id)
        ).scalar_one_or_none()
        changed |= result is not None
    return changed


def classify_seed_technologies(
    connection: Connection,
    organization_id: str,
    technology_ids: Collection[str] | None = None,
) -> bool:
    """Add functional classes to known identities; keep custom classifications.

    Existing registries may use older IDs: collision-checked canonical aliases
    resolve those identities. This never creates a technology or a usage fact.
    Passing new IDs keeps their initial revision at 1; migration updates revisions
    only for existing technologies whose classification actually changes.
    """
    technologies = table("technology", column("organization_id"), column("id"), column("revision"))
    aliases = table(
        "technology_alias",
        column("organization_id"),
        column("technology_id"),
        column("normalized_name"),
    )
    classifications = table(
        "technology_classification",
        column("organization_id"),
        column("technology_id"),
        column("category_id"),
    )
    categories = _registry("technology_category")
    category_rows = connection.execute(
        select(categories.c.id, categories.c.normalized_name).where(
            categories.c.organization_id == organization_id
        )
    ).all()
    by_name = {row.normalized_name: row.id for row in category_rows}
    present_ids = {row.id for row in category_rows}
    category_ids = {
        identifier: identifier
        if identifier in present_ids
        else by_name.get(normalize_technology_name(name))
        for identifier, _code, name, _localized, _area in TAXONOMY_CATEGORIES
    }
    seed_names = {
        normalize_technology_name(name): identifier
        for identifier, metadata in SEED_TECHNOLOGIES
        for name in (metadata.name, *metadata.aliases)
    }
    identities: dict[str, set[str]] = {}
    for technology_id, name in connection.execute(
        select(aliases.c.technology_id, aliases.c.normalized_name).where(
            aliases.c.organization_id == organization_id
        )
    ):
        if name in seed_names:
            identities.setdefault(technology_id, set()).add(seed_names[name])
    existing: dict[str, set[str]] = {}
    for technology_id, category_id in connection.execute(
        select(classifications.c.technology_id, classifications.c.category_id).where(
            classifications.c.organization_id == organization_id
        )
    ):
        existing.setdefault(technology_id, set()).add(category_id)
    query = select(technologies.c.id).where(technologies.c.organization_id == organization_id)
    if technology_ids is not None:
        query = query.where(technologies.c.id.in_(technology_ids))
    changed = False
    for technology_id in connection.scalars(query):
        # The upgrade is additive. Once functional classes exist, replay leaves
        # the owner's selection intact, including removed secondary classes.
        if existing.get(technology_id, set()) & set(category_ids.values()):
            continue
        candidates = identities.get(technology_id, set())
        if technology_id in TAXONOMY_CLASSIFICATIONS:
            seed_id = technology_id
        elif len(candidates) == 1:
            seed_id = next(iter(candidates))
        else:
            continue
        additions = [
            category_ids[key]
            for key in TAXONOMY_CLASSIFICATIONS[seed_id]
            if category_ids.get(key) and category_ids[key] not in existing.get(technology_id, set())
        ]
        if not additions:
            continue
        connection.execute(
            insert(classifications)
            .values(
                [
                    {
                        "organization_id": organization_id,
                        "technology_id": technology_id,
                        "category_id": key,
                    }
                    for key in additions
                ]
            )
            .on_conflict_do_nothing()
        )
        if technology_ids is None:
            connection.execute(
                update(technologies)
                .where(
                    technologies.c.organization_id == organization_id,
                    technologies.c.id == technology_id,
                )
                .values(revision=technologies.c.revision + 1)
            )
        changed = True
    return changed
