import { useEffect, useState } from "react";
import { api } from "./api";
import { DatasetPage } from "./components/DatasetPage";
import { Home } from "./components/Home";
import { MemoryPage } from "./components/MemoryPage";
import { AuthPage } from "./components/AuthPage";
import { AuthProvider, useAuth } from "./auth";
import { WorkspaceProvider } from "./store";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const onChange = () => {
      setHash(window.location.hash || "#/");
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

const UUID = "([0-9a-f-]{36})";

/** Older links (`#/run/<id>`) resolve the run's dataset and move to the dataset's findings. */
function RunRedirect({ id }: { id: string }) {
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    api.run(id).then(
      (run) => {
        window.location.replace(
          run.dataset_id ? `#/d/${run.dataset_id}/findings/${id}` : "#/",
        );
      },
      () => setMissing(true),
    );
  }, [id]);
  return <p style={{ padding: 48 }}>{missing ? "That run does not exist." : "Opening run…"}</p>;
}

function Routes() {
  const hash = useHash();
  const findings = new RegExp(`^#/d/${UUID}/findings(?:/${UUID})?$`, "i").exec(hash);
  if (findings) return <DatasetPage id={findings[1]} tab="findings" runId={findings[2] ?? null} />;
  const ask = new RegExp(`^#/d/${UUID}/ask$`, "i").exec(hash);
  if (ask) return <DatasetPage id={ask[1]} tab="ask" runId={null} />;
  const dataset = new RegExp(`^#/d/${UUID}$`, "i").exec(hash);
  if (dataset) return <DatasetPage id={dataset[1]} tab="overview" runId={null} />;
  const run = new RegExp(`^#/run/${UUID}$`, "i").exec(hash);
  if (run) return <RunRedirect id={run[1]} />;
  if (hash === "#/memory") return <MemoryPage />;
  return <Home />;
}

function Gate() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <AuthPage />;
  // Keyed by user so one person's cached lists never survive into another's session.
  return (
    <WorkspaceProvider key={user.user_id}>
      <Routes />
    </WorkspaceProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
