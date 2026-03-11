import { type RefObject, useState, useEffect } from "react";

/**
 * Returns the current pixel width of a DOM element via ResizeObserver.
 * Starts at 160px (a safe minimum card width) and updates on the first
 * ResizeObserver callback immediately after mount.
 * We intentionally do NOT read ref.current in the useState initializer —
 * that would violate the react-hooks/refs lint rule which forbids ref reads
 * during render.
 */
export function useContainerWidth(
  ref: RefObject<HTMLDivElement | null>
): number {
  const [width, setWidth] = useState(160);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(entry.contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);

  return width;
}
