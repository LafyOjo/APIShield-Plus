import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "./api";

const emptyState = {
  tours_completed: [],
  tours_dismissed: [],
};

export function useTour(tourKey, tenantKey) {
  const [state, setState] = useState(emptyState);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const autoStarted = useRef(false);

  const loadState = useCallback(async () => {
    if (!tenantKey) {
      setState(emptyState);
      setOpen(false);
      return;
    }
    setLoading(true);
    try {
      const resp = await apiFetch("/api/v1/users/tours", { skipReauth: true });
      if (!resp.ok) {
        throw new Error("Unable to load tour state");
      }
      const data = await resp.json();
      setState({
        tours_completed: Array.isArray(data?.tours_completed)
          ? data.tours_completed
          : [],
        tours_dismissed: Array.isArray(data?.tours_dismissed)
          ? data.tours_dismissed
          : [],
      });
    } catch (err) {
      setState(emptyState);
    } finally {
      setLoading(false);
      autoStarted.current = false;
    }
  }, [tenantKey]);

  useEffect(() => {
    loadState();
  }, [loadState]);

  useEffect(() => {
    if (loading || !tenantKey || autoStarted.current) return;
    const completed = state.tours_completed || [];
    const dismissed = state.tours_dismissed || [];
    if (!completed.includes(tourKey) && !dismissed.includes(tourKey)) {
      autoStarted.current = true;
      setOpen(true);
    }
  }, [loading, state, tourKey, tenantKey]);

  const updateState = useCallback(
    async (payload) => {
      if (!tenantKey) return null;
      const resp = await apiFetch("/api/v1/users/tours", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        return null;
      }
      const data = await resp.json();
      setState({
        tours_completed: Array.isArray(data?.tours_completed)
          ? data.tours_completed
          : [],
        tours_dismissed: Array.isArray(data?.tours_dismissed)
          ? data.tours_dismissed
          : [],
      });
      return data;
    },
    [tenantKey]
  );

  const complete = useCallback(async () => {
    await updateState({ complete: [tourKey] });
    setOpen(false);
  }, [tourKey, updateState]);

  const dismiss = useCallback(async () => {
    await updateState({ dismiss: [tourKey] });
    setOpen(false);
  }, [tourKey, updateState]);

  const restart = useCallback(async () => {
    await updateState({ reset: [tourKey] });
    autoStarted.current = true;
    setOpen(true);
  }, [tourKey, updateState]);

  const start = useCallback(() => {
    autoStarted.current = true;
    setOpen(true);
  }, []);

  return {
    open,
    start,
    restart,
    complete,
    dismiss,
    state,
  };
}
