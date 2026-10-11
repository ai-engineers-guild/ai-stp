import { ObjectPresentationEditorPage } from "@/components/screens/object-presentation-editor-page";

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
