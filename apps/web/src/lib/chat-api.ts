import { formatApiError, type ApiErr } from "@/lib/studio-api";

export type CatalogModel = {
  model_id: string;
  display_name: string;
  family: "image" | "chat";
  supports: string[];
  on_disk?: boolean;
  vram_gb_hint?: number;
  default?: boolean;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export type ChatOk = {
  status: string;
  text: string;
  metadata?: Record<string, unknown>;
};

export async function fetchCatalogModels(): Promise<CatalogModel[]> {
  const res = await fetch("/api/models", { cache: "no-store" });
  const raw = await res.text();
  let data: { models?: CatalogModel[] };
  try {
    data = JSON.parse(raw) as { models?: CatalogModel[] };
  } catch {
    throw new Error(
      res.ok
        ? "Model catalog returned invalid JSON"
        : `Could not load model catalog (HTTP ${res.status})`,
    );
  }
  if (!res.ok) {
    throw new Error("Could not load model catalog");
  }
  return data.models ?? [];
}

export function chatModelsAvailable(models: CatalogModel[]): CatalogModel[] {
  return models.filter((m) => m.family === "chat");
}

/** Chat models downloaded on the inference server (selectable in UI). */
export function chatModelsOnServer(models: CatalogModel[]): CatalogModel[] {
  return chatModelsAvailable(models).filter((m) => m.on_disk === true);
}

export function pickDefaultChatModel(models: CatalogModel[]): string | null {
  const onDisk = chatModelsOnServer(models);
  if (onDisk.length === 0) return null;
  const def = onDisk.find((m) => m.default);
  return def?.model_id ?? onDisk[0]?.model_id ?? null;
}

export async function warmupChatModel(modelId: string): Promise<void> {
  const res = await fetch(`/api/models/${encodeURIComponent(modelId)}/load`, {
    method: "POST",
  });
  const data = (await res.json()) as { message?: string } & ApiErr;
  if (!res.ok) {
    throw new Error(formatApiError(data, "Could not load model", res.statusText));
  }
}

export function buildConversationPrompt(messages: ChatMessage[]): string {
  return messages
    .map((m) => `${m.role === "user" ? "User" : "Assistant"}: ${m.content}`)
    .join("\n\n");
}

export async function sendChat(payload: {
  model_id: string;
  prompt: string;
  system_prompt?: string;
  max_tokens?: number;
  temperature?: number;
}): Promise<ChatOk> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = (await res.json()) as ChatOk & ApiErr;
  if (!res.ok) {
    throw new Error(formatApiError(data, "Chat failed", res.statusText));
  }
  return data;
}
