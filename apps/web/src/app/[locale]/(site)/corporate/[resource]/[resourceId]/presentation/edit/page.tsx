import CorporatePresentationEditContent from "../edit-content";
export default function PresentationEditPage({
  params,
}: {
  params: Promise<{ locale: string; resource: string; resourceId: string }>;
}) {
  return <CorporatePresentationEditContent params={params} />;
}
