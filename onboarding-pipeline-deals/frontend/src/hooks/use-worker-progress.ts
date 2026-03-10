import { useCallback, useEffect, useRef, useState } from "react";
import { api, WorkerProgress } from "@/lib/api";

const BASE_URL: string = import.meta.env.VITE_API_URL ?? "";

/**
 * Self-contained SSE hook for worker progress.
 *
 * On mount (and when `refresh()` is called), checks `/sync/status` to see
 * if a run is active. If so, opens an SSE connection for real-time updates.
 * On unmount (navigation away), the SSE connection is closed. On remount
 * (navigation back), it re-checks the server and reconnects automatically.
 */
export function useWorkerProgress(): {
  progress: WorkerProgress | null;
  isRunning: boolean;
  refresh: () => void;
} {
  const [progress, setProgress] = useState<WorkerProgress | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [trigger, setTrigger] = useState(0);
  const esRef = useRef<EventSource | null>(null);
  const cancelledRef = useRef(false);

  const refresh = useCallback(() => setTrigger((t) => t + 1), []);

  useEffect(() => {
    cancelledRef.current = false;

    function connectSSE() {
      esRef.current?.close();
      const token = localStorage.getItem("token");
      if (!token) return;

      const url = `${BASE_URL}/sync/run/progress?token=${encodeURIComponent(token)}`;
      const es = new EventSource(url);
      esRef.current = es;

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WorkerProgress;
          setProgress(data);

          if (["completed", "failed", "cancelled"].includes(data.status)) {
            setIsRunning(false);
            es.close();
            esRef.current = null;
          }
        } catch {
          // Ignore malformed events
        }
      };

      es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) {
          esRef.current = null;
          // SSE closed unexpectedly — re-check server state after a delay
          if (!cancelledRef.current) {
            setTimeout(() => {
              if (!cancelledRef.current) checkAndConnect();
            }, 3000);
          }
        }
      };
    }

    async function checkAndConnect() {
      try {
        const status = await api.getSyncStatus();
        if (cancelledRef.current) return;

        if (status.is_running) {
          setIsRunning(true);
          connectSSE();
        } else {
          setIsRunning(false);
          setProgress(null);
          esRef.current?.close();
          esRef.current = null;
        }
      } catch {
        // ignore — will retry on next trigger/mount
      }
    }

    checkAndConnect();

    return () => {
      cancelledRef.current = true;
      esRef.current?.close();
      esRef.current = null;
    };
  }, [trigger]);

  return { progress, isRunning, refresh };
}
