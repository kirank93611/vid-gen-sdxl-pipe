export type ApiErr = {
  message?: string;
  error_code?: string | null;
  request_id?: string;
};

export type GenerateOk = {
  status: string;
  image_base64: string;
  metadata?: Record<string, unknown>;
};

export type JobStatus = {
  status: string;
  image_base64?: string | null;
  iterations?: {
    attempt: number;
    passed: boolean;
    correction?: string | null;
  }[];
  message?: string | null;
  error_code?: string | null;
};

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export function formatApiError(
  err: ApiErr,
  fallback: string,
  statusText?: string,
): string {
  const msg = err.message ?? statusText ?? fallback;
  return err.error_code ? `${msg} (${err.error_code})` : msg;
}
