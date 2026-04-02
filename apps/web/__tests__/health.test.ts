import { describe, it, expect } from "vitest";
import { GET } from "@/app/api/health/route";

describe("Health API Route", () => {
  it("returns ok status with correct shape", async () => {
    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.data.status).toBe("ok");
    expect(body.data.service).toBe("web");
    expect(body.data.version).toBe("0.1.0");
    expect(body.data.timestamp).toBeDefined();
    expect(body.error).toBeNull();
  });
});
