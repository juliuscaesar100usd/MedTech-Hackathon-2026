import { useCallback, useEffect, useRef, useState } from 'react';

export interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
  reload: () => void;
  /** Set the data locally (e.g. optimistic queue removal). */
  setData: (updater: T | ((cur: T | null) => T | null)) => void;
}

/**
 * Generic async data hook. Re-runs whenever any value in `deps` changes.
 * The fetcher is called with an AbortSignal-free contract; results from
 * superseded calls are ignored to avoid race conditions.
 */
export function useFetch<T>(fetcher: () => Promise<T>, deps: unknown[]): FetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [nonce, setNonce] = useState(0);
  const callId = useRef(0);

  // store latest fetcher without forcing re-runs on identity changes
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    const id = ++callId.current;
    setLoading(true);
    setError(null);
    fetcherRef.current()
      .then((res) => {
        if (id === callId.current) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (id === callId.current) {
          setError(err);
          setLoading(false);
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  return { data, loading, error, reload, setData };
}
