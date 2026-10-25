import { useEffect, useState } from "react";
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
  MonitorSmartphone,
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
import OverviewPage from "./pages/OverviewPage";
import AuthPage from "./pages/AuthPage";
import ProfilesPage from "./pages/ProfilesPage";
import CorporatePage from "./pages/CorporatePage";
import CatalogPage from "./pages/CatalogPage";
import TasksPage from "./pages/TasksPage";
import InstallPage from "./pages/InstallPage";
import TargetsPage from "./pages/TargetsPage";
import DiscoveryPage from "./pages/DiscoveryPage";
import RegistryPage from "./pages/RegistryPage";
import DebugPage from "./pages/DebugPage";
import SettingsPage from "./pages/SettingsPage";

const GROUPS = [
  {
    label: "Workspace",
    items: [
      { to: "/", icon: Home, label: "Overview" },
      { to: "/catalog", icon: Package, label: "Catalog" },
      { to: "/corporate", icon: Building2, label: "Company" },
      { to: "/install", icon: Wrench, label: "Setups" },
      { to: "/tasks", icon: ListChecks, label: "Activity" },
    ],
  },
  {
    label: "Tools",
    items: [
      { to: "/targets", icon: MonitorSmartphone, label: "Targets" },
      { to: "/discover", icon: Radar, label: "Discovery" },
      { to: "/registry", icon: SquareTerminal, label: "Commands" },
    ],
  },
  {
    label: "System",
    items: [
      { to: "/auth", icon: ShieldCheck, label: "Account" },
      { to: "/profiles", icon: ShieldCheck, label: "Connections" },
      { to: "/settings", icon: Settings, label: "Settings" },
      { to: "/debug", icon: Bug, label: "Diagnostics" },
    ],
  },
];

function Shell() {
  const context = useContexts((state) => state.selected);
  const { auth, cliOk, cliVersion, refreshAuth, refreshCli } = useApp();
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
  return (
    <div className="app-shell">
      <a
        href="#main-content"
        className="skip-link"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        Skip to content
      </a>
      <aside className="app-sidebar">
        <NavLink to="/" className="brand" aria-label="ai-stp home">
          <span className="brand-mark">
            <SquareTerminal size={20} />
          </span>
          <span>
            <strong>ai-stp</strong>
            <span className="brand-caption">Your agent workspace</span>
          </span>
        </NavLink>
        <ContextSwitcher />
        <nav aria-label="Main navigation" className="sidebar-nav">
          {GROUPS.map((group) => (
            <div key={group.label} className="nav-group">
              <p className="eyebrow">{group.label}</p>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) =>
                    `nav-item ${isActive ? "nav-active" : ""}`
                  }
                >
                  <item.icon size={17} aria-hidden="true" />
                  <span>{item.label}</span>
                  {item.to === "/debug" && failures > 0 && (
                    <span className="ml-auto text-xs text-destructive">
                      {failures}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="engine-status">
            <Activity
              size={15}
              aria-hidden="true"
              className={cliOk ? "text-success" : "text-muted-foreground"}
            />
            <span>
              {cliOk === null
                ? "Connecting to engine"
                : cliOk
                  ? `Rust CLI ${cliVersion ?? ""}`
                  : "Engine unavailable"}
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
                ? "Context account"
                : signedIn
                  ? "Account connected"
                  : "Connect account"}
              <ArrowUpRight size={13} />
            </NavLink>
            <button
              className="icon-button"
              onClick={toggleTheme}
              aria-label={dark ? "Use light theme" : "Use dark theme"}
            >
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </div>
      </aside>
      <main id="main-content" tabIndex={-1} className="app-main">
        <div className="page-container">
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
