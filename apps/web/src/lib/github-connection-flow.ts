const POLL_TIMEOUT_MS = 2 * 60 * 1000;

export function openGitHubConnectionWindow(): Window | null {
  return window.open(
    "about:blank",
    "ai-stp-github-connection",
    "popup,width=600,height=760,resizable=yes,scrollbars=yes",
  );
}

export function navigateGitHubConnectionWindow(popup: Window | null, url: string): void {
  if (popup && !popup.closed) {
    popup.location.replace(url);
    popup.focus();
    return;
  }
  window.location.assign(url);
}

export function watchGitHubConnection(
  popup: Window | null,
  check: () => Promise<boolean>,
  onConnected: () => void,
): () => void {
  let active = true;
  let inFlight = false;
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let timer: number | null = null;

  const stop = () => {
    active = false;
    if (timer !== null) window.clearInterval(timer);
  };

  const poll = async () => {
    if (!active || inFlight) return;
    if (Date.now() >= deadline) {
      stop();
      return;
    }
    inFlight = true;
    try {
      if (await check()) {
        stop();
        if (popup && !popup.closed) popup.close();
        onConnected();
      }
    } finally {
      inFlight = false;
    }
  };

  timer = window.setInterval(() => void poll(), 1000);
  void poll();
  return stop;
}
