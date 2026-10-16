import RegistryPage from "./RegistryPage";
export default function DiscoveryPage() {
  return (
    <RegistryPage
      title="Discovery"
      description="Inspect local projects and sources before choosing or creating a setup."
      prefixes={[
        "component discover",
        "project discover",
        "project index",
        "project symbols",
        "source",
        "component source",
      ]}
    />
  );
}
