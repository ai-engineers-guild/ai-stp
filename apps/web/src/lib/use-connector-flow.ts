"use client";

import { useEffect, useRef, useState, useTransition } from "react";

import {
  navigateConnectionWindow,
  openConnectionWindow,
  watchConnection,
} from "@/lib/connection-flow";

export type ConnectorPurpose = "source" | "administration";

export type ConnectorStatusShape = {
  connections: ReadonlyArray<{ purpose: string; state: string; configured: boolean }>;
};

export type ConnectorResult<T> = { ok: true; data: T } | { ok: false; code: string };

/**
 * Shared connector state machine: status polling, popup OAuth window,
 * plan/busy bookkeeping. Provider connectors keep only their deltas.
 */
export function useConnectorFlow<
  S extends ConnectorStatusShape,
  A extends unknown[] = [],
>(options: {
  fetchStatus: () => Promise<ConnectorResult<S>>;
  requestConnect: (
    purpose: ConnectorPurpose,
    ...args: A
  ) => Promise<ConnectorResult<{ authorization_url: string }>>;
  /** Re-fetch identity: status is reloaded whenever these inputs change. */
  deps: readonly unknown[];
}) {
  const [status, setStatus] = useState<S | null>(null);
  const [error, setError] = useState("");
  const [busy, start] = useTransition();
  const stopPolling = useRef<(() => void) | null>(null);
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  });

  function run<T>(
    request: () => Promise<ConnectorResult<T>>,
    done: (data: T) => void,
    failed?: () => void,
  ) {
    setError("");
    start(async () => {
      const result = await request();
      if (result.ok) done(result.data);
      else {
        setError(result.code);
        failed?.();
      }
    });
  }

  function refresh() {
    void optionsRef.current
      .fetchStatus()
      .then((result) => {
        if (result.ok) setStatus(result.data);
        else setError(result.code);
      })
      .catch(() => {
        setError("unavailable");
      });
  }

  function connect(purpose: ConnectorPurpose, ...args: A) {
    const popup = openConnectionWindow();
    run(
      () => optionsRef.current.requestConnect(purpose, ...args),
      (result) => {
        navigateConnectionWindow(popup, result.authorization_url);
        stopPolling.current?.();
        stopPolling.current = watchConnection(
          popup,
          async () => {
            const current = await optionsRef.current.fetchStatus();
            if (!current.ok) {
              setError(current.code);
              return false;
            }
            setStatus(current.data);
            return current.data.connections.some((item) => item.state === "connected");
          },
          refresh,
        );
      },
      () => popup?.close(),
    );
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh reads the latest options through a ref; callers declare the re-fetch inputs.
  useEffect(refresh, options.deps);
  useEffect(() => () => stopPolling.current?.(), []);

  const source = status?.connections.find((item) => item.purpose === "source") as
    S["connections"][number] | undefined;
  const admin = status?.connections.find((item) => item.purpose === "administration") as
    S["connections"][number] | undefined;

  return {
    status,
    setStatus,
    error,
    busy,
    run,
    connect,
    refresh,
    source,
    admin,
    connected: source?.state === "connected",
  };
}
