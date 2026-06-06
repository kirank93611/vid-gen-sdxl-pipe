"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Bot, Loader2, Send, Sparkles, User } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  buildConversationPrompt,
  type CatalogModel,
  type ChatMessage,
  chatModelsOnServer,
  fetchCatalogModels,
  pickDefaultChatModel,
  sendChat,
  warmupChatModel,
} from "@/lib/chat-api";
import { cn } from "@/lib/utils";

const DEFAULT_SYSTEM =
  "You are a helpful creative assistant for a visual product studio. Be concise and clear.";

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function ChatInterface() {
  const [catalog, setCatalog] = useState<CatalogModel[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [modelId, setModelId] = useState<string>("");
  const [systemPrompt, setSystemPrompt] = useState(DEFAULT_SYSTEM);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelReady, setModelReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const warmupGenRef = useRef(0);

  const chatModels = chatModelsOnServer(catalog);
  const selected = chatModels.find((m) => m.model_id === modelId);

  useEffect(() => {
    void fetchCatalogModels()
      .then((models) => {
        setCatalog(models);
        const id = pickDefaultChatModel(models);
        if (id) setModelId(id);
      })
      .catch((e) =>
        setCatalogError(e instanceof Error ? e.message : "Failed to load models"),
      );
  }, []);

  useEffect(() => {
    if (!modelId || !chatModels.some((m) => m.model_id === modelId)) {
      setModelReady(false);
      return;
    }

    const gen = ++warmupGenRef.current;
    setModelLoading(true);
    setModelReady(false);
    setError(null);

    void warmupChatModel(modelId)
      .then(() => {
        if (warmupGenRef.current === gen) setModelReady(true);
      })
      .catch((e) => {
        if (warmupGenRef.current === gen) {
          setError(e instanceof Error ? e.message : "Failed to load model");
          setModelReady(false);
        }
      })
      .finally(() => {
        if (warmupGenRef.current === gen) setModelLoading(false);
      });
  }, [modelId, catalog]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, loading]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading || !modelId || !modelReady) return;

    const userMsg: ChatMessage = {
      id: newId(),
      role: "user",
      content: text,
    };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput("");
    setError(null);
    setLoading(true);

    try {
      const data = await sendChat({
        model_id: modelId,
        system_prompt: systemPrompt.trim() || undefined,
        prompt: buildConversationPrompt(nextMessages),
        max_tokens: 1024,
        temperature: 0.7,
      });
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "assistant",
          content: data.text,
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chat failed");
    } finally {
      setLoading(false);
    }
  }, [input, loading, modelId, messages, selected, systemPrompt]);

  return (
    <div className="mx-auto flex h-[calc(100vh-3.5rem)] max-w-4xl flex-col px-4 py-4 sm:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-4 shrink-0"
      >
        <div className="flex flex-wrap items-center gap-2">
          <Sparkles className="h-5 w-5 text-[var(--studio-lime)]" />
          <h1 className="text-lg font-semibold">Chat</h1>
          <Badge variant="lime" className="normal-case">
            GGUF · GPU
          </Badge>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Text models run on the inference API. Image generation stays on the
          Image tab.
        </p>
      </motion.div>

      <div className="mb-3 shrink-0 rounded-xl border border-border bg-card/80 p-3">
        <label
          htmlFor="chat-model"
          className="mb-1.5 block text-xs font-medium text-muted-foreground"
        >
          Model
        </label>
        <select
          id="chat-model"
          value={modelId}
          onChange={(e) => setModelId(e.target.value)}
          disabled={loading || modelLoading || chatModels.length === 0}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-[var(--studio-lime)] focus:outline-none focus:ring-1 focus:ring-[var(--studio-lime)]"
        >
          {chatModels.length === 0 && (
            <option value="">No chat models on server</option>
          )}
          {chatModels.map((m) => (
            <option key={m.model_id} value={m.model_id}>
              {m.display_name}
              {m.default ? " · default" : ""}
              {m.vram_gb_hint ? ` · ~${m.vram_gb_hint}GB` : ""}
            </option>
          ))}
        </select>
        {catalogError && (
          <p className="mt-2 text-xs text-red-400">{catalogError}</p>
        )}
        {modelLoading && (
          <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin text-[var(--studio-lime)]" />
            Loading weights into VRAM…
          </p>
        )}
        {modelReady && selected && !modelLoading && (
          <p className="mt-2 text-xs text-[var(--studio-lime)]">
            {selected.display_name} ready
          </p>
        )}
        {chatModels.length === 0 && !catalogError && (
          <p className="mt-2 text-xs text-amber-400">
            Download on GPU:{" "}
            <code className="rounded bg-muted px-1">
              make spheron-download-llm
            </code>
          </p>
        )}
      </div>

      <div
        ref={scrollRef}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-xl border border-border bg-card/40 p-4"
      >
        {messages.length === 0 && !loading && (
          <p className="text-center text-sm text-muted-foreground">
            Pick a model and send a message. First reply may take a minute while
            weights load into VRAM.
          </p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={cn(
              "flex gap-3",
              m.role === "user" ? "justify-end" : "justify-start",
            )}
          >
            {m.role === "assistant" && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent">
                <Bot className="h-4 w-4 text-[var(--studio-lime)]" />
              </div>
            )}
            <div
              className={cn(
                "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
                m.role === "user"
                  ? "bg-[var(--studio-lime)] text-black"
                  : "border border-border bg-card",
              )}
            >
              <p className="whitespace-pre-wrap">{m.content}</p>
            </div>
            {m.role === "user" && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent">
                <User className="h-4 w-4" />
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-[var(--studio-lime)]" />
            Generating…
          </div>
        )}
      </div>

      {error && (
        <p className="mt-2 shrink-0 text-sm text-red-400" role="alert">
          {error}
        </p>
      )}

      <details className="mt-3 shrink-0 text-sm">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
          System prompt
        </summary>
        <Textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={2}
          disabled={loading}
          className="mt-2 text-xs"
        />
      </details>

      <Separator className="my-3 shrink-0" />

      <div className="flex shrink-0 gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message…"
          rows={2}
          disabled={loading || modelLoading || !modelId}
          className="min-h-[52px] flex-1 resize-none"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void handleSend();
            }
          }}
        />
        <Button
          type="button"
          variant="lime"
          size="icon"
          className="h-auto min-h-[52px] w-12 shrink-0"
          disabled={loading || modelLoading || !modelReady || !input.trim() || !modelId}
          onClick={() => void handleSend()}
          aria-label="Send"
        >
          {loading ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <Send className="h-5 w-5" />
          )}
        </Button>
      </div>
      <p className="mt-2 shrink-0 text-center text-xs text-muted-foreground">
        Enter to send · Shift+Enter for newline
      </p>
    </div>
  );
}
