import { useEffect } from "react";
import { HashRouter, Navigate, NavLink, Route, Routes } from "react-router";
import {
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
import OverviewPage from "./pages/OverviewPage";
import AuthPage from "./pages/AuthPage";
import CatalogPage from "./pages/CatalogPage";
import TasksPage from "./pages/TasksPage";
import InstallPage from "./pages/InstallPage";
import TargetsPage from "./pages/TargetsPage";
import DiscoveryPage from "./pages/DiscoveryPage";
import RegistryPage from "./pages/RegistryPage";
import DebugPage from "./pages/DebugPage";
import SettingsPage from "./pages/SettingsPage";

const NAV = [
  { to: "/", icon: Home, label: "Overview" },
  { to: "/auth", icon: ShieldCheck, label: "Account" },
  { to: "/catalog", icon: Package, label: "Catalog" },
  { to: "/tasks", icon: ListChecks, label: "Tasks" },
  { to: "/install", icon: Wrench, label: "Install" },
  { to: "/targets", icon: MonitorSmartphone, label: "Targets" },
  { to: "/discover", icon: Radar, label: "Discovery" },
  { to: "/registry", icon: SquareTerminal, label: "Commands" },
  { to: "/debug", icon: Bug, label: "Debug" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export default function App() {
  const { auth, cliOk, refreshAuth, refreshCli } = useApp();
  const { debugMode, setDebugMode, log } = useDebug();

  useEffect(() => {
    // Color theme: an explicit saved choice wins; otherwise follow the OS.
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const saved = localStorage.getItem("ai-stp.theme");
      document.documentElement.classList.toggle(
        "dark",
        saved ? saved === "dark" : mq.matches,
      );
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    void refreshCli();
    void refreshAuth();
  }, [refreshCli, refreshAuth]);

  const signedIn = auth?.state === "authenticated";
  const failures = log.filter((e) => e.ok === false || e.ok === null).length;

  function toggleTheme() {
    const dark = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("ai-stp.theme", dark ? "dark" : "light");
  }

  return (
    <HashRouter>
      <div className="flex h-screen bg-background text-foreground">
        <aside className="flex w-52 shrink-0 flex-col border-r border-border">
          <div className="mb-2 flex items-center gap-2 px-4 pt-4">
            <span className="h-2.5 w-2.5 rounded-[2px] bg-primary" />
            <span className="font-mono text-sm font-medium">ai-stp-desktop</span>
            <span
              className={`ml-auto h-2 w-2 rounded-full ${
                cliOk === null ? "bg-warning" : cliOk ? "bg-success" : "bg-destructive"
              }`}
              title={cliOk ? "CLI connected" : "CLI unavailable"}
            />
          </div>
          <nav className="flex flex-col px-2 py-2">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) =>
                  `relative flex items-center gap-2.5 rounded-sm px-3 py-2 text-sm transition-colors hover:bg-accent ${
                    isActive ? "font-medium text-primary" : "text-foreground"
                  }`
                }
              >
                <n.icon size={15} />
                {n.label}
                {n.to === "/debug" && failures > 0 && (
                  <span className="ml-auto rounded-md bg-destructive/15 px-1.5 font-mono text-[10px] text-destructive">
                    {failures}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>
          <div className="mt-auto space-y-1 border-t border-border px-4 py-3">
            <div className="flex items-center justify-between">
              <p className="font-mono text-[11px] text-muted-foreground">
                {signedIn ? "signed in" : "signed out"}
              </p>
              <button
                onClick={toggleTheme}
                className="rounded-sm p-1 text-muted-foreground hover:bg-accent"
                title="Toggle light/dark"
              >
                <Sun size={13} className="hidden dark:block" />
                <Moon size={13} className="dark:hidden" />
              </button>
            </div>
            <label className="flex cursor-pointer items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
              <input
                type="checkbox"
                checked={debugMode}
                onChange={(e) => setDebugMode(e.target.checked)}
                className="h-3 w-3 accent-primary"
              />
              debug trace
            </label>
          </div>
        </aside>
        <main className="flex-1 overflow-auto p-6">
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/auth" element={<AuthPage />} />
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
        </main>
      </div>
    </HashRouter>
  );
}
