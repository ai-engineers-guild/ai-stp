function observeNavigation(route, title) {
  const key = "__aiStpNavigationTiming";
  window[key]?.dispose();

  let settled = false;
  let frame = null;
  let timeout = null;
  let finish;
  let refuse;
  const promise = new Promise((resolve, reject) => {
    finish = resolve;
    refuse = reject;
  });
  promise.catch(() => {});
  const expected = "#/" + route;

  const cleanup = () => {
    document.removeEventListener("click", clicked, true);
    if (frame !== null) cancelAnimationFrame(frame);
    if (timeout !== null) clearTimeout(timeout);
  };
  const fail = (message) => {
    if (settled) return;
    settled = true;
    cleanup();
    refuse(new Error(message));
  };
  const ready = () =>
    (location.hash === expected || (expected === "#/" && location.hash === "")) &&
    document.querySelector("main h1")?.textContent === title &&
    !document.querySelector('section[aria-label="Context view"] select')?.disabled;

  function clicked(event) {
    const link =
      event.target instanceof Element
        ? event.target.closest('nav[aria-label="Main navigation"] a[href]')
        : null;
    if (link?.getAttribute("href") !== expected) return;
    if (!event.isTrusted) {
      fail("Navigation timing requires an actual trusted click");
      return;
    }
    const started = performance.now();
    document.removeEventListener("click", clicked, true);
    const inspect = () => {
      if (settled) return;
      if (!ready()) {
        frame = requestAnimationFrame(inspect);
        return;
      }
      document.fonts.ready.then(() => {
        if (settled) return;
        frame = requestAnimationFrame(() => {
          if (settled) return;
          frame = requestAnimationFrame(() => {
            if (settled) return;
            if (!ready()) {
              frame = requestAnimationFrame(inspect);
              return;
            }
            const rendererMs = performance.now() - started;
            if (!Number.isFinite(rendererMs) || rendererMs <= 0) {
              fail("Renderer timing is not finite and positive");
              return;
            }
            settled = true;
            cleanup();
            finish({ route, trusted: true, renderer_ms: rendererMs });
          });
        });
      }, () => fail("Font readiness observation failed"));
    };
    inspect();
  }

  window[key] = {
    route,
    promise,
    dispose: () => fail("Navigation timing was superseded"),
  };
  document.addEventListener("click", clicked, true);
  timeout = setTimeout(() => fail("Navigation timing deadline"), 30000);
  return true;
}
