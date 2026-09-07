import { ObjectPresentationEditorPage } from "@/components/organisms/object-presentation-editor-page";

export default async function EditComponentPresentationPage({
  params,
}: {
  params: Promise<{ locale: string; stableId: string }>;
}) {
  const { locale, stableId } = await params;
  return (
    <ObjectPresentationEditorPage locale={locale} objectKind="component" stableId={stableId} />
  );
}
