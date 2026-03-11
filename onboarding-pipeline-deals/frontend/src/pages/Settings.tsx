import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, OrgQuotaResponse } from "@/lib/api";
import Navbar from "@/components/Navbar";
import QuotaBar from "@/components/QuotaBar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";

const Settings = () => {
  const { user, isLoading, refreshUser } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [quota, setQuota] = useState<OrgQuotaResponse | null>(null);
  const [classificationLimit, setClassificationLimit] = useState("");
  const [vectorizationLimit, setVectorizationLimit] = useState("");
  const [isSavingLimits, setIsSavingLimits] = useState(false);
  const [tenantId, setTenantId] = useState("");
  const [isSavingTenantId, setIsSavingTenantId] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) navigate("/", { replace: true });
  }, [user, isLoading, navigate]);

  useEffect(() => {
    if (user?.organization_id) {
      api.getOrgQuota().then((q) => {
        setQuota(q);
        setClassificationLimit(String(q.classification_limit));
        setVectorizationLimit(String(q.vectorization_limit));
        setTenantId(q.tenant_id ?? "");
      }).catch(() => {});
    }
  }, [user?.organization_id]);

  if (isLoading || !user) return null;

  const handleSaveTenantId = async () => {
    setIsSavingTenantId(true);
    try {
      const updated = await api.updateOrgSettings({
        tenant_id: tenantId.trim() || null,
      });
      setQuota(updated);
      setTenantId(updated.tenant_id ?? "");
      toast({ title: "Tenant ID updated" });
    } catch (err: unknown) {
      toast({
        title: "Failed to save",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsSavingTenantId(false);
    }
  };

  const handleSaveLimits = async () => {
    const cLimit = parseInt(classificationLimit, 10);
    const vLimit = parseInt(vectorizationLimit, 10);

    if (isNaN(cLimit) || cLimit < 0 || isNaN(vLimit) || vLimit < 0) {
      toast({
        title: "Invalid input",
        description: "Limits must be non-negative numbers",
        variant: "destructive",
      });
      return;
    }

    setIsSavingLimits(true);
    try {
      const updated = await api.updateOrgSettings({
        classification_limit: cLimit,
        vectorization_limit: vLimit,
      });
      setQuota(updated);
      toast({ title: "Limits updated" });
    } catch (err: unknown) {
      toast({
        title: "Failed to save",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsSavingLimits(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-2xl px-6 pt-24 pb-16">
        <h1 className="font-heading text-3xl font-semibold text-foreground">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">{user.email}</p>

        {/* Organization */}
        {user.organization && (
          <section className="mt-10">
            <h2 className="font-heading text-lg font-medium text-foreground">Organization</h2>
            <p className="mt-3 text-sm text-foreground">
              {user.organization.name}
              {quota && (
                <span className="ml-2 text-muted-foreground">
                  ({quota.member_count} member{quota.member_count !== 1 ? "s" : ""})
                </span>
              )}
            </p>
          </section>
        )}

        {/* Usage & Quotas */}
        {quota && (
          <section className="mt-10">
            <h2 className="font-heading text-lg font-medium text-foreground">Usage &amp; Quotas</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Current usage and processing limits for your organization.
            </p>
            <div className="mt-4 space-y-4">
              <QuotaBar
                label="Classification"
                used={quota.classification_used}
                limit={quota.classification_limit}
              />
              <QuotaBar
                label="Vectorization"
                used={quota.vectorization_used}
                limit={quota.vectorization_limit}
              />
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Max processing time per sync: {quota.processing_timeout_hours} hour{quota.processing_timeout_hours !== 1 ? "s" : ""}
            </p>

            {/* Editable limits */}
            <div className="mt-6 rounded-md border border-border p-4 space-y-4">
              <h3 className="text-sm font-medium text-foreground">Update Limits</h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="classification-limit" className="text-sm text-muted-foreground">
                    Classification Limit
                  </Label>
                  <Input
                    id="classification-limit"
                    type="number"
                    min={0}
                    value={classificationLimit}
                    onChange={(e) => setClassificationLimit(e.target.value)}
                    className="border-border bg-background text-foreground"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="vectorization-limit" className="text-sm text-muted-foreground">
                    Vectorization Limit
                  </Label>
                  <Input
                    id="vectorization-limit"
                    type="number"
                    min={0}
                    value={vectorizationLimit}
                    onChange={(e) => setVectorizationLimit(e.target.value)}
                    className="border-border bg-background text-foreground"
                  />
                </div>
              </div>
              <div className="flex justify-end">
                <Button
                  onClick={handleSaveLimits}
                  disabled={isSavingLimits}
                  className="bg-primary text-primary-foreground hover:bg-accent"
                >
                  {isSavingLimits ? "Saving…" : "Save Limits"}
                </Button>
              </div>
            </div>
          </section>
        )}

        {/* RAG Configuration */}
        {quota && (
          <section className="mt-10">
            <h2 className="font-heading text-lg font-medium text-foreground">RAG Configuration</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Configure the tenant identifier used for vectorization and RAG Gateway integration.
            </p>
            <div className="mt-4 rounded-md border border-border p-4 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="tenant-id" className="text-sm text-muted-foreground">
                  Tenant ID
                </Label>
                <Input
                  id="tenant-id"
                  type="text"
                  placeholder="e.g. onboarding-testing-t1"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  className="border-border bg-background text-foreground"
                />
                <p className="text-xs text-muted-foreground">
                  Tenant identifier for the RAG Gateway. Used during document vectorization and analytical extraction.
                </p>
              </div>
              <div className="flex justify-end">
                <Button
                  onClick={handleSaveTenantId}
                  disabled={isSavingTenantId}
                  className="bg-primary text-primary-foreground hover:bg-accent"
                >
                  {isSavingTenantId ? "Saving..." : "Save Tenant ID"}
                </Button>
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
};

export default Settings;
