import { useEffect, useState, useMemo } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, RunDetailResponse, RunFileDetail } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Search, ExternalLink, CheckCircle2, XCircle, Ban, Clock, ChevronLeft, ChevronRight } from "lucide-react";

// ── Constants ────────────────────────────────────────────────────────────

const TYPE_LABELS: Record<string, string> = {
  pitch_deck: "Pitch Deck",
  investment_memo: "Investment Memo",
  prescreening_report: "Pre-screening",
  meeting_minutes: "Meeting Minutes",
  due_diligence_report: "Due Diligence",
  password_protected: "Locked",
  other: "Other",
};

const TYPE_COLORS: Record<string, string> = {
  pitch_deck: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  investment_memo: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  prescreening_report: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  meeting_minutes: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  due_diligence_report: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  password_protected: "bg-red-500/10 text-red-400 border-red-500/20",
  other: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
};

const STATUS_COLORS: Record<string, string> = {
  processed: "bg-green-500/10 text-green-400 border-green-500/20",
  vectorized: "bg-green-500/10 text-green-400 border-green-500/20",
  skipped: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  pending: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
  failed: "bg-red-500/10 text-red-400 border-red-500/20",
};

// ── Helpers ──────────────────────────────────────────────────────────────

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
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function driveUrl(fileId: string) {
  return `https://drive.google.com/file/d/${fileId}/view`;
}

function RunStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return <CheckCircle2 className="h-5 w-5 text-green-500" />;
    case "failed":
      return <XCircle className="h-5 w-5 text-red-500" />;
    case "cancelled":
      return <Ban className="h-5 w-5 text-yellow-500" />;
    case "running":
      return <Clock className="h-5 w-5 text-blue-500 animate-spin" />;
    default:
      return <Clock className="h-5 w-5 text-muted-foreground" />;
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
    <Badge variant={variant} className="capitalize">
      {status}
    </Badge>
  );
}

// ── Filter types ─────────────────────────────────────────────────────────

const DOC_TYPE_FILTERS = [
  "pitch_deck",
  "investment_memo",
  "prescreening_report",
  "meeting_minutes",
  "due_diligence_report",
  "password_protected",
  "other",
] as const;

const STATUS_FILTERS = ["processed", "vectorized", "skipped", "pending", "failed"] as const;

const PAGE_SIZE = 15;

// ── Main component ───────────────────────────────────────────────────────

const RunDetail = () => {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const { runId } = useParams<{ runId: string }>();
  const [data, setData] = useState<RunDetailResponse | null>(null);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);

  // Pagination
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!user || !runId) return;
    setFetching(true);
    api
      .getRunDetail(Number(runId))
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setFetching(false));
  }, [user, runId]);

  useEffect(() => {
    if (!isLoading && !user) navigate("/");
  }, [isLoading, user, navigate]);

  const filtered = useMemo(() => {
    if (!data) return [];
    let files = data.files;
    if (query) {
      const q = query.toLowerCase();
      files = files.filter(
        (f) =>
          f.file_name.toLowerCase().includes(q) ||
          (f.deal_name?.toLowerCase().includes(q) ?? false) ||
          (f.folder_path?.toLowerCase().includes(q) ?? false)
      );
    }
    if (typeFilter) {
      files = files.filter((f) => f.doc_type === typeFilter);
    }
    if (statusFilter) {
      files = files.filter((f) => f.status === statusFilter);
    }
    return files;
  }, [data, query, typeFilter, statusFilter]);

  // Reset page when filters change
  useEffect(() => setPage(1), [query, typeFilter, statusFilter]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const run = data?.run;
  const pd = run?.progress_data;

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-6xl px-6 pt-24 pb-16">
        {/* Back link */}
        <Link
          to="/runs"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors mb-6"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Runs
        </Link>

        {/* Loading */}
        {fetching && (
          <div className="space-y-4">
            <Skeleton className="h-10 w-64" />
            <Skeleton className="h-6 w-96" />
            <Skeleton className="h-96 w-full rounded-lg" />
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="py-12 text-center text-sm text-red-400">{error}</p>
        )}

        {/* Content */}
        {!fetching && run && (
          <>
            {/* Header */}
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <RunStatusIcon status={run.status} />
                <div>
                  <h1 className="font-heading text-3xl font-semibold text-foreground">
                    Run #{run.id}
                  </h1>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {formatDate(run.started_at)}
                    {run.finished_at && (
                      <span className="ml-2">
                        ({formatDuration(run.started_at, run.finished_at)})
                      </span>
                    )}
                  </p>
                </div>
              </div>
              <RunStatusBadge status={run.status} />
            </div>

            {/* Error message */}
            {run.error_message && (
              <div className="mt-4 rounded-md border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-400">
                {run.error_message}
              </div>
            )}

            {/* Summary stats */}
            {pd && (
              <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
                <StatCard label="Files Found" value={pd.new_files_found ?? 0} />
                <StatCard label="Persisted" value={pd.persisted ?? 0} />
                <StatCard
                  label="Skipped"
                  value={(pd.skipped_client ?? 0) + (pd.skipped_other ?? 0)}
                />
                <StatCard label="Superseded" value={pd.superseded ?? 0} />
              </div>
            )}

            {/* Files table */}
            <div className="mt-8">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <h2 className="font-heading text-lg font-medium text-foreground">
                  Files ({filtered.length}
                  {data.files.length !== filtered.length
                    ? ` of ${data.files.length}`
                    : ""}
                  )
                </h2>
                <div className="relative w-full sm:w-64">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search files..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    className="pl-9 h-9"
                  />
                </div>
              </div>

              {/* Type filters */}
              <div className="mt-3 flex flex-wrap gap-1.5">
                <FilterChip
                  label="All Types"
                  active={typeFilter === null}
                  onClick={() => setTypeFilter(null)}
                />
                {DOC_TYPE_FILTERS.map((t) => (
                  <FilterChip
                    key={t}
                    label={TYPE_LABELS[t] ?? t}
                    active={typeFilter === t}
                    onClick={() => setTypeFilter(typeFilter === t ? null : t)}
                  />
                ))}
              </div>

              {/* Status filters */}
              <div className="mt-2 flex flex-wrap gap-1.5">
                <FilterChip
                  label="All Statuses"
                  active={statusFilter === null}
                  onClick={() => setStatusFilter(null)}
                />
                {STATUS_FILTERS.map((s) => (
                  <FilterChip
                    key={s}
                    label={s}
                    active={statusFilter === s}
                    onClick={() =>
                      setStatusFilter(statusFilter === s ? null : s)
                    }
                  />
                ))}
              </div>

              {/* Table */}
              <div className="mt-4 overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/30">
                      <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">
                        File
                      </th>
                      <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">
                        Type
                      </th>
                      <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">
                        Status
                      </th>
                      <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">
                        Deal
                      </th>
                      <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">
                        Folder
                      </th>
                      <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">
                        Summary
                      </th>
                      <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">
                        Date
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.length === 0 && (
                      <tr>
                        <td
                          colSpan={7}
                          className="px-4 py-8 text-center text-muted-foreground"
                        >
                          {data.files.length === 0
                            ? "No files in this run (run may predate per-file tracking)."
                            : "No files match your filters."}
                        </td>
                      </tr>
                    )}
                    {paginated.map((f) => (
                      <FileRow key={f.id} file={f} />
                    ))}
                  </tbody>
                </table>
                {/* Pagination */}
                {filtered.length > PAGE_SIZE && (
                  <div className="flex items-center justify-between border-t border-border px-4 py-3">
                    <p className="text-sm text-muted-foreground">
                      Showing {(page - 1) * PAGE_SIZE + 1}&ndash;{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
                    </p>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={page === 1}
                        onClick={() => setPage((p) => p - 1)}
                      >
                        <ChevronLeft className="h-4 w-4 mr-1" />
                        Previous
                      </Button>
                      <span className="text-sm text-muted-foreground">
                        {page} / {totalPages}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={page >= totalPages}
                        onClick={() => setPage((p) => p + 1)}
                      >
                        Next
                        <ChevronRight className="h-4 w-4 ml-1" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
};

// ── Sub-components ───────────────────────────────────────────────────────

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs transition-colors capitalize ${
        active
          ? "border-primary bg-primary/10 text-primary"
          : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/30"
      }`}
    >
      {label}
    </button>
  );
}

function FileRow({ file }: { file: RunFileDetail }) {
  const typeColor = TYPE_COLORS[file.doc_type] ?? TYPE_COLORS.other;
  const statusColor = STATUS_COLORS[file.status] ?? STATUS_COLORS.pending;

  return (
    <tr className="border-b border-border/50 hover:bg-muted/30 transition-colors">
      <td className="px-4 py-2.5 max-w-[300px]">
        <a
          href={driveUrl(file.file_id)}
          target="_blank"
          rel="noopener noreferrer"
          className="group inline-flex items-start gap-1.5 text-foreground hover:text-primary transition-colors"
        >
          <span className="break-all leading-snug">{file.file_name}</span>
          <ExternalLink className="h-3 w-3 shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />
        </a>
      </td>
      <td className="px-4 py-2.5">
        <span className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${typeColor}`}>
          {TYPE_LABELS[file.doc_type] ?? file.doc_type}
        </span>
      </td>
      <td className="px-4 py-2.5">
        <span className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize ${statusColor}`}>
          {file.status}
        </span>
      </td>
      <td className="px-4 py-2.5 text-muted-foreground">
        {file.deal_name ? (
          file.deal_id ? (
            <Link
              to={`/documents/${file.deal_id}`}
              className="text-foreground hover:text-primary transition-colors"
            >
              {file.deal_name}
            </Link>
          ) : (
            file.deal_name
          )
        ) : (
          <span className="text-muted-foreground/50">-</span>
        )}
      </td>
      <td className="px-4 py-2.5 max-w-[140px]">
        {file.folder_path ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="block truncate text-muted-foreground cursor-default">
                {file.folder_path}
              </span>
            </TooltipTrigger>
            <TooltipContent>{file.folder_path}</TooltipContent>
          </Tooltip>
        ) : (
          <span className="text-muted-foreground/50">-</span>
        )}
      </td>
      <td className="px-4 py-2.5 max-w-[240px]">
        {file.description ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="block truncate text-muted-foreground cursor-default">
                {file.description}
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-sm">
              {file.description}
            </TooltipContent>
          </Tooltip>
        ) : (
          <span className="text-muted-foreground/50">-</span>
        )}
      </td>
      <td className="px-4 py-2.5 whitespace-nowrap text-muted-foreground">
        {file.doc_date ?? "-"}
      </td>
    </tr>
  );
}

export default RunDetail;
