import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type DatasetSummary } from "./api";

interface Workspace {
  datasets: DatasetSummary[] | null;
  refresh: () => Promise<void>;
  /** Upload a file, then open its dataset. Failures are shown, never swallowed. */
  upload: (file: File) => Promise<void>;
  uploading: boolean;
  notice: string | null;
  dismiss: () => void;
}

const Context = createContext<Workspace | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDatasets(await api.datasets());
    } catch (error) {
      setDatasets((current) => current ?? []);
      setNotice(error instanceof Error ? error.message : "Could not load datasets.");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const upload = useCallback(
    async (file: File) => {
      setUploading(true);
      setNotice(null);
      try {
        const view = await api.uploadDataset(file);
        await refresh();
        window.location.hash = `#/d/${view.dataset_id}`;
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "The upload failed. Try again.");
      } finally {
        setUploading(false);
      }
    },
    [refresh],
  );

  return (
    <Context.Provider
      value={{ datasets, refresh, upload, uploading, notice, dismiss: () => setNotice(null) }}
    >
      {children}
    </Context.Provider>
  );
}

export function useWorkspace(): Workspace {
  const value = useContext(Context);
  if (!value) throw new Error("WorkspaceProvider is missing");
  return value;
}
