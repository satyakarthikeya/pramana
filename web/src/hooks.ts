import { useEffect, useState } from "react";
import { api, type RunResults, type RunView } from "./api";

/** Follow one run until it finishes, then load its stored results. */
export function useRun(id: string | null, onFinished?: () => void) {
  const [run, setRun] = useState<RunView | null>(null);
  const [results, setResults] = useState<RunResults | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    setRun(null);
    setResults(null);
    setProblem(null);
    if (!id) return;
    let stopped = false;
    let timer: number | undefined;
    const step = async () => {
      try {
        const view = await api.run(id);
        if (stopped) return;
        setRun(view);
        if (view.status === "pending" || view.status === "running") {
          timer = window.setTimeout(step, 1500);
          return;
        }
        try {
          const final = await api.results(id);
          if (!stopped) setResults(final);
        } catch {
          /* a failed run may have no snapshot; the run view explains why */
        }
        onFinished?.();
      } catch (error) {
        if (!stopped) setProblem(error instanceof Error ? error.message : "Could not load this run.");
      }
    };
    step();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
    // onFinished is intentionally not a dependency: a new callback must not restart polling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  return { run, results, problem };
}
