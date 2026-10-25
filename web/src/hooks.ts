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
    let failures = 0;
    const step = async () => {
      try {
        const view = await api.run(id);
        if (stopped) return;
        failures = 0;
        setProblem(null);
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
        if (stopped) return;
        // A dropped connection or a server restart is usually brief: keep following the run
        // with a growing delay, and only show the problem once it has lasted a while.
        failures += 1;
        if (failures >= 4) {
          setProblem(error instanceof Error ? error.message : "Could not load this run.");
        }
        if (failures < 20) timer = window.setTimeout(step, Math.min(15000, 1500 * 2 ** failures));
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

let alphaPromise: Promise<number | null> | null = null;

/** The gate's alpha, read once from the server's config; null until known or if unavailable. */
export function useAlpha(): number | null {
  const [alpha, setAlpha] = useState<number | null>(null);
  useEffect(() => {
    alphaPromise ??= api.system().then(
      (s) => s.alpha,
      () => {
        alphaPromise = null;
        return null;
      },
    );
    let live = true;
    alphaPromise.then((a) => live && setAlpha(a));
    return () => {
      live = false;
    };
  }, []);
  return alpha;
}
