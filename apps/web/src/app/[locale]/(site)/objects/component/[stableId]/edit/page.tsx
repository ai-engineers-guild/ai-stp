import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { ObjectPresentationForm } from "@/components/organisms/object-presentation-form";
import { ApiError } from "@/lib/api/errors";
import { readOwnerPresentation } from "@/lib/api/owner";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function EditComponentPresentationPage({
  params,
}: {
  params: Promise<{ locale: string; stableId: string }>;
}) {
  const { locale, stableId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/objects/component/${stableId}/edit`);
  const t = await getTranslations("objects");
  const tc = await getTranslations("common");
  const token = (await sessionCookieValue()) ?? "";
  let presentation;
  try {
    presentation = await readOwnerPresentation(token, stableId);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
      return <StatePanel kind="error" title={tc("notFound")} description={t("notFound")} />;
    }
    throw error;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <HistoryBackButton label={t("backToObjects")} fallback={`/objects/component/${stableId}`} />
      <header className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("editPresentation")}</h1>
        <p className="text-muted-foreground">{t("editPresentationNote")}</p>
      </header>
      <ObjectPresentationForm
        locale={locale}
        stableId={stableId}
        csrfToken={(await readCsrfToken()) ?? ""}
        initialBio={presentation.bio}
        initialMedia={presentation.media}
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
          uploadedReady: t("mediaUploadedReady"),
          uploadError: t("mediaUploadError"),
          itemStatusIdle: t("mediaItemStatusIdle"),
          itemStatusUploading: t("mediaItemStatusUploading"),
          itemStatusReady: t("mediaItemStatusReady"),
          itemStatusError: t("mediaItemStatusError"),
          altRequired: t("mediaAltRequired"),
          mediaCount: t("mediaCount"),
          kindImage: t("mediaKindImage"),
          kindVideo: t("mediaKindVideo"),
          kindYoutube: t("mediaKindYoutube"),
        }}
      />
    </div>
  );
}
