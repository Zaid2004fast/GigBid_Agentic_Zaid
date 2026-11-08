// Typed API client. Types come from src/lib/api/schema.d.ts, generated from FastAPI's
// OpenAPI schema (npm run gen:api) - do not hand-edit the schema file.
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type JobCard = Schemas["JobCard"];
export type JobDetail = Schemas["JobDetail"];
export type ApprovalOut = Schemas["ApprovalOut"];
export type PipelineCard = Schemas["PipelineCard"];
export type RunOut = Schemas["RunOut"];
export type RunDetail = Schemas["RunDetail"];
export type SettingsModel = Schemas["SettingsModel"];
export type Analytics = Schemas["Analytics"];
export type MemoryItem = Schemas["MemoryItem"];
export type Health = Schemas["Health"];
export type UserOut = Schemas["UserOut"];

export const api = createClient<paths>({ baseUrl: "", credentials: "include" });

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Unwraps openapi-fetch results into data-or-throw.
export async function call<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (error !== undefined || !response.ok) {
    const detail = (error as { detail?: unknown })?.detail;
    throw new ApiError(response.status, typeof detail === "string" ? detail : JSON.stringify(detail ?? error ?? response.statusText));
  }
  return data as T;
}