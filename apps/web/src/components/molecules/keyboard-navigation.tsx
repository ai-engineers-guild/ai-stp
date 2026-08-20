"use client";

import { useEffect } from "react";

import { useRouter } from "@/lib/i18n/navigation";

type KeyboardNavigationProps = {
  accountHref: "/account" | "/login";
  contactEnabled: boolean;
};

function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

/** Global discoverable shortcuts. Single-letter keys never fire while typing. */
export function KeyboardNavigation({ accountHref, contactEnabled }: KeyboardNavigationProps) {
  const router = useRouter();

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target) || event.altKey) return;

      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        router.push("/catalog");
        return;
      }
      if (event.ctrlKey || event.metaKey || event.shiftKey) return;

      const key = event.key.toLowerCase();
      if (contactEnabled && key === "c") router.push("/contact");
      if (key === "p") router.push(accountHref);
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [accountHref, contactEnabled, router]);

  return null;
}
