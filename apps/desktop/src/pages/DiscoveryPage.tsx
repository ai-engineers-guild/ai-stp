import { useText } from "../i18n";
import RegistryPage from "./RegistryPage";
export default function DiscoveryPage() {
  const msg = useText();
  return (
    <RegistryPage
      title={msg("shell.discovery")}
      description={msg(
        "discovery.inspectLocalProjectsAndSourcesBeforeChoosingOrCreating",
      )}
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
