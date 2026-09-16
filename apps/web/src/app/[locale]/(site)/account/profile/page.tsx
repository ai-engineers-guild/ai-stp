import { redirect } from "next/navigation";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function AccountProfilePage({ params }: PageProps) {
  const { locale } = await params;
  redirect(`/${locale}/account/profile/edit`);
}
