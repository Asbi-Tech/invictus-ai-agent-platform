import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, WorkerRunHistory } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckCircle2, XCircle, Ban, Clock, ChevronRight } from "lucide-react";

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

function formatDate(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-red-500" />;
    case "cancelled":
      return <Ban className="h-4 w-4 text-yellow-500" />;
    case "running":
      return <Clock className="h-4 w-4 text-blue-500 animate-spin" />;
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
}

function StatusBadge({ status }: { status: string }) {
  const variant =
    status === "completed"
      ? "default"
      : status === "failed"
        ? "destructive"
        : "secondary";
  return (
    <Badge variant={variant} className="text-[10px] px-1.5 py-0 capitalize">
      {status}
    </Badge>
  );
}

const RunHistory = () => {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const [runs, setRuns] = useState<WorkerRunHistory[]>([]);
  const [fetching, setFetching] = useState(false);

  useEffect(() => {
    if (!user) return;
    setFetching(true);
    api
      .getRunHistory(50)
      .then(setRuns)
      .catch(() => null)
      .finally(() => setFetching(false));
  }, [user]);

  useEffect(() => {
    if (!isLoading && !user) navigate("/");
  }, [isLoading, user, navigate]);

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-4xl px-6 pt-24 pb-16">
        <h1 className="font-heading text-3xl font-semibold text-foreground">
          Run History
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Pipeline run history with per-file classification details.
        </p>

        <div className="mt-8 space-y-2">
          {fetching &&
            Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg" />
            ))}

          {!fetching && runs.length === 0 && (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No pipeline runs yet. Start a run from the Dashboard.
            </p>
          )}

          {runs.map((run) => (
            <button
              key={run.id}
              onClick={() => navigate(`/runs/${run.id}`)}
              className="group flex w-full items-center justify-between rounded-lg border border-border bg-card px-5 py-3.5 text-left transition-colors hover:bg-muted/50"
            >
              <div className="flex items-center gap-3">
                <StatusIcon status={run.status} />
                <div>
                  <span className="text-sm font-medium text-foreground">
                    Run #{run.id}
                  </span>
                  <span className="ml-3 text-xs text-muted-foreground">
                    {formatDate(run.started_at)}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-4">
                {run.progress_data?.new_files_found != null && (
                  <span className="text-xs text-muted-foreground">
                    {run.progress_data.new_files_found} files
                  </span>
                )}
                {run.progress_data?.persisted != null && (
                  <span className="text-xs text-muted-foreground">
                    {run.progress_data.persisted} persisted
                  </span>
                )}
                <span className="text-xs text-muted-foreground">
                  {formatDuration(run.started_at, run.finished_at)}
                </span>
                <StatusBadge status={run.status} />
                <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
            </button>
          ))}
        </div>
      </main>
    </div>
  );
};

export default RunHistory;
