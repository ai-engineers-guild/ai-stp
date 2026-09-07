import { getTranslations, setRequestLocale } from "next-intl/server";
import { StatePanel } from "@/components/molecules/state-panel";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { ObjectPresentationForm } from "@/components/organisms/object-presentation-form";
import { ExternalProductManager } from "@/components/organisms/external-product-manager";
import { listExternalProducts, type ExternalProduct } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/errors";
import { readOwnerExternalProducts, readOwnerPresentation } from "@/lib/api/owner";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
export async function ObjectPresentationEditorPage({
  locale,
  objectKind,
  stableId,
}: {
  locale: string;
  objectKind: "component" | "setup";
  stableId: string;
}) {
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/objects/${objectKind}/${stableId}/edit`);
  const t = await getTranslations("objects");
  const tc = await getTranslations("common");
  const token = (await sessionCookieValue()) ?? "";
  let presentation;
  let allProducts: { schema_version: 1; items: ExternalProduct[] } = {
    schema_version: 1,
    items: [],
  };
  let attachedProducts: { schema_version: 1; items: ExternalProduct[] } = {
    schema_version: 1,
    items: [],
  };
  try {
    if (process.env.NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED === "false") {
      presentation = await readOwnerPresentation(token, stableId, objectKind);
    } else {
      [presentation, allProducts, attachedProducts] = await Promise.all([
        readOwnerPresentation(token, stableId, objectKind),
        listExternalProducts(),
        readOwnerExternalProducts(token, objectKind, stableId),
      ]);
    }
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
      return <StatePanel kind="error" title={tc("notFound")} description={t("notFound")} />;
    }
    throw error;
  }
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <HistoryBackButton
        label={t("backToObjects")}
        fallback={`/objects/${objectKind}/${stableId}`}
      />
      <header className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("editPresentation")}</h1>
        <p className="text-muted-foreground">{t("editPresentationNote")}</p>
      </header>
      <ObjectPresentationForm
        objectKind={objectKind}
        locale={locale}
        stableId={stableId}
        csrfToken={(await readCsrfToken()) ?? ""}
        initialBio={presentation.bio}
        initialMedia={presentation.media}
        afterMedia={
          process.env.NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED !== "false" ? (
            <ExternalProductManager
              locale={locale}
              objectKind={objectKind}
              stableId={stableId}
              csrfToken={(await readCsrfToken()) ?? ""}
              initialProducts={allProducts.items}
              selectedDomains={attachedProducts.items.map((item) => item.canonical_domain)}
            />
          ) : undefined
        }
        labels={{
          bio: t("bio"),
          media: t("media"),
          addMedia: t("addMedia"),
          remove: t("removeMedia"),
          kind: t("mediaKind"),
          url: t("mediaUrl"),
          alt: t("mediaAlt"),
          caption: t("mediaCaption"),
          save: t("savePresentation"),
          saving: t("savingPresentation"),
          saved: t("presentationSaved"),
          help: t("mediaHelp"),
          upload: t("mediaUpload"),
          uploading: t("mediaUploading"),
          requirements: t("mediaRequirements"),
          youtubeHint: t("mediaYoutubeHint"),
          githubHint: t("mediaGithubHint"),
          youtubePlaceholder: t("mediaYoutubePlaceholder"),
          githubPlaceholder: t("mediaGithubPlaceholder"),
          invalid: t("mediaInvalid"),
          uploadFailed: t("mediaUploadFailed"),
          unsupportedType: t("mediaUnsupportedType"),
          sizeExceeded: t("mediaSizeExceeded"),
          saveFailed: t("presentationSaveFailed"),
          preview: t("mediaPreview"),
          uploadInProgress: t("mediaUploadInProgress"),
          uploadRequired: t("mediaUploadRequired"),
          retryUpload: t("mediaRetryUpload"),
          replaceUpload: t("mediaReplaceUpload"),
          sourceUpload: t("mediaSourceUpload"),
          sourceGithub: t("mediaSourceGithub"),
          sourceYoutube: t("mediaSourceYoutube"),
          sourceChoice: t("mediaSourceChoice"),
          sourceUrl: t("mediaSourceUrl"),
          urlHint: t("mediaUrlHint"),
          urlPlaceholder: t("mediaUrlPlaceholder"),
          uploadedReady: t("mediaUploadedReady"),
          uploadError: t("mediaUploadError"),
          itemStatusIdle: t("mediaItemStatusIdle"),
          itemStatusUploading: t("mediaItemStatusUploading"),
          itemStatusReady: t("mediaItemStatusReady"),
          itemStatusError: t("mediaItemStatusError"),
          altRequired: t("mediaAltRequired"),
          kindImage: t("mediaKindImage"),
          kindVideo: t("mediaKindVideo"),
          kindYoutube: t("mediaKindYoutube"),
          mediaCount: t("mediaCount", { count: "{count}", max: "{max}" }),
        }}
      />
    </div>
  );
}
