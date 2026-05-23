import { useEffect, useRef, type RefObject } from "react";

/** F4-3 — scroll container to bottom when deps change. */
export function useAutoScroll<T>(deps: T[]): RefObject<HTMLDivElement | null> {
  const anchorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    anchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, deps);

  return anchorRef;
}
