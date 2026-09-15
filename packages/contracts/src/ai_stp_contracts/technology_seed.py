"""Frozen initial registry manifest (SPEC-081 REQ-8202).

Identifiers are manifest identity, not derived from mutable display names.
Never reorder or replace existing entries; a changed manifest needs a new version.
"""

from typing import Final

from ai_stp_contracts.technology import TechnologyMetadata

SEED_PROVENANCE: Final = "ai_stp:technology-seed:1"
SEED_CATEGORIES: Final = (
    ("category_00000000000000000000000001", "Language"),
    ("category_00000000000000000000000002", "Library"),
    ("category_00000000000000000000000003", "Framework"),
    ("category_00000000000000000000000004", "Runtime"),
    ("category_00000000000000000000000005", "Browser"),
    ("category_00000000000000000000000006", "Web API and standard"),
    ("category_00000000000000000000000007", "DBMS"),
    ("category_00000000000000000000000008", "Cache and key-value store"),
    ("category_00000000000000000000000009", "Message broker and event platform"),
    ("category_00000000000000000000000010", "Build and bundling tool"),
    ("category_00000000000000000000000011", "Package manager"),
    ("category_00000000000000000000000012", "Package and artifact registry"),
    ("category_00000000000000000000000013", "Test framework"),
    ("category_00000000000000000000000014", "Test runner and browser automation"),
    ("category_00000000000000000000000015", "CI/CD system"),
    ("category_00000000000000000000000016", "Job runner and execution agent"),
    ("category_00000000000000000000000017", "Container and orchestration platform"),
    ("category_00000000000000000000000018", "Operating system"),
    ("category_00000000000000000000000019", "Cloud platform and managed service"),
    ("category_00000000000000000000000020", "Web server and proxy"),
    ("category_00000000000000000000000021", "Infrastructure provisioning and configuration tool"),
    ("category_00000000000000000000000022", "Observability"),
    ("category_00000000000000000000000023", "Identity and security infrastructure"),
)

SEED_TECHNOLOGIES: Final = (
    (
        "technology_00000000000000000000000001",
        TechnologyMetadata(
            name="Bun", category_ids=[SEED_CATEGORIES[index][0] for index in (3, 9, 10, 13)]
        ),
    ),
    (
        "technology_00000000000000000000000002",
        TechnologyMetadata(name="npm CLI", category_ids=[SEED_CATEGORIES[10][0]]),
    ),
    (
        "technology_00000000000000000000000003",
        TechnologyMetadata(name="npm registry", category_ids=[SEED_CATEGORIES[11][0]]),
    ),
    (
        "technology_00000000000000000000000004",
        TechnologyMetadata(name="GitLab CI/CD", category_ids=[SEED_CATEGORIES[14][0]]),
    ),
    (
        "technology_00000000000000000000000005",
        TechnologyMetadata(name="GitLab Runner", category_ids=[SEED_CATEGORIES[15][0]]),
    ),
    (
        "technology_00000000000000000000000006",
        TechnologyMetadata(
            name="React", aliases=["React.js"], category_ids=[SEED_CATEGORIES[1][0]]
        ),
    ),
    (
        "technology_00000000000000000000000007",
        TechnologyMetadata(
            name="PostgreSQL", aliases=["Postgres"], category_ids=[SEED_CATEGORIES[6][0]]
        ),
    ),
)
