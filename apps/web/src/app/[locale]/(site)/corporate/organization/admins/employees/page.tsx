import CorporateAdministrationPage from "../page";

export default function EmployeeAccessPage(props: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  return <CorporateAdministrationPage {...props} accessView />;
}
