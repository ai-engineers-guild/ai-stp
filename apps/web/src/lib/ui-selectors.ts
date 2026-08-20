/**
 * Stable public selectors for tests, browser automation and support tooling.
 *
 * Prefer `data-ui` over classes or copy. IDs are reserved for document landmarks,
 * form controls and anchor targets where browser semantics benefit from them.
 */
export const UI = {
  shell: {
    root: "site-shell",
    header: "site-header",
    primaryNav: "primary-navigation",
    main: "main-content",
    footer: "site-footer",
    footerNav: "footer-navigation",
  },
  navigation: {
    home: "nav-home",
    catalog: "nav-catalog",
    services: "nav-services",
    docs: "nav-docs",
    content: "nav-content",
    objects: "nav-objects",
    access: "nav-access",
    reports: "nav-reports",
    devices: "nav-devices",
    contact: "nav-contact",
    account: "nav-account",
    locale: "locale-select",
    shortcuts: "keyboard-shortcuts",
  },
  theme: {
    toggle: "color-theme-toggle",
  },
  projection: {
    toggle: "human-machine-toggle",
    human: "projection-human",
    machine: "projection-machine",
  },
  machine: {
    header: "machine-header",
    index: "machine-site-index",
    projection: "machine-page-projection",
    footer: "machine-footer",
    locale: "machine-locale-select",
  },
  contact: {
    page: "contact-page",
    form: "contact-form",
    name: "contact-name",
    email: "contact-email",
    subject: "contact-subject",
    message: "contact-message",
    submit: "contact-submit",
  },
  landing: {
    page: "landing-page",
    preview: "landing-workflow-preview",
  },
  services: {
    page: "regional-services-page",
    hero: "regional-services-hero",
    filters: "regional-services-filters",
    results: "regional-services-results",
  },
  catalog: {
    page: "catalog-page",
    search: "catalog-search",
    filters: "catalog-filters",
    results: "catalog-results",
    card: "catalog-object-card",
    usage: "catalog-usage-metrics",
  },
  component: {
    detailHeader: "component-detail-header",
    actions: "component-actions",
    overflow: "component-overflow",
    mediaGallery: "component-media-gallery",
    mediaLightbox: "component-media-lightbox",
    relationships: "component-relationships",
    descriptionMedia: "component-description-media",
    detailLower: "component-detail-lower",
    detailMain: "component-detail-main",
    detailRail: "component-detail-rail",
    passport: "component-passport",
    install: "component-install",
    contextBudget: "catalog-context-budget",
    profileForm: "profile-form",
  },
  primitive: {
    button: "ui-button",
    badge: "ui-badge",
    input: "ui-input",
    textarea: "ui-textarea",
    dialog: "ui-dialog",
    statePanel: "state-panel",
  },
} as const;

export type UiSelector = string;

export function uiSelector(value: UiSelector): string {
  return `[data-ui="${value}"]`;
}
