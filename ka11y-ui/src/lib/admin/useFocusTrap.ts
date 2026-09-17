"use client";

import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

export function getFocusable(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => el.getAttribute("aria-hidden") !== "true" && el.getClientRects().length > 0,
  );
}

interface FocusTrapOptions {
  onEscape?: () => void;
  /** Element to focus on open; defaults to the first focusable descendant. */
  initialFocus?: RefObject<HTMLElement | null>;
}

/**
 * Keeps Tab / Shift+Tab inside `ref` while `active`, closes on Escape, and
 * returns focus to whatever was focused before it opened (WCAG 2.4.3 / 2.1.2).
 * The rest of the page should be marked `inert` by the caller so pointer and
 * AT focus cannot leave either.
 */
export function useFocusTrap(ref: RefObject<HTMLElement | null>, active: boolean, options: FocusTrapOptions = {}) {
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  });

  useEffect(() => {
    if (!active) return;
    if (!ref.current) return;
    // Hoisted function declarations below do not see the null-check narrowing.
    const root: HTMLElement = ref.current;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const frame = requestAnimationFrame(() => {
      const initial = optionsRef.current.initialFocus?.current ?? getFocusable(root)[0] ?? root;
      initial.focus();
    });

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        optionsRef.current.onEscape?.();
        return;
      }
      if (event.key !== "Tab") return;
      const items = getFocusable(root);
      if (items.length === 0) {
        event.preventDefault();
        root.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const current = document.activeElement as HTMLElement | null;
      const inside = current !== null && root.contains(current);
      if (event.shiftKey && (current === first || !inside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (current === last || !inside)) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [active, ref]);
}

/**
 * Closes a non-modal popover/menu on Escape or on a pointer press outside
 * `ref`. Escape also hands focus back to `returnTo` so the keyboard user is
 * not dropped at the top of the page.
 */
export function useDismissable(
  open: boolean,
  onClose: () => void,
  ref: RefObject<HTMLElement | null>,
  returnTo?: RefObject<HTMLElement | null>,
) {
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) onCloseRef.current();
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        returnTo?.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, ref, returnTo]);
}
