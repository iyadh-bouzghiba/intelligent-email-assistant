import { useEffect, useRef, ReactNode } from 'react';

const FOCUSABLE_SELECTORS = [
  'a[href]:not([tabindex="-1"])',
  'button:not([disabled]):not([tabindex="-1"])',
  'input:not([disabled]):not([tabindex="-1"])',
  'select:not([disabled]):not([tabindex="-1"])',
  'textarea:not([disabled]):not([tabindex="-1"])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

function getFocusable(container: HTMLElement | null): HTMLElement[] {
  if (!container) return [];
  return Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS)
  ).filter((el) => !el.closest('[aria-hidden="true"]') && el.offsetParent !== null);
}

interface FocusTrapProps {
  children: ReactNode;
  /** CSS selector for the element to receive initial focus. Defaults to first focusable child. */
  initialFocusSelector?: string;
}

/**
 * Traps keyboard focus inside its children while mounted.
 * Saves the previously focused element and restores it on unmount.
 * Uses `display: contents` so it has zero layout impact.
 */
export function FocusTrap({ children, initialFocusSelector }: FocusTrapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previousFocusRef.current = document.activeElement as HTMLElement;
    const container = containerRef.current;
    if (!container) return;

    // Delay focus by one frame so Framer Motion entrance animations settle first
    const focusTimer = setTimeout(() => {
      const target = initialFocusSelector
        ? container.querySelector<HTMLElement>(initialFocusSelector)
        : getFocusable(container)[0];
      target?.focus();
    }, 50);

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Tab') return;
      const focusable = getFocusable(container);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      clearTimeout(focusTimer);
      document.removeEventListener('keydown', handleKeyDown);
      // Restore focus to whatever triggered the modal
      previousFocusRef.current?.focus();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // `contents` makes this div layout-invisible while still being a real DOM node
  // that querySelectorAll can traverse.
  return (
    <div ref={containerRef} className="contents">
      {children}
    </div>
  );
}
