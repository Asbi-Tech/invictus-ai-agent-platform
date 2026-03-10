import { useEffect, useRef, useState } from "react";
import type { WorkerProgress } from "@/lib/api";

const BASE_URL: string = import.meta.env.VITE_API_URL ?? "";

/**
 * SSE hook that streams real-time worker progress updates.
 * Connects when `isRunning` is true and disconnects when the run finishes.
 */
export function useWorkerProgress(isRunning: boolean): WorkerProgress | null {
  const [progress, setProgress] = useState<WorkerProgress | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!isRunning) {
      // Clean up any lingering connection
      esRef.current?.close();
      esRef.current = null;
      return;
    }

    const token = localStorage.getItem("token");
    if (!token) return;

    const url = `${BASE_URL}/sync/run/progress?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WorkerProgress;
        setProgress(data);

        // Auto-close on terminal states
        if (["completed", "failed", "cancelled"].includes(data.status)) {
          es.close();
          esRef.current = null;
        }
      } catch {
        // Ignore malformed events
      }
    };

    es.onerror = () => {
      // EventSource will auto-reconnect on transient errors.
      // On permanent failure it stays in CLOSED state.
      if (es.readyState === EventSource.CLOSED) {
        esRef.current = null;
      }
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [isRunning]);

  return progress;
}
