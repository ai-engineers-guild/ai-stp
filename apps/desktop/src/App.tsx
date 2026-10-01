import { useEffect } from "react";
import { HashRouter, NavLink, Route, Routes } from "react-router";
import {
  Home,
  ListChecks,
  Package,
  Settings,
  ShieldCheck,
  SquareTerminal,
  Wrench,
  MonitorSmartphone,
} from "lucide-react";
import { useApp } from "./store";
import OverviewPage from "./pages/OverviewPage";
import AuthPage from "./pages/AuthPage";
import CatalogPage from "./pages/CatalogPage";
import TasksPage from "./pages/TasksPage";
import InstallPage from "./pages/InstallPage";
import TargetsPage from "./pages/TargetsPage";
import RegistryPage from "./pages/RegistryPage";
import SettingsPage from "./pages/SettingsPage";

const NAV = [
  { to: "/", icon: Home, label: "Overview" },
  { to: "/auth", icon: ShieldCheck, label: "Account" },
  { to: "/catalog", icon: Package, label: "Catalog" },
  { to: "/tasks", icon: ListChecks, label: "Tasks" },
  { to: "/install", icon: Wrench, label: "Install" },
  { to: "/targets", icon: MonitorSmartphone, label: "Targets" },
  { to: "/registry", icon: SquareTerminal, label: "Commands" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export default function App() {
  const { auth, cliOk, scope, refreshAuth, refreshCli } = useApp();

  useEffect(() => {
    void refreshCli();
    void refreshAuth();
  }, [refreshCli, refreshAuth]);

  const signedIn = Boolean(
    auth && (auth.authenticated ?? auth.status === "authenticated"),
  );

  return (
    <HashRouter>
      <div className="flex h-screen bg-canvas text-ink">
        <aside className="flex w-52 shrink-0 flex-col border-r border-current/10 p-3">
          <div className="mb-4 flex items-center gap-2 px-2">
            <span className="h-2.5 w-2.5 rounded-sm bg-brand" />
            <span className="font-bold">ai-stp</span>
            <span
              className={`ml-auto h-2 w-2 rounded-full ${
                cliOk === null ? "bg-amber-400" : cliOk ? "bg-emerald-500" : "bg-red-500"
              }`}
              title={cliOk ? "CLI connected" : "CLI unavailable"}
            />
          </div>
          <nav className="flex flex-col gap-0.5">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm ${
                    isActive
                      ? "bg-brand/10 font-semibold text-brand"
                      : "opacity-70 hover:bg-black/5 dark:hover:bg-white/5"
                  }`
                }
              >
                <n.icon size={15} />
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-auto space-y-1 px-2 text-[11px] opacity-60">
            <p>scope: {scope.kind}</p>
            <p>{signedIn ? "signed in" : "signed out"}</p>
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
            <Route path="/registry" element={<RegistryPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </HashRouter>
  );
}
