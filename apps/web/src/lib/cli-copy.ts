/**
 * Web surface for the generated CLI copy contract.
 * Templates live in ai_stp_contracts.cli_copy; this file only re-exports.
 */
export {
  COMPONENT_NEXT_STEP,
  DISTRIBUTION,
  INITIALIZE_PROMPT,
  INITIALIZE_START,
  INSTALL_CLI,
  INTENTS_BOOTSTRAP,
  LOGIN,
  REGISTRY_SHOW,
  REGISTRY_VERSION,
  SELECT_IMPACT,
  SETUP_NEXT_STEP,
  login,
  objectKindFromId,
  ownerComponentNextStep,
  ownerSetupNextStep,
  installStart,
  installSetupStart,
  installTaskStart,
  registryCommand,
  registryShow,
  registryVersion,
  selectImpact,
  type LoginProvider,
  type ObjectKind,
} from "@/lib/generated/cli-copy";
