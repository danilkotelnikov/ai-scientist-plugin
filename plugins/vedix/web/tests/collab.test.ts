/**
 * Block 11 §5.11 — unit tests for collab helpers.
 *
 * Full Yjs round-trip belongs in the Playwright e2e suite (Block 12);
 * here we exercise the pure helper surface and a smoke import to
 * confirm the modules type-check + load under jsdom.
 */
import { describe, expect, it } from "vitest";
import { stringToColor } from "../src/collab/CursorOverlay";

describe("CursorOverlay/stringToColor", () => {
  it("is deterministic for the same input", () => {
    expect(stringToColor("alice")).toBe(stringToColor("alice"));
    expect(stringToColor("Bob")).toBe(stringToColor("Bob"));
  });
  it("produces different colors for different names", () => {
    const a = stringToColor("alice");
    const b = stringToColor("bob");
    expect(a).not.toBe(b);
  });
  it("returns an hsl() string in the 0–359 range", () => {
    const c = stringToColor("anything goes here");
    const match = c.match(/^hsl\((\d+),\s*70%,\s*50%\)$/);
    expect(match).not.toBeNull();
    const hue = Number(match![1]);
    expect(hue).toBeGreaterThanOrEqual(0);
    expect(hue).toBeLessThanOrEqual(360);
  });
  it("never returns a negative hue even for short / unusual inputs", () => {
    for (const sample of ["", "z", "ZZZZ", "тест", "👍"]) {
      const c = stringToColor(sample);
      const match = c.match(/^hsl\((\d+),/);
      expect(match).not.toBeNull();
      expect(Number(match![1])).toBeGreaterThanOrEqual(0);
    }
  });
});

describe("collab module imports", () => {
  it("YjsProvider module loads", async () => {
    const mod = await import("../src/collab/YjsProvider");
    expect(typeof mod.YjsProvider).toBe("function");
    expect(typeof mod.useYjs).toBe("function");
  });
  it("CollabEditor page module loads", async () => {
    const mod = await import("../src/pages/CollabEditor");
    expect(typeof mod.CollabEditor).toBe("function");
  });
});
