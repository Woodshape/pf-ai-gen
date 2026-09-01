import type { EngineResult } from "./types";

const requestId = () => crypto.randomUUID();

export async function execute(operation: string, payload: Record<string, unknown>): Promise<EngineResult> {
  const response = await fetch("/api/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ protocolVersion: "1", requestId: requestId(), operation, payload }),
  });
  const body = await response.json();
  if (!body.ok) {
    const error = new Error(body.error?.message || "Request failed") as Error & { data?: Record<string, unknown> };
    error.data = body.error;
    throw error;
  }
  return body.result;
}

export async function loadCatalog() {
  const response = await fetch("/catalog.json");
  if (!response.ok) throw new Error("Catalog failed to load");
  return response.json();
}

export async function loadNpcCatalog() {
  const response = await fetch("/npc.json");
  if (!response.ok) throw new Error("NPC catalog failed to load");
  return response.json();
}

export const newChangeId = (field: string) => `${field}-${requestId()}`;
