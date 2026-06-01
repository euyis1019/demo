import { useCallback, useState } from "react";

export type ViewMode = "god" | "story";

const STORAGE_KEY = "drama_demo_view_mode";

export function loadViewMode(): ViewMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "god" || raw === "story") {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return "story";
}

export function persistViewMode(mode: ViewMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function useViewMode(defaultMode: ViewMode = loadViewMode()) {
  const [viewMode, setViewModeState] = useState<ViewMode>(defaultMode);

  const setViewMode = useCallback((mode: ViewMode) => {
    setViewModeState(mode);
    persistViewMode(mode);
  }, []);

  const toggleViewMode = useCallback(() => {
    setViewMode(viewMode === "god" ? "story" : "god");
  }, [viewMode, setViewMode]);

  return { viewMode, setViewMode, toggleViewMode };
}
