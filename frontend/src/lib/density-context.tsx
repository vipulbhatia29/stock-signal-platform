"use client";

// DensityProvider — controls screener table row density (comfortable vs compact).
// Persisted to localStorage so the preference survives page reloads.

import { createContext, useContext, useState } from "react";

type Density = "comfortable" | "compact";

interface DensityContextValue {
  density: Density;
  toggleDensity: () => void;
}

const DensityContext = createContext<DensityContextValue>({
  density: "comfortable",
  toggleDensity: () => {},
});

const STORAGE_KEY = "screener-density";

export function DensityProvider({ children }: { children: React.ReactNode }) {
  const [density, setDensity] = useState<Density>(() => {
    if (typeof window === "undefined") return "comfortable";
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "compact" ? "compact" : "comfortable";
  });

  function toggleDensity() {
    setDensity((prev) => {
      const next = prev === "comfortable" ? "compact" : "comfortable";
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }

  return (
    <DensityContext.Provider value={{ density, toggleDensity }}>
      {children}
    </DensityContext.Provider>
  );
}

export function useDensity() {
  return useContext(DensityContext);
}
