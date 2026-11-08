import { Component, type ReactNode } from "react";
import { i18n } from "../i18n";

export default class PageBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section className="card space-y-4 p-6" role="alert">
        <h1 className="page-title">{i18n.t("shell.loadError")}</h1>
        <p className="page-sub">{i18n.t("shell.loadErrorHelp")}</p>
        <button
          type="button"
          className="btn-primary"
          onClick={() => window.location.reload()}
        >
          {i18n.t("shell.reopen")}
        </button>
      </section>
    );
  }
}
