/**
 * §5.11 — Presence cursors layered over the collab editor.
 *
 * Reads peer state from the y-websocket awareness channel and renders
 * a per-peer label at the most-recently-broadcast mouse position.
 * Awareness state is `{ user: { name, color }, cursor: {x, y} | null }`.
 */
import { useEffect, useState } from "react";
import { useYjs } from "./YjsProvider";

interface PresenceState {
  user: { name: string; color: string };
  cursor: { x: number; y: number } | null;
}

interface CursorOverlayProps {
  /** The current user's display name. */
  myName: string;
}

export function CursorOverlay({ myName }: CursorOverlayProps): JSX.Element {
  const { provider } = useYjs();
  const [peers, setPeers] = useState<Record<number, PresenceState>>({});

  useEffect(() => {
    const awareness = provider.awareness;
    awareness.setLocalStateField("user", {
      name: myName,
      color: stringToColor(myName),
    });
    const onMove = (e: MouseEvent): void => {
      awareness.setLocalStateField("cursor", {
        x: e.clientX,
        y: e.clientY,
      });
    };
    window.addEventListener("mousemove", onMove);
    const refresh = (): void => {
      const next: Record<number, PresenceState> = {};
      awareness.getStates().forEach((state, clientId) => {
        if (clientId === awareness.clientID) return;
        const s = state as Partial<PresenceState>;
        if (s.user) {
          next[clientId] = {
            user: s.user,
            cursor: s.cursor ?? null,
          };
        }
      });
      setPeers(next);
    };
    awareness.on("change", refresh);
    refresh();
    return () => {
      window.removeEventListener("mousemove", onMove);
      awareness.off("change", refresh);
      // Clear our own cursor so other peers stop drawing it on disconnect.
      awareness.setLocalState(null);
    };
  }, [provider, myName]);

  return (
    <>
      {Object.entries(peers).map(([id, p]) =>
        p.cursor ? (
          <div
            key={id}
            data-testid={`peer-cursor-${id}`}
            style={{
              position: "fixed",
              left: p.cursor.x,
              top: p.cursor.y,
              pointerEvents: "none",
              background: p.user.color,
              color: "white",
              padding: "2px 6px",
              borderRadius: 3,
              fontSize: 12,
              zIndex: 9999,
              transform: "translate(8px, 8px)",
            }}
          >
            {p.user.name}
          </div>
        ) : null,
      )}
    </>
  );
}

/** Deterministic HSL colour from a string (so a user's name → same hue across tabs). */
export function stringToColor(s: string): string {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0;
  return `hsl(${((h % 360) + 360) % 360}, 70%, 50%)`;
}
