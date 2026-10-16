import RegistryPage from "./RegistryPage";
export default function TargetsPage() {
  return (
    <RegistryPage
      title="Configuration targets"
      description="Inspect installed harnesses and manage their configurations. Harness executables stay under your control."
      prefixes={["configuration", "program", "provider"]}
    />
  );
}
