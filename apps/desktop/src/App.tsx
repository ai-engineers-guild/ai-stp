import { lazy, Suspense, useEffect, useState, type ComponentType } from "react";
import {
  HashRouter,
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
} from "react-router";
import {
  Activity,
  Building2,
  ArrowUpRight,
  Bug,
  Home,
  ListChecks,
  Moon,
  Package,
  Radar,
  Settings,
  ShieldCheck,
  SquareTerminal,
  Sun,
  Wrench,
} from "lucide-react";
import { useApp, useDebug } from "./store";
import { readPreference, writePreference } from "./preferences";
import { useContexts } from "./contexts";
import ContextSwitcher from "./components/ContextSwitcher";
import ForegroundHeartbeat from "./components/ForegroundHeartbeat";
import OverviewPage from "./pages/OverviewPage";
import {
  i18n,
  loadCatalog,
  useText,
  type MessageKey,
  type Locale,
} from "./i18n";
import LanguageSelect from "./components/LanguageSelect";
import { Spinner } from "./components/Result";
import PageBoundary from "./components/PageBoundary";

function page(load: () => Promise<{ default: ComponentType }>) {
  return lazy(async () => {
    const [module] = await Promise.all([
      load(),
      loadCatalog(i18n.resolvedLanguage as Locale),
    ]);
    return module;
  });
}
const AuthPage = page(() => import("./pages/AuthPage"));
const ProfilesPage = page(() => import("./pages/ProfilesPage"));
const CorporatePage = page(() => import("./pages/CorporatePage"));
const CatalogPage = page(() => import("./pages/CatalogPage"));
const TasksPage = page(() => import("./pages/TasksPage"));
const InstallPage = page(() => import("./pages/InstallPage"));
const TargetsPage = page(() => import("./pages/TargetsPage"));
const DiscoveryPage = page(() => import("./pages/DiscoveryPage"));
const RegistryPage = page(() => import("./pages/RegistryPage"));
const DebugPage = page(() => import("./pages/DebugPage"));
const SettingsPage = page(() => import("./pages/SettingsPage"));

const PRIMARY = [
  { to: "/", icon: Home, label: "shell.home" },
  { to: "/catalog", icon: Package, label: "shell.catalog" },
  { to: "/targets", icon: Wrench, label: "shell.setups" },
  { to: "/tasks", icon: ListChecks, label: "shell.activity" },
] as const;
const ACCOUNT = [
  { to: "/corporate", icon: Building2, label: "shell.company" },
  { to: "/auth", icon: ShieldCheck, label: "shell.account" },
  { to: "/profiles", icon: ShieldCheck, label: "shell.connections" },
  { to: "/settings", icon: Settings, label: "shell.settings" },
] as const;
const ADVANCED = [
  { to: "/discover", icon: Radar, label: "shell.discovery" },
  { to: "/registry", icon: SquareTerminal, label: "shell.commands" },
  { to: "/debug", icon: Bug, label: "shell.diagnostics" },
] as const;

function Shell() {
  const t = useText();
  const context = useContexts((state) => state.selected);
  const { auth, cliOk, refreshAuth, refreshCli } = useApp();
  const failures = useDebug(
    (s) => s.log.filter((entry) => entry.ok !== true).length,
  );
  const [dark, setDark] = useState(
    document.documentElement.classList.contains("dark"),
  );
  const location = useLocation();
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const saved = readPreference("ai-stp.theme");
      const next = saved ? saved === "dark" : mq.matches;
      document.documentElement.classList.toggle("dark", next);
      setDark(next);
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
  useEffect(() => {
    void refreshCli();
    void refreshAuth();
  }, [refreshCli, refreshAuth]);
  useEffect(() => {
    document.getElementById("main-content")?.scrollTo(0, 0);
  }, [location.pathname]);
  const session = auth?.session as Record<string, unknown> | undefined;
  const signedIn =
    session?.state === "authorized" && session.access_expired !== true;
  function toggleTheme() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    writePreference("ai-stp.theme", next ? "dark" : "light");
  }
  function navigation(
    items: readonly { to: string; icon: typeof Home; label: MessageKey }[],
  ) {
    return items.map((item) => (
      <NavLink
        key={item.to}
        to={item.to}
        end={item.to === "/"}
        className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`}
      >
        <item.icon size={17} aria-hidden="true" />
        <span>{t(item.label)}</span>
        {item.to === "/debug" && failures > 0 && (
          <span className="ms-auto text-xs text-destructive">{failures}</span>
        )}
      </NavLink>
    ));
  }
  return (
    <div className="app-shell">
      <ForegroundHeartbeat />
      <a
        href="#main-content"
        className="skip-link"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        {t("shell.skip")}
      </a>
      <aside className="app-sidebar">
        <NavLink to="/" className="brand">
          <span className="brand-mark">
            <SquareTerminal size={20} aria-hidden="true" />
          </span>
          <span>
            <strong>ai-stp</strong>
            <span className="brand-caption">{t("shell.caption")}</span>
          </span>
        </NavLink>
        <ContextSwitcher />
        <nav aria-label={t("shell.navigation")} className="sidebar-nav">
          <div className="nav-group">{navigation(PRIMARY)}</div>
          <div className="nav-group">{navigation(ACCOUNT)}</div>
          <details
            className="nav-group"
            open={
              ADVANCED.some((item) => item.to === location.pathname) ||
              undefined
            }
          >
            <summary className="nav-item">{t("shell.advanced")}</summary>
            {navigation(ADVANCED)}
          </details>
        </nav>
        <div className="sidebar-footer">
          <LanguageSelect compact />
          <div className="engine-status">
            <Activity
              size={15}
              aria-hidden="true"
              className={cliOk ? "text-success" : "text-muted-foreground"}
            />
            <span>
              {cliOk === null
                ? t("shell.connecting")
                : cliOk
                  ? t("shell.ready")
                  : t("shell.offline")}
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <NavLink
              to={
                context?.connection
                  ? `/auth?connection=${encodeURIComponent(context.connection)}`
                  : "/auth"
              }
              className="account-link"
            >
              {context?.connection
                ? t("shell.contextAccount")
                : signedIn
                  ? t("shell.accountConnected")
                  : t("shell.connectAccount")}
              <ArrowUpRight size={13} />
            </NavLink>
            <button
              className="icon-button"
              onClick={toggleTheme}
              aria-label={dark ? t("shell.light") : t("shell.dark")}
            >
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </div>
      </aside>
      <main id="main-content" tabIndex={-1} className="app-main">
        <div className="page-container">
          <PageBoundary key={location.pathname}>
            <Suspense fallback={<Spinner label={t("common.loading")} />}>
              <Routes>
                <Route path="/" element={<OverviewPage />} />
                <Route path="/auth" element={<AuthPage />} />
                <Route path="/profiles" element={<ProfilesPage />} />
                <Route path="/corporate" element={<CorporatePage />} />
                <Route path="/catalog" element={<CatalogPage />} />
                <Route path="/tasks" element={<TasksPage />} />
                <Route path="/install" element={<InstallPage />} />
                <Route path="/targets" element={<TargetsPage />} />
                <Route path="/discover" element={<DiscoveryPage />} />
                <Route path="/registry" element={<RegistryPage />} />
                <Route path="/debug" element={<DebugPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </PageBoundary>
        </div>
      </main>
    </div>
  );
}
export default function App() {
  return (
    <HashRouter>
      <Shell />
    </HashRouter>
  );
}
