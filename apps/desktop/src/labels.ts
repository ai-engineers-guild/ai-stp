import type { MessageKey, useText } from "./i18n";

type Text = ReturnType<typeof useText>;
const choices: Record<string, MessageKey> = {
  install: "choice.install",
  update: "choice.update",
  remove: "choice.remove",
  replace: "choice.replace",
  inactive: "choice.inactive",
  stopped: "choice.stopped",
  running: "choice.running",
  unknown: "choice.unknown",
  global: "choice.global",
  user_root: "choice.userRoot",
  user: "choice.user",
  project: "choice.project",
  instruction: "choice.instruction",
  skill: "choice.skill",
  mcp: "choice.mcp",
  hook: "choice.hook",
  command: "choice.command",
  agent: "choice.agent",
  plugin: "choice.plugin",
  setting: "choice.setting",
  cli: "choice.cli",
  personal: "choice.personal",
  corporate: "choice.corporate",
  human: "choice.human",
  external: "choice.external",
};
const intents: Record<string, MessageKey> = {
  inspect: "intent.inspect",
  initialize: "intent.initialize",
  install: "install.installASetup",
  change: "intent.change",
  author: "install.createFromFiles",
  switch: "intent.switch",
  account: "intent.account",
  publish: "intent.publish",
  technology: "intent.technology",
};
const guidance: Record<string, MessageKey> = {
  install: "intent.installHelp",
  author: "intent.authorHelp",
};

/** Known labels are localized; unknown wire values remain inspectable data. */
export function choiceLabel(text: Text, value: string): string {
  return choices[value] ? text(choices[value]) : value;
}
export function intentLabel(text: Text, value: string): string {
  return intents[value] ? text(intents[value]) : value;
}
export function intentGuidance(
  text: Text,
  value: string,
  original?: string,
): string | undefined {
  return guidance[value] ? text(guidance[value]) : original;
}
