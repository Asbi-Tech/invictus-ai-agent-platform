import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Play, Square, ChevronDown, ChevronUp, Clock, CheckCircle2, XCircle, Ban } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/context/AuthContext";
import { api, WorkerRunHistory } from "@/lib/api";
import { useWorkerProgress } from "@/hooks/use-worker-progress";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";

// ── Stage label mapping ──────────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  pending: "Starting pipeline...",
  discovering_files: "Scanning Google Drive...",
  downloading: "Downloading files...",
  analyzing: "Classifying documents...",
  persisting: "Saving results...",
  version_management: "Managing versions...",
  vectorizing: "Vectorizing deals...",
};

const STATUS_LABELS: Record<string, string> = {
  not_connected: "Not Connected",
  no_folder: "No Folder Set",
  processing: "Processing",
  idle: "Up to Date",
};

// ── Stage ordering for progress bar ──────────────────────────────────────

const STAGE_ORDER = [
  "discovering_files",
  "downloading",
  "analyzing",
  "persisting",
  "version_management",
  "vectorizing",
];

function stageProgress(stage: string | null): number {
  if (!stage) return 0;
  const idx = STAGE_ORDER.indexOf(stage);
  if (idx < 0) return 0;
  return Math.round(((idx + 1) / STAGE_ORDER.length) * 100);
}

// ── Stats display helpers ────────────────────────────────────────────────

interface DocumentStats {
  total_validated: number;
  shortlisted: number;
  archived: number;
  knowledge_base: number;
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return "-";
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const secs = Math.round((end - start) / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const remSecs = secs % 60;
  if (mins < 60) return `${mins}m ${remSecs}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

function formatTimeAgo(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}

// ── Main component ───────────────────────────────────────────────────────

const SyncStatusCard = () => {
  const { user } = useAuth();

  // Sync status
  const [syncStatus, setSyncStatus] = useState<{
    status: string;
    next_sync: string;
    is_running: boolean;
    active_run_id: number | null;
  } | null>(null);
  const [stats, setStats] = useState<DocumentStats | null>(null);

  // Run state
  const [isStarting, setIsStarting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [elapsedTimer, setElapsedTimer] = useState<number>(0);

  // History
  const [history, setHistory] = useState<WorkerRunHistory[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  // SSE progress
  const progress = useWorkerProgress(isRunning);

  // ── Fetch initial status ────────────────────────────────────────────────

  const refreshStatus = useCallback(async () => {
    if (!user) return;
    try {
      const s = await api.getSyncStatus();
      setSyncStatus(s);
      setIsRunning(s.is_running);
    } catch {
      // ignore
    }
  }, [user]);

  useEffect(() => {
    refreshStatus();
    api.getDocumentStats().then(setStats).catch(() => null);
  }, [refreshStatus]);

  // ── Elapsed timer during run ────────────────────────────────────────────

  useEffect(() => {
    if (!isRunning) {
      setElapsedTimer(0);
      return;
    }
    const t0 = Date.now();
    const interval = setInterval(() => {
      setElapsedTimer(Math.round((Date.now() - t0) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [isRunning]);

  // ── Watch for run completion via SSE ────────────────────────────────────

  useEffect(() => {
    if (!progress) return;
    if (progress.status === "completed") {
      setIsRunning(false);
      toast.success("Pipeline completed successfully");
      refreshStatus();
      api.getDocumentStats().then(setStats).catch(() => null);
      loadHistory();
    } else if (progress.status === "failed") {
      setIsRunning(false);
      toast.error("Pipeline run failed");
      refreshStatus();
      loadHistory();
    } else if (progress.status === "cancelled") {
      setIsRunning(false);
      toast("Pipeline run was cancelled");
      refreshStatus();
      loadHistory();
    }
  }, [progress?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── History ─────────────────────────────────────────────────────────────

  const loadHistory = useCallback(async () => {
    try {
      const h = await api.getRunHistory(10);
      setHistory(h);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // ── Actions ─────────────────────────────────────────────────────────────

  const handleStart = async () => {
    setIsStarting(true);
    try {
      await api.startPipelineRun();
      setIsRunning(true);
      toast.success("Pipeline started");
      refreshStatus();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to start";
      toast.error(message);
    } finally {
      setIsStarting(false);
    }
  };

  const handleCancel = async () => {
    setIsCancelling(true);
    try {
      await api.cancelPipelineRun();
      toast("Cancellation requested...");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to cancel";
      toast.error(message);
    } finally {
      setIsCancelling(false);
    }
  };

  // ── Render helpers ──────────────────────────────────────────────────────

  const statusLabel = syncStatus
    ? (STATUS_LABELS[syncStatus.status] ?? syncStatus.status)
    : "Yet to Sync";

  const stageLabel = progress?.stage
    ? (STAGE_LABELS[progress.stage] ?? progress.stage)
    : STAGE_LABELS["pending"];

  const progressPct = stageProgress(progress?.stage ?? null);

  const progressData = progress?.data ?? {};

  const formatElapsed = (secs: number) => {
    if (secs < 60) return `${secs}s`;
    const m = Math.floor(secs / 60);
    return `${m}m ${secs % 60}s`;
  };

  // ── Build stats rows ───────────────────────────────────────────────────

  const statRows: { label: string; value: number | string }[] = stats
    ? [
        { label: "Total Documents Validated", value: stats.total_validated },
        { label: "Documents Shortlisted", value: stats.shortlisted },
        { label: "Documents Archived", value: stats.archived },
        { label: "Added to Knowledge Base", value: stats.knowledge_base },
      ]
    : [];

  return (
    <motion.section
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.6 }}
      className="flex flex-col items-center px-6 py-12"
    >
      <div className="w-full max-w-lg rounded-lg border border-border bg-card p-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-2xl font-semibold text-foreground">
            Pipeline
          </h2>
          {!isRunning ? (
            <Button
              size="sm"
              onClick={handleStart}
              disabled={isStarting || !syncStatus || syncStatus.status === "not_connected"}
              className="gap-1.5"
            >
              <Play className="h-3.5 w-3.5" />
              {isStarting ? "Starting..." : "Run Pipeline"}
            </Button>
          ) : (
            <Button
              size="sm"
              variant="destructive"
              onClick={handleCancel}
              disabled={isCancelling}
              className="gap-1.5"
            >
              <Square className="h-3.5 w-3.5" />
              {isCancelling ? "Cancelling..." : "Cancel"}
            </Button>
          )}
        </div>

        {/* Status indicator */}
        {!isRunning && (
          <div className="mt-4 flex items-center gap-3">
            <span className="relative flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-pulse-gold rounded-full bg-primary opacity-75" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-primary" />
            </span>
            <span className="text-sm font-medium text-muted-foreground">{statusLabel}</span>
          </div>
        )}

        {/* ── Running: progress display ─────────────────────────────── */}
        {isRunning && (
          <div className="mt-5 space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-foreground">{stageLabel}</span>
              <span className="text-muted-foreground">{formatElapsed(elapsedTimer)}</span>
            </div>

            <Progress value={progressPct} className="h-2" />

            {/* Progress counters */}
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {progressData.files_found != null && (
                <span>Files found: <span className="text-foreground font-medium">{progressData.files_found}</span></span>
              )}
              {progressData.downloaded != null && (
                <span>Downloaded: <span className="text-foreground font-medium">{progressData.downloaded}</span></span>
              )}
              {progressData.analyzed != null && (
                <span>Analyzed: <span className="text-foreground font-medium">{progressData.analyzed}</span></span>
              )}
              {progressData.persisted != null && (
                <span>Persisted: <span className="text-foreground font-medium">{progressData.persisted}</span></span>
              )}
              {progressData.deals_to_vectorize != null && (
                <span>Deals to vectorize: <span className="text-foreground font-medium">{progressData.deals_to_vectorize}</span></span>
              )}
              {progressData.download_failed != null && progressData.download_failed > 0 && (
                <span className="text-red-400">Failed: {progressData.download_failed}</span>
              )}
            </div>
          </div>
        )}

        {/* ── Idle: stats ───────────────────────────────────────────── */}
        {!isRunning && statRows.length > 0 && (
          <div className="mt-4 space-y-2 border-t border-border pt-4 text-sm">
            {statRows.map((row) => (
              <div key={row.label} className="flex justify-between">
                <span className="text-muted-foreground">{row.label}</span>
                <span className="font-medium text-foreground">{row.value}</span>
              </div>
            ))}
          </div>
        )}

        {/* Next sync */}
        {!isRunning && (
          <div className="mt-4 flex items-center justify-between border-t border-border pt-4">
            <span className="text-xs text-muted-foreground">Next Sync</span>
            <span className="text-sm font-medium text-foreground">
              {syncStatus?.next_sync ?? "02:00 AM"}
            </span>
          </div>
        )}

        {/* ── Run history ───────────────────────────────────────────── */}
        {history.length > 0 && (
          <div className="mt-4 border-t border-border pt-4">
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="flex w-full items-center justify-between text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <span>Run History ({history.length})</span>
              {showHistory ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>

            {showHistory && (
              <div className="mt-3 space-y-2">
                {history.map((run) => (
                  <div
                    key={run.id}
                    className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-2 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <RunStatusIcon status={run.status} />
                      <span className="text-muted-foreground">
                        {formatTimeAgo(run.started_at)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      {run.progress_data?.persisted != null && (
                        <span className="text-muted-foreground">
                          {run.progress_data.new_files_found ?? run.progress_data.persisted} files
                        </span>
                      )}
                      <span className="text-muted-foreground">
                        {formatDuration(run.started_at, run.finished_at)}
                      </span>
                      <RunStatusBadge status={run.status} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </motion.section>
  );
};

function RunStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />;
    case "failed":
      return <XCircle className="h-3.5 w-3.5 text-red-500" />;
    case "cancelled":
      return <Ban className="h-3.5 w-3.5 text-yellow-500" />;
    case "running":
      return <Clock className="h-3.5 w-3.5 text-blue-500 animate-spin" />;
    default:
      return <Clock className="h-3.5 w-3.5 text-muted-foreground" />;
  }
}

function RunStatusBadge({ status }: { status: string }) {
  const variant =
    status === "completed"
      ? "default"
      : status === "failed"
        ? "destructive"
        : "secondary";

  return (
    <Badge variant={variant} className="text-[10px] px-1.5 py-0">
      {status}
    </Badge>
  );
}

export default SyncStatusCard;
