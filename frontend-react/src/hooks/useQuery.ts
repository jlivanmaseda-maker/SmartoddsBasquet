/** Small fetch-based GraphQL query hook (Apollo-free). */
import { useEffect, useState, useRef, useCallback } from "react";
import { gql } from "../config/api";

interface QueryState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

interface UseQueryOptions {
  variables?: Record<string, unknown>;
  /** Poll interval in ms. 0/undefined disables polling. */
  pollInterval?: number;
  skip?: boolean;
}

export function useQuery<T = unknown>(
  query: string,
  options: UseQueryOptions = {},
): QueryState<T> {
  const { variables, pollInterval, skip } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(!skip);
  const [error, setError] = useState<string | null>(null);

  // Serialize variables so the effect only re-runs on real changes.
  const varsKey = JSON.stringify(variables || {});
  const aliveRef = useRef(true);

  const run = useCallback(() => {
    if (skip) return;
    gql<T>(query, variables || {})
      .then((d) => {
        if (aliveRef.current) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: Error) => {
        if (aliveRef.current) setError(e.message);
      })
      .finally(() => {
        if (aliveRef.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, varsKey, skip]);

  useEffect(() => {
    aliveRef.current = true;
    if (skip) {
      setLoading(false);
      return;
    }
    setLoading(true);
    run();
    let timer: ReturnType<typeof setInterval> | null = null;
    if (pollInterval && pollInterval > 0) {
      timer = setInterval(run, pollInterval);
    }
    return () => {
      aliveRef.current = false;
      if (timer) clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, pollInterval, skip]);

  return { data, loading, error, refetch: run };
}
