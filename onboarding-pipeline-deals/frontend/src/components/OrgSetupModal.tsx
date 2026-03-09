import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { api, OrgListItem } from "@/lib/api";
import { toast } from "sonner";

interface Props {
  open: boolean;
  onDone: () => void;
}

export default function OrgSetupModal({ open, onDone }: Props) {
  const [tab, setTab] = useState<"create" | "join">("create");
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  // Join state
  const [orgs, setOrgs] = useState<OrgListItem[]>([]);
  const [loadingOrgs, setLoadingOrgs] = useState(false);
  const [selectedOrg, setSelectedOrg] = useState<OrgListItem | null>(null);
  const [migrateData, setMigrateData] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (open && tab === "join") {
      setLoadingOrgs(true);
      api
        .listOrgs()
        .then(setOrgs)
        .catch(() => toast.error("Failed to load organizations"))
        .finally(() => setLoadingOrgs(false));
    }
  }, [open, tab]);

  const handleCreate = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      await api.createOrg(trimmed);
      toast.success("Organization created");
      onDone();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create organization");
    } finally {
      setSaving(false);
    }
  };

  const handleJoin = async () => {
    if (!selectedOrg) return;
    setSaving(true);
    try {
      await api.joinOrg(selectedOrg.id, migrateData);
      toast.success(`Joined ${selectedOrg.name}`);
      onDone();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to join organization");
    } finally {
      setSaving(false);
    }
  };

  const filtered = orgs.filter((o) =>
    o.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-lg" onPointerDownOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Set Up Your Organization</DialogTitle>
          <DialogDescription>
            Create a new organization or join an existing one. Documents, deals, and settings are shared within an organization.
          </DialogDescription>
        </DialogHeader>

        {/* Tab switcher */}
        <div className="mt-2 flex gap-2">
          <Button
            variant={tab === "create" ? "default" : "outline"}
            size="sm"
            onClick={() => { setTab("create"); setSelectedOrg(null); }}
          >
            Create New
          </Button>
          <Button
            variant={tab === "join" ? "default" : "outline"}
            size="sm"
            onClick={() => setTab("join")}
          >
            Join Existing
          </Button>
        </div>

        {tab === "create" && (
          <div className="mt-4 space-y-2">
            <Label htmlFor="org-name">Organization name</Label>
            <Input
              id="org-name"
              placeholder="Acme Ventures"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
            />
          </div>
        )}

        {tab === "join" && (
          <div className="mt-4 space-y-3">
            <Input
              placeholder="Search organizations..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <div className="max-h-48 overflow-y-auto rounded-md border border-border">
              {loadingOrgs && (
                <p className="p-3 text-sm text-muted-foreground">Loading...</p>
              )}
              {!loadingOrgs && filtered.length === 0 && (
                <p className="p-3 text-sm text-muted-foreground">No organizations found</p>
              )}
              {filtered.map((org) => (
                <button
                  key={org.id}
                  onClick={() => setSelectedOrg(org)}
                  className={`w-full px-3 py-2 text-left text-sm hover:bg-muted/50 flex justify-between items-center ${
                    selectedOrg?.id === org.id ? "bg-muted" : ""
                  }`}
                >
                  <span className="font-medium">{org.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {org.member_count} member{org.member_count !== 1 ? "s" : ""}
                  </span>
                </button>
              ))}
            </div>

            {selectedOrg && (
              <div className="rounded-md border border-border p-3 space-y-2">
                <p className="text-sm font-medium">
                  Join <span className="text-foreground">{selectedOrg.name}</span>?
                </p>
                <div className="flex gap-3">
                  <label className="flex items-center gap-1.5 text-sm">
                    <input
                      type="radio"
                      checked={migrateData}
                      onChange={() => setMigrateData(true)}
                    />
                    Migrate my data
                  </label>
                  <label className="flex items-center gap-1.5 text-sm">
                    <input
                      type="radio"
                      checked={!migrateData}
                      onChange={() => setMigrateData(false)}
                    />
                    Start fresh
                  </label>
                </div>
                <p className="text-xs text-muted-foreground">
                  {migrateData
                    ? "Your existing documents and deals will be moved to this organization."
                    : "Your existing data stays with your current organization."}
                </p>
              </div>
            )}
          </div>
        )}

        <DialogFooter className="mt-4">
          {tab === "create" ? (
            <Button onClick={handleCreate} disabled={!name.trim() || saving}>
              {saving ? "Creating..." : "Create Organization"}
            </Button>
          ) : (
            <Button onClick={handleJoin} disabled={!selectedOrg || saving}>
              {saving ? "Joining..." : "Join Organization"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
