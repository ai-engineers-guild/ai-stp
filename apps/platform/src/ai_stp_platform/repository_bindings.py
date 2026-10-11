"""Read repository sources from CLI links and explicit corporate bindings."""

from sqlalchemy import select, union
from sqlalchemy.sql.selectable import Subquery

from ai_stp_platform.organization_models import CorporateRepositoryBinding, ProjectLink


def repository_links() -> Subquery:
    """One source projection; CLI synchronization remains device-bound."""
    fields = ("organization_id", "remote_project_id", "provider_project_id", "state")
    return union(
        select(*(getattr(ProjectLink, field) for field in fields)),
        select(*(getattr(CorporateRepositoryBinding, field) for field in fields)),
    ).subquery()
