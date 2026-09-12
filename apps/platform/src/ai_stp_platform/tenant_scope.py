"""Transaction-local PostgreSQL tenant context for corporate row policies."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant_scope(session: AsyncSession, organization_id: str) -> None:
    """Set the tenant seen by FORCE RLS policies for this transaction."""
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        await session.execute(
            select(func.set_config("ai_stp.organization_id", organization_id, True))
        )


__all__ = ["set_tenant_scope"]
