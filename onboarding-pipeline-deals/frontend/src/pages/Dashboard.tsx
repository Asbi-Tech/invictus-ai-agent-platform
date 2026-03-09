import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, OrgQuotaResponse } from "@/lib/api";
import Navbar from "@/components/Navbar";
import DriveConnectCard from "@/components/DriveConnectCard";
import SyncStatusCard from "@/components/SyncStatusCard";
import OrgSetupModal from "@/components/OrgSetupModal";
import QuotaBar from "@/components/QuotaBar";
import { Button } from "@/components/ui/button";
import { FolderOpen } from "lucide-react";

const Dashboard = () => {
  const { user, isLoading, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [showOrgModal, setShowOrgModal] = useState(false);
  const [quota, setQuota] = useState<OrgQuotaResponse | null>(null);

  useEffect(() => {
    if (!isLoading && !user) navigate("/", { replace: true });
  }, [user, isLoading, navigate]);

  // Prompt for org setup when user has no organization
  useEffect(() => {
    if (!isLoading && user && user.needs_org) {
      setShowOrgModal(true);
    }
  }, [isLoading, user]);

  // Fetch quota when user has an org
  useEffect(() => {
    if (user?.organization_id) {
      api.getOrgQuota().then(setQuota).catch(() => {});
    }
  }, [user?.organization_id]);

  if (isLoading || !user) return null;

  const handleOrgDone = async () => {
    setShowOrgModal(false);
    await refreshUser();
    api.getOrgQuota().then(setQuota).catch(() => {});
  };

  const orgName = user.organization?.name ?? user.company_name;

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-3xl px-6 pt-28 pb-24">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="font-heading text-3xl font-semibold text-foreground">
              {orgName ?? "Dashboard"}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Signed in as <span className="text-foreground font-medium">{user.email}</span>
            </p>
          </div>
        </div>

        {/* Quota usage */}
        {quota && (
          <section className="mt-8 rounded-lg border border-border p-5 space-y-4">
            <h2 className="font-heading text-lg font-medium text-foreground">Usage</h2>
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
            <p className="text-sm text-muted-foreground">
              Max processing time: {quota.processing_timeout_hours}h per sync
            </p>
          </section>
        )}

        <div className="mt-8 space-y-0 [&_section]:py-6">
          <DriveConnectCard />
          <SyncStatusCard />
        </div>

        {user.folder_id && (
          <div className="mt-8 flex justify-end">
            <Button
              onClick={() => navigate("/documents")}
              className="gap-2 bg-primary text-primary-foreground hover:bg-accent"
            >
              <FolderOpen className="h-4 w-4" />
              Browse Documents
            </Button>
          </div>
        )}
      </main>

      <footer className="border-t border-border py-8 text-center text-xs text-muted-foreground">
        © 2025 Invictus Deals Onboarding. All rights reserved.
      </footer>

      <OrgSetupModal open={showOrgModal} onDone={handleOrgDone} />
    </div>
  );
};

export default Dashboard;
