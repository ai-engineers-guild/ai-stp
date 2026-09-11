import { getTranslations } from "next-intl/server";
import { Link } from "@/lib/i18n/navigation";
import { CONTEXT_SURFACES, CORPORATE_SURFACES } from "@/lib/context-surfaces";
import { hasCapability } from "@/lib/product-context";
import { contextStatus, loadProductContext } from "@/lib/product-context-server";

export default async function WorkspacePage({
  searchParams,
}: {
  searchParams: Promise<{ surface?: string }>;
}) {
  const snapshot = await loadProductContext();
  const t = await getTranslations("context");
  const selected = (await searchParams).surface;
  const requested = [...CONTEXT_SURFACES, ...CORPORATE_SURFACES].find(
    (surface) => surface.key === selected,
  );
  const contextState = contextStatus(snapshot);
  const status =
    contextState !== "ready"
      ? contextState
      : selected && (!requested || !hasCapability(snapshot.context, requested.capability))
        ? requested
          ? snapshot.context.capabilities.unavailable[requested.capability] === "unsupported"
            ? "unsupported"
            : snapshot.context.capabilities.unavailable[requested.capability] === "dependency"
              ? "unavailable"
              : "forbidden"
          : "forbidden"
        : "ready";
  const organization = snapshot.organizations.find(
    (item) => item.organization_id === snapshot.context.organization_id,
  );
  const visible = [...CONTEXT_SURFACES, ...CORPORATE_SURFACES].filter((surface) =>
    hasCapability(snapshot.context, surface.capability),
  );
  return (
    <section className="mx-auto max-w-5xl space-y-8 py-8" data-ui="context-workspace">
      <header className="space-y-2">
        <p className="text-muted-foreground font-mono text-xs uppercase">
          {t(snapshot.context.mode)}
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">{t("workspace")}</h1>
        {organization && <p data-ui="context-organization">{organization.display_name}</p>}
        <p className="text-muted-foreground max-w-2xl">{t("workspaceDescription")}</p>
      </header>
      {status !== "ready" ? (
        <p className="border-border rounded-md border p-4 text-sm">
          {t("statusMessage", { status: t(status) })}
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {visible.map((surface) => (
            <Link
              key={surface.key}
              href={surface.href}
              className="border-border hover:border-foreground/40 rounded-lg border p-5 transition-colors"
            >
              <h2 className="font-medium">
                {t(
                  CONTEXT_SURFACES.some((item) => item.key === surface.key)
                    ? "surfaces." + surface.key
                    : "corporateSurfaces." + surface.key,
                )}
              </h2>
              {CONTEXT_SURFACES.some((item) => item.key === surface.key) && (
                <p className="text-muted-foreground mt-2 text-sm">
                  {t("surfaceDescriptions." + surface.key)}
                </p>
              )}
            </Link>
          ))}
          {CORPORATE_SURFACES.filter(
            (surface) => snapshot.context.capabilities.unavailable[surface.capability],
          ).map((surface) => {
            const reason = snapshot.context.capabilities.unavailable[surface.capability];
            return (
              <div
                key={surface.key}
                data-ui="unavailable-surface"
                className="border-border rounded-lg border p-5"
              >
                <h2 className="font-medium">{t("corporateSurfaces." + surface.key)}</h2>
                <p className="text-muted-foreground mt-2 text-sm">
                  {t(
                    reason === "unsupported"
                      ? "unsupported"
                      : reason === "forbidden"
                        ? "forbidden"
                        : "unavailable",
                  )}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
