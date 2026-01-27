import { useEffect, useState } from "react";
import { DEMO_DATA_KEY } from "./api";

const parseDemoParam = () => {
  const params = new URLSearchParams(window.location.search);
  const value = params.get("demo");
  if (value == null) return null;
  const normalized = String(value).toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return null;
};

export function useDemoData() {
  const initialFromUrl = parseDemoParam();
  const [enabled, setEnabled] = useState(() => {
    if (initialFromUrl !== null) {
      return initialFromUrl;
    }
    return localStorage.getItem(DEMO_DATA_KEY) === "true";
  });

  useEffect(() => {
    localStorage.setItem(DEMO_DATA_KEY, enabled ? "true" : "false");
  }, [enabled]);

  return { enabled, setEnabled };
}
