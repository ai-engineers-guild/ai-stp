"use client";

import { useSyncExternalStore } from "react";

/** Nothing to subscribe to: the answer changes once, when React hydrates. */
const noSubscription = () => () => {};

/**
 * Whether this render is running after hydration.
 *
 * Several components render one thing on the server and another once the
 * client knows something the server did not — the resolved theme, whether a
 * session cookie is present, what the viewport is. The first client render has
 * to match the server byte for byte or React discards the tree, so those
 * components need to know which render they are in.
 *
 * The idiom for that used to be a mount flag:
 *
 * ```tsx
 * const [mounted, setMounted] = useState(false);
 * useEffect(() => { setMounted(true); }, []);
 * ```
 *
 * It works, and it costs a second render pass on every mount to carry one bit
 * that `useSyncExternalStore` can answer directly — `false` from the server
 * snapshot, `true` from the client one, with no state written from an effect.
 * `eslint-plugin-react-hooks` 7 flags the effect version as a cascading render,
 * and it is right: eight components here paid that cost.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    noSubscription,
    () => true,
    () => false,
  );
}
