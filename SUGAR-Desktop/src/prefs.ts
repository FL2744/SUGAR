import { useCallback, useEffect, useState } from "react";

export type Prefs = {
  mode: "basic" | "advanced";
  debug: boolean;
  density: "comfortable" | "compact";
  textScale: number;          // 0.85 – 1.5, multiplies the base font size (OS scaling still applies on top)
  interpreter: "auto" | "deterministic";
};

export const DEFAULT_PREFS: Prefs = { mode: "basic", debug: false, density: "comfortable", textScale: 1, interpreter: "auto" };
const KEY = "sugar.prefs.v1";

export function loadPrefs(): Prefs {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULT_PREFS;
    return normalizePrefs({ ...DEFAULT_PREFS, ...(JSON.parse(raw) as Partial<Prefs>) });
  } catch {
    return DEFAULT_PREFS;
  }
}

export function normalizePrefs(prefs: Prefs): Prefs {
  return {
    mode: prefs.mode === "advanced" ? "advanced" : "basic",
    debug: Boolean(prefs.debug),
    density: prefs.density === "compact" ? "compact" : "comfortable",
    textScale: Math.min(1.5, Math.max(0.85, Number(prefs.textScale) || 1)),
    interpreter: prefs.interpreter === "deterministic" ? "deterministic" : "auto",
  };
}

export function savePrefs(prefs: Prefs): boolean {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(normalizePrefs(prefs)));
    return true;
  } catch {
    return false;
  }
}

/** Apply interface preferences to the document. OS display scaling is handled by the browser; textScale is on top of it. */
export function applyPrefs(prefs: Prefs): void {
  const root = document.documentElement;
  root.style.fontSize = `${Math.round(16 * prefs.textScale * 100) / 100}px`;
  root.dataset.density = prefs.density;
  root.dataset.mode = prefs.mode;
}

export function usePrefs(): [Prefs, (next: Prefs) => boolean] {
  const [prefs, setPrefs] = useState<Prefs>(() => loadPrefs());
  useEffect(() => applyPrefs(prefs), [prefs]);
  const commit = useCallback((next: Prefs) => {
    const normalized = normalizePrefs(next);
    setPrefs(normalized);
    return savePrefs(normalized);
  }, []);
  return [prefs, commit];
}
