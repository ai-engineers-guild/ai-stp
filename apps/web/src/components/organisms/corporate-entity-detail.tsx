import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { AvatarImage } from "@/components/atoms/avatar-image";
import { MarkdownDescription } from "@/components/molecules/markdown-description";
import { ObjectDetailFrame } from "@/components/organisms/object-detail-frame";
import { ComponentMediaGallery } from "@/components/organisms/component-media-gallery";
import { CorporateRichEditor } from "@/components/organisms/corporate-rich-editor";
import {
  corporateReferenceHref,
  type CorporatePresentation,
  type CorporateDetailResource,
} from "@/lib/corporate-detail";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

export function CorporateEntityDetail({
  presentation,
  description,
  children,
  organizationId,
  resource,
  resourceId,
  csrfToken,
  rail,
}: {
  presentation: CorporatePresentation | null;
  description: string;
  children: ReactNode;
  organizationId: string;
  resource: CorporateDetailResource;
  resourceId: string;
  csrfToken: string;
  rail?: ReactNode;
}) {
  const t = useTranslations("account");
  const h = useTranslations("hub");
  const c = useTranslations("common");
  const catalog = useTranslations("catalog");
  const objects = useTranslations("objects");
  const corporate = useTranslations("corporate");
  const relations = presentation
    ? ([
        [h("teams"), presentation.teams],
        [h("projects"), presentation.projects],
        [h("technologies"), presentation.technologies],
        [h("teamLeads"), presentation.leads],
        [catalog("components"), presentation.components],
      ] as const)
    : [];
  return (
    <>
      {presentation?.can_edit ? (
        <CorporateRichEditor
          initial={presentation}
          organizationId={organizationId}
          resource={resource}
          resourceId={resourceId}
          csrfToken={csrfToken}
        />
      ) : null}
      <ObjectDetailFrame
        description={
          <MarkdownDescription
            source={presentation?.description ?? description}
            heading={corporate("description")}
          />
        }
        main={
          <>
            {relations.map(([title, refs]) =>
              refs.length ? (
                <section key={title} className="space-y-3">
                  <h2 className="text-xl font-medium">{title}</h2>
                  <ul className="divide-border divide-y">
                    {refs.map((ref) => (
                      <li key={`${ref.kind}:${ref.id}`}>
                        <Link
                          className="inline-flex min-h-11 items-center underline underline-offset-4"
                          href={corporateReferenceHref(ref)}
                        >
                          {ref.name}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null,
            )}
            {children}
          </>
        }
        rail={
          <>
            {presentation ? (
              <section className="border-border bg-card space-y-4 rounded-lg border p-5">
                <div className="flex items-center gap-3">
                  <AvatarImage
                    src={presentation.avatar_url}
                    width={64}
                    className="size-16 rounded-full object-cover"
                    fallback={<Icon name="user" size="lg" />}
                  />
                  <span className="min-w-0 font-medium [overflow-wrap:anywhere]">
                    {presentation.name}
                  </span>
                </div>
                {(
                  [
                    [
                      presentation.owner?.kind === "employee" ? h("operationalOwner") : h("owner"),
                      presentation.owner,
                    ],
                    [catalog("author"), presentation.author],
                  ] as const
                ).map(([label, ref]) =>
                  ref ? (
                    <div key={label} className="space-y-1">
                      <p className="text-muted-foreground text-xs">{label}</p>
                      <Link
                        href={corporateReferenceHref(ref)}
                        className="inline-flex min-h-11 items-center underline underline-offset-4"
                      >
                        {ref.name}
                      </Link>
                    </div>
                  ) : null,
                )}
                {presentation.links.length ? (
                  <ul className="border-border space-y-2 border-t pt-4">
                    {presentation.links.map((link) => (
                      <li key={link.url}>
                        <a
                          href={link.url}
                          rel="noopener noreferrer"
                          target="_blank"
                          className="inline-flex min-h-11 items-center break-all underline underline-offset-4"
                        >
                          {link.label}
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>
            ) : null}
            {presentation?.media.length ? (
              <ComponentMediaGallery
                items={presentation.media}
                labels={{
                  gallery: catalog("gallery"),
                  open: t("profilePreview"),
                  source: objects("source"),
                  close: c("cancel"),
                }}
              />
            ) : null}
            {rail}
          </>
        }
      />
    </>
  );
}
