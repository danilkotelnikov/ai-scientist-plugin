import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock auth.ts to avoid touching real localStorage.
let token: string | null = null;
vi.mock("../src/lib/auth", () => ({
  getToken: () => token,
  setToken: (t: string) => {
    token = t;
  },
  clearToken: () => {
    token = null;
  },
  isAuthenticated: () => token !== null,
  onAuthChange: () => () => {},
}));

// Import AFTER the mock is registered so the api module picks it up.
const { api, ApiError, buildUrl } = await import("../src/api/client");
const { createJob, getJob } = await import("../src/api/jobs");

interface MockResponseInit {
  status?: number;
  body?: unknown;
  text?: string;
}

function mockOnce({ status = 200, body = {}, text }: MockResponseInit) {
  global.fetch = vi.fn(async () => {
    const payload = text ?? JSON.stringify(body);
    return {
      ok: status >= 200 && status < 300,
      status,
      text: async () => payload,
      json: async () => JSON.parse(payload),
    } as Response;
  }) as unknown as typeof fetch;
}

describe("api client", () => {
  beforeEach(() => {
    token = null;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("buildUrl skips undefined/null and serializes the rest", () => {
    expect(buildUrl("/path", { a: 1, b: undefined, c: null, d: "x" })).toBe(
      "/path?a=1&d=x",
    );
    expect(buildUrl("/empty", {})).toBe("/empty");
  });

  it("attaches Authorization header when token present", async () => {
    token = "deadbeef";
    const spy = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => "{}",
      json: async () => ({ ok: true }),
    })) as unknown as typeof fetch;
    global.fetch = spy;

    await api<{ ok: boolean }>("/v1/api/health");

    expect(spy).toHaveBeenCalledTimes(1);
    const [, init] = (spy as unknown as { mock: { calls: [string, RequestInit][] } })
      .mock.calls[0];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer deadbeef");
  });

  it("throws ApiError on non-2xx and surfaces status + body", async () => {
    mockOnce({ status: 500, text: "boom" });
    await expect(api("/v1/api/jobs/missing")).rejects.toBeInstanceOf(ApiError);
  });

  it("clears token on 401", async () => {
    token = "expired";
    mockOnce({ status: 401, text: "expired" });
    await expect(api("/v1/api/jobs")).rejects.toBeInstanceOf(ApiError);
    expect(token).toBeNull();
  });

  it("createJob POSTs payload to /v1/api/jobs", async () => {
    const spy = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => '{"job_id":"abc","state":"queued"}',
      json: async () => ({ job_id: "abc", state: "queued" }),
    })) as unknown as typeof fetch;
    global.fetch = spy;

    const result = await createJob({
      topic: "Investigate the effect of X on Y",
      discipline: "computer_science",
      language: "en",
      venue: "preprint",
      hypothesis_style: "confirmatory",
      experiment_type: "computational",
      primary_metric: "accuracy",
      expected_direction: "increase",
      tolerance: 0.05,
    });

    expect(result).toEqual({ job_id: "abc", state: "queued" });
    const [url, init] = (spy as unknown as { mock: { calls: [string, RequestInit][] } })
      .mock.calls[0];
    expect(url).toMatch(/\/v1\/api\/jobs$/);
    expect(init.method).toBe("POST");
    expect(init.body).toContain("Investigate the effect");
  });

  it("getJob fetches /v1/api/jobs/:id", async () => {
    mockOnce({
      body: { job_id: "abc", state: "running", phase: "experiment", progress: 42 },
    });
    const status = await getJob("abc");
    expect(status.state).toBe("running");
    expect(status.progress).toBe(42);
  });
});
