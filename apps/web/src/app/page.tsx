import { GenerateForm } from "@/components/generate-form";

export default function Home() {
  return (
    <div className="flex flex-col flex-1 items-center bg-zinc-50 font-sans dark:bg-zinc-950">
      <main className="flex w-full max-w-3xl flex-1 flex-col gap-10 px-6 py-16 sm:py-24">
        <div className="flex flex-col gap-3">
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">
            SDXL generate
          </h1>
          <p className="text-base leading-relaxed text-zinc-600 dark:text-zinc-400">
            Calls the inference API through a Next.js route handler so the API
            key stays on the server. Start the API with{" "}
            <code className="rounded bg-zinc-200 px-1.5 py-0.5 text-sm dark:bg-zinc-800">
              make run
            </code>{" "}
            from the repo root (default{" "}
            <code className="rounded bg-zinc-200 px-1.5 py-0.5 text-sm dark:bg-zinc-800">
              :8001
            </code>
            ).
          </p>
        </div>
        <GenerateForm />
      </main>
    </div>
  );
}
