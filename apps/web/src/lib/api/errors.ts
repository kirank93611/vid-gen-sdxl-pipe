import { ERROR_HELP } from "@/lib/studio-setting-help";

export type ApiErr = {
  message?: string;
  error_code?: string | null;
  request_id?: string;
  details?: string | null;
};

export function formatApiError(
  err: ApiErr,
  fallback: string,
  statusText?: string,
  retryAfterSec?: number,
): string {
  const code = err.error_code ?? undefined;
  const friendly = code ? ERROR_HELP[code] : undefined;
  const msg =
    friendly ??
    err.message ??
    statusText ??
    fallback;
  const detail = err.details?.trim();
  let base = msg;
  if (code && !friendly) {
    base = `${msg} (${code})`;
  }
  if (retryAfterSec != null && retryAfterSec > 0) {
    base = `${base} Retry in ~${retryAfterSec}s.`;
  }
  if (err.request_id) {
    base = `${base} (request ${err.request_id})`;
  }
  return detail ? `${base} — ${detail}` : base;
}
