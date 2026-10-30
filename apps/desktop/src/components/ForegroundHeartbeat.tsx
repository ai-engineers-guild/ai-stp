import { useEffect } from "react";
import { useContexts } from "../contexts";
import { foregroundHeartbeat } from "../heartbeat";

// Serialize foreground passes across context changes and component remounts.
let inFlight: Promise<void> | null = null;
export default function ForegroundHeartbeat() {
  const context = useContexts((state) => state.selected);
  const loading = useContexts((state) => state.loading || state.switching);
  useEffect(() => {
    let active = true;
    const current = () => active && !loading && document.visibilityState === "visible" && document.hasFocus() &&
      useContexts.getState().selected?.id === context?.id && !useContexts.getState().loading && !useContexts.getState().switching;
    const tick = () => {
      if (inFlight || !current()) return;
      inFlight = foregroundHeartbeat(context, current).catch(() => {}).finally(() => { inFlight = null; });
    };
    tick();
    const interval = window.setInterval(tick, 60000);
    document.addEventListener("visibilitychange", tick);
    window.addEventListener("focus", tick);
    return () => {
      active = false;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", tick);
      window.removeEventListener("focus", tick);
    };
  }, [context?.id, loading]);
  return null;
}
