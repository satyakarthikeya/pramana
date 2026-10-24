import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type DatasetSummary } from "./api";

interface Workspace {
  datasets: DatasetSummary[] | null;
  refresh: () => Promise<void>;
  /** A file chosen or dropped anywhere, waiting on the home screen for a name. */
  staged: File | null;
  stage: (file: File | null) => void;
  /** Upload under a name, start the analysis, then open its findings. Failures are shown. */
  start: (file: File, name: string, question: string) => Promise<void>;
  starting: boolean;
  notice: string | null;
  dismiss: () => void;
}

const Context = createContext<Workspace | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null);
  const [staged, setStaged] = useState<File | null>(null);
  const [starting, setStarting] = useState(false);
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

  const stage = useCallback((file: File | null) => {
    setStaged(file);
    setNotice(null);
    if (file) window.location.hash = "#/";
  }, []);

  const start = useCallback(
    async (file: File, name: string, question: string) => {
      setStarting(true);
      setNotice(null);
      try {
        const view = await api.uploadDataset(file, name);
        // clear only the file that was uploaded; never a newer one chosen meanwhile
        setStaged((current) => (current === file ? null : current));
        try {
          const run = await api.analyse(view.dataset_id, question);
          await refresh();
          window.location.hash = `#/d/${view.dataset_id}/findings/${run.run_id}`;
        } catch (error) {
          // The table is stored even if the analysis could not start; open it and say why.
          await refresh();
          window.location.hash = `#/d/${view.dataset_id}`;
          setNotice(
            `${name} was added, but the analysis did not start: ${
              error instanceof Error ? error.message : "unknown error"
            }`,
          );
        }
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "The upload failed. Try again.");
      } finally {
        setStarting(false);
      }
    },
    [refresh],
  );

  return (
    <Context.Provider
      value={{
        datasets,
        refresh,
        staged,
        stage,
        start,
        starting,
        notice,
        dismiss: () => setNotice(null),
      }}
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
