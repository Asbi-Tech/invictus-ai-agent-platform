import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, DealResponse, MergePreviewResponse, MergeResolution } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { Folder, FolderOpen, Search, Merge, Check, Trash2, Loader2, FileText } from "lucide-react";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";

const FILL_FILTERS = [
  { label: "25%", slots: 1 },
  { label: "50%", slots: 2 },
  { label: "75%", slots: 3 },
  { label: "100%", slots: 4 },
] as const;

const Documents = () => {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const [deals, setDeals] = useState<DealResponse[]>([]);
  const [fetching, setFetching] = useState(false);
  const [query, setQuery] = useState("");
  const [fillFilter, setFillFilter] = useState<number | null>(null);

  // Merge state
  const [mergeMode, setMergeMode] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeName, setMergeName] = useState("");
  const [merging, setMerging] = useState(false);
  const [mergePreview, setMergePreview] = useState<MergePreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [resolutions, setResolutions] = useState<Record<string, number>>({});

  // Delete state
  const [deleteTarget, setDeleteTarget] = useState<DealResponse | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) navigate("/", { replace: true });
  }, [user, isLoading, navigate]);

  const fetchDeals = () => {
    if (!user) return;
    setFetching(true);
    api.getDeals().then(setDeals).catch(() => null).finally(() => setFetching(false));
  };

  useEffect(() => {
    fetchDeals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  if (isLoading || !user) return null;

  const dealsWithDocs = deals
    .filter((d) => d.doc_count > 0 || d.archived.length > 0)
    .sort((a, b) => a.name.localeCompare(b.name));

  const filtered = dealsWithDocs
    .filter((d) => !query.trim() || d.name.toLowerCase().includes(query.trim().toLowerCase()))
    .filter((d) => fillFilter === null || Object.values(d.documents).filter(Boolean).length === fillFilter);

  function toggleSelect(dealId: number) {
    setSelected((prev) => {
      if (prev.includes(dealId)) return prev.filter((id) => id !== dealId);
      if (prev.length >= 2) return prev;
      return [...prev, dealId];
    });
  }

  function cancelMerge() {
    setMergeMode(false);
    setSelected([]);
    setMergeName("");
    setMergePreview(null);
    setResolutions({});
  }

  async function openMergeDialog() {
    if (selected.length !== 2) return;
    const target = dealsWithDocs.find((d) => d.id === selected[1]);
    setMergeName(target?.name ?? "");
    setMergeOpen(true);
    setMergePreview(null);
    setResolutions({});

    // Fetch preview with LLM conflict resolution
    setPreviewLoading(true);
    try {
      const preview = await api.previewMerge(selected[0], selected[1]);
      setMergePreview(preview);
      // Pre-fill resolutions with LLM recommendations
      const defaults: Record<string, number> = {};
      for (const c of preview.conflicts) {
        defaults[c.doc_type] =
          c.recommendation === "keep_source" ? c.source_doc.id : c.target_doc.id;
      }
      setResolutions(defaults);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to preview merge");
      setMergeOpen(false);
    } finally {
      setPreviewLoading(false);
    }
  }

  async function confirmMerge() {
    if (selected.length !== 2) return;
    const [sourceId, targetId] = selected;
    setMerging(true);
    try {
      const trimmed = mergeName.trim();
      const targetDeal = dealsWithDocs.find((d) => d.id === targetId);
      const newName = trimmed && trimmed !== targetDeal?.name ? trimmed : undefined;

      // Build resolutions array from user's choices
      const mergeResolutions: MergeResolution[] | undefined =
        mergePreview && mergePreview.conflicts.length > 0
          ? mergePreview.conflicts.map((c) => ({
              doc_type: c.doc_type,
              keep_doc_id: resolutions[c.doc_type] ?? c.target_doc.id,
            }))
          : undefined;

      const res = await api.mergeDeals(sourceId, targetId, newName, mergeResolutions);
      toast.success(
        `Merged into "${res.target_deal_name}" — ${res.documents_moved} doc(s) moved, ${res.documents_superseded} superseded`
      );
      setMergeOpen(false);
      cancelMerge();
      fetchDeals();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to merge deals");
    } finally {
      setMerging(false);
    }
  }

  const sourceDeal = dealsWithDocs.find((d) => d.id === selected[0]);
  const targetDeal = dealsWithDocs.find((d) => d.id === selected[1]);

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-6xl px-6 pt-24 pb-16">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="font-heading text-3xl font-semibold text-foreground">Deals</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {user.company_name && (
                <span className="font-medium text-foreground">{user.company_name} · </span>
              )}
              {filtered.length}{(query.trim() || fillFilter !== null) ? ` of ${dealsWithDocs.length}` : ""} deal{dealsWithDocs.length !== 1 ? "s" : ""}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Merge toggle */}
            {!mergeMode && dealsWithDocs.length >= 2 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setMergeMode(true)}
                className="gap-1.5"
              >
                <Merge className="h-3.5 w-3.5" />
                Merge
              </Button>
            )}
            {mergeMode && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  {selected.length === 0
                    ? "Select source deal"
                    : selected.length === 1
                      ? "Select target deal"
                      : "Ready to merge"}
                </span>
                <Button
                  size="sm"
                  disabled={selected.length !== 2}
                  onClick={openMergeDialog}
                  className="gap-1.5"
                >
                  <Merge className="h-3.5 w-3.5" />
                  Merge ({selected.length}/2)
                </Button>
                <Button variant="ghost" size="sm" onClick={cancelMerge}>
                  Cancel
                </Button>
              </div>
            )}

            {/* Fill filter pills */}
            {!mergeMode && (
              <div className="flex items-center gap-1.5">
                {FILL_FILTERS.map(({ label, slots }) => (
                  <button
                    key={slots}
                    onClick={() => setFillFilter(fillFilter === slots ? null : slots)}
                    className={cn(
                      "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                      fillFilter === slots
                        ? "bg-primary/15 text-primary"
                        : "bg-muted text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
            <div className="relative w-full sm:w-56">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <Input
                placeholder="Search deals…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>
        </div>

        {/* Merge mode instructions */}
        {mergeMode && (
          <div className="mt-4 rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-primary">
            {selected.length === 0 && "Click the first deal to select it as the source (will be absorbed)."}
            {selected.length === 1 && (
              <>
                <span className="font-medium">Source: {sourceDeal?.name}</span>
                {" — now click the target deal (will be kept)."}
              </>
            )}
            {selected.length === 2 && (
              <>
                <span className="font-medium">Source: {sourceDeal?.name}</span>
                {" → "}
                <span className="font-medium">Target: {targetDeal?.name}</span>
                {" — click Merge to continue."}
              </>
            )}
          </div>
        )}

        {/* Skeleton */}
        {fetching && (
          <div className="mt-8 grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-3 rounded-xl border border-border p-5">
                <Skeleton className="h-10 w-10 rounded-lg" />
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-20" />
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!fetching && filtered.length === 0 && (
          <p className="mt-16 text-center text-sm text-muted-foreground">
            {query.trim() ? `No deals match "${query}".` : "No deals found. Run the worker after configuring your Drive folder."}
          </p>
        )}

        {/* Deal folder grid */}
        {!fetching && filtered.length > 0 && (
          <div className="mt-8 grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {filtered.map((deal) => (
              <DealCard
                key={deal.id}
                deal={deal}
                mergeMode={mergeMode}
                selectedIndex={selected.indexOf(deal.id)}
                onClick={() => {
                  if (mergeMode) {
                    toggleSelect(deal.id);
                  } else {
                    navigate(`/documents/${deal.id}`);
                  }
                }}
                onDelete={() => setDeleteTarget(deal)}
              />
            ))}
          </div>
        )}

        {/* Merge confirmation dialog */}
        <Dialog open={mergeOpen} onOpenChange={(open) => { if (!open && !merging && !previewLoading) { setMergeOpen(false); } }}>
          <DialogContent className={mergePreview && mergePreview.conflicts.length > 0 ? "sm:max-w-2xl" : ""}>
            <DialogHeader>
              <DialogTitle>Merge deals</DialogTitle>
              <DialogDescription>
                "{sourceDeal?.name}" will be absorbed into "{targetDeal?.name}".
                {mergePreview && mergePreview.conflicts.length > 0
                  ? " Review the document conflicts below before confirming."
                  : " The merged deal will be re-analyzed on the next processing run."}
              </DialogDescription>
            </DialogHeader>

            {/* Loading state while preview is fetching */}
            {previewLoading && (
              <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Analyzing documents for conflicts...
              </div>
            )}

            {/* Main content (after preview loaded) */}
            {!previewLoading && mergePreview && (
              <div className="space-y-4 py-2">
                {/* Deal name input */}
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-foreground">
                    Deal name
                  </label>
                  <Input
                    value={mergeName}
                    onChange={(e) => setMergeName(e.target.value)}
                    placeholder={targetDeal?.name}
                    disabled={merging}
                  />
                  <p className="text-xs text-muted-foreground">
                    Leave as-is to keep the target deal's name, or type a new name.
                  </p>
                </div>

                {/* Conflict resolution */}
                {mergePreview.conflicts.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <div className="h-px flex-1 bg-border" />
                      <span className="text-xs font-medium text-muted-foreground">
                        {mergePreview.conflicts.length} document conflict{mergePreview.conflicts.length !== 1 ? "s" : ""}
                      </span>
                      <div className="h-px flex-1 bg-border" />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Both deals have documents of the same type. Choose which to keep — the other will be archived.
                    </p>
                    {mergePreview.conflicts.map((conflict) => {
                      const keepId = resolutions[conflict.doc_type];
                      return (
                        <div key={conflict.doc_type} className="rounded-lg border border-border p-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-foreground">{conflict.doc_type_label}</span>
                            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-500">
                              conflict
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground italic">{conflict.reason}</p>
                          <div className="grid grid-cols-2 gap-2">
                            {/* Source doc option */}
                            <button
                              type="button"
                              onClick={() => setResolutions((r) => ({ ...r, [conflict.doc_type]: conflict.source_doc.id }))}
                              className={cn(
                                "flex flex-col gap-1 rounded-md border p-2.5 text-left text-xs transition-all",
                                keepId === conflict.source_doc.id
                                  ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                                  : "border-border hover:border-muted-foreground/30"
                              )}
                              disabled={merging}
                            >
                              <div className="flex items-center gap-1.5">
                                <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
                                <span className="font-medium text-foreground truncate">{conflict.source_doc.file_name}</span>
                              </div>
                              <span className="text-muted-foreground">
                                {conflict.source_doc.date ?? "No date"} · Source
                              </span>
                              {conflict.source_doc.description && (
                                <span className="text-muted-foreground/70 line-clamp-2">{conflict.source_doc.description}</span>
                              )}
                              {keepId === conflict.source_doc.id && (
                                <span className="mt-0.5 inline-flex items-center gap-1 text-primary font-medium">
                                  <Check className="h-3 w-3" /> Keep
                                </span>
                              )}
                            </button>
                            {/* Target doc option */}
                            <button
                              type="button"
                              onClick={() => setResolutions((r) => ({ ...r, [conflict.doc_type]: conflict.target_doc.id }))}
                              className={cn(
                                "flex flex-col gap-1 rounded-md border p-2.5 text-left text-xs transition-all",
                                keepId === conflict.target_doc.id
                                  ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                                  : "border-border hover:border-muted-foreground/30"
                              )}
                              disabled={merging}
                            >
                              <div className="flex items-center gap-1.5">
                                <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
                                <span className="font-medium text-foreground truncate">{conflict.target_doc.file_name}</span>
                              </div>
                              <span className="text-muted-foreground">
                                {conflict.target_doc.date ?? "No date"} · Target
                              </span>
                              {conflict.target_doc.description && (
                                <span className="text-muted-foreground/70 line-clamp-2">{conflict.target_doc.description}</span>
                              )}
                              {keepId === conflict.target_doc.id && (
                                <span className="mt-0.5 inline-flex items-center gap-1 text-primary font-medium">
                                  <Check className="h-3 w-3" /> Keep
                                </span>
                              )}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Summary */}
                {mergePreview.conflicts.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    No document conflicts found. {mergePreview.documents_to_move} document(s) will be moved to the target deal.
                  </p>
                )}
              </div>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={() => setMergeOpen(false)} disabled={merging || previewLoading}>
                Cancel
              </Button>
              <Button onClick={confirmMerge} disabled={merging || previewLoading || !mergePreview}>
                {merging ? "Merging…" : "Confirm merge"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Delete confirmation dialog */}
        <AlertDialog open={!!deleteTarget} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete "{deleteTarget?.name}"?</AlertDialogTitle>
              <AlertDialogDescription>
                This will remove the deal and unlink all its documents. The documents will remain in the system and may be re-grouped on the next processing run. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
                disabled={deleting}
                onClick={async (e) => {
                  e.preventDefault();
                  if (!deleteTarget) return;
                  setDeleting(true);
                  try {
                    const res = await api.deleteDeal(deleteTarget.id);
                    toast.success(`Deleted "${res.deal_name}" — ${res.documents_unlinked} document(s) unlinked`);
                    setDeleteTarget(null);
                    fetchDeals();
                  } catch (err: unknown) {
                    toast.error(err instanceof Error ? err.message : "Failed to delete deal");
                  } finally {
                    setDeleting(false);
                  }
                }}
              >
                {deleting ? "Deleting…" : "Delete"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </main>
    </div>
  );
};

function DealCard({
  deal,
  onClick,
  onDelete,
  mergeMode,
  selectedIndex,
}: {
  deal: DealResponse;
  onClick: () => void;
  onDelete: () => void;
  mergeMode?: boolean;
  selectedIndex?: number;
}) {
  const [hovered, setHovered] = useState(false);

  const filledSlots = Object.values(deal.documents).filter(Boolean).length;
  const totalSlots = 4;
  const isSelected = selectedIndex !== undefined && selectedIndex >= 0;
  const label = selectedIndex === 0 ? "Source" : selectedIndex === 1 ? "Target" : null;

  return (
    <div
      className={cn(
        "group relative flex cursor-pointer flex-col gap-4 rounded-xl border bg-card p-5 text-left transition-all duration-150 focus-within:ring-2 focus-within:ring-primary",
        isSelected
          ? "border-primary shadow-md ring-1 ring-primary/30"
          : "border-border hover:border-primary/40 hover:shadow-md"
      )}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Selection indicator */}
      {mergeMode && isSelected && (
        <div className="absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground shadow">
          <Check className="h-3.5 w-3.5" />
        </div>
      )}
      {mergeMode && isSelected && label && (
        <span className="absolute left-2 top-2 rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold text-primary">
          {label}
        </span>
      )}

      {/* Delete button (top-right, visible on hover, hidden in merge mode) */}
      {!mergeMode && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground/50 opacity-0 transition-all hover:bg-red-500/10 hover:text-red-400 group-hover:opacity-100"
          title="Delete deal"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}

      {/* Folder icon */}
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors duration-150 group-hover:bg-primary/20">
        {hovered ? (
          <FolderOpen className="h-7 w-7" />
        ) : (
          <Folder className="h-7 w-7" />
        )}
      </div>

      {/* Deal name */}
      <div className="flex-1">
        <p className="font-medium text-foreground line-clamp-2">{deal.name}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {filledSlots}/{totalSlots} documents
        </p>
      </div>

      {/* Doc type badges */}
      <div className="flex flex-wrap gap-1">
        {(["pitch_deck", "investment_memo", "prescreening_report", "meeting_minutes"] as const).map(
          (type) => (
            <span
              key={type}
              className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${
                deal.documents[type]
                  ? "bg-primary/15 text-primary"
                  : "bg-muted text-muted-foreground/50"
              }`}
            >
              {TYPE_SHORT[type]}
            </span>
          )
        )}
      </div>

      {/* Archive badge */}
      {deal.archived.length > 0 && (
        <Badge variant="outline" className="w-fit border-muted text-[10px] text-muted-foreground">
          {deal.archived.length} archived
        </Badge>
      )}
    </div>
  );
}

const TYPE_SHORT: Record<string, string> = {
  pitch_deck: "Deck",
  investment_memo: "Memo",
  prescreening_report: "Pre-screen",
  meeting_minutes: "Minutes",
};

export default Documents;
