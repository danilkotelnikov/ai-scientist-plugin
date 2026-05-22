/**
 * §5.10 / §5.11 — Yjs document context.
 *
 * Boots a fresh ``Y.Doc`` for the given ``docId`` and hands it to
 * descendants together with the ``y-websocket`` provider. Children
 * inside the tree read both via ``useYjs()``. The provider is bound
 * to the URL convention shared with the Python WebSocket server in
 * ``app/workers/yjs_server.py`` — every CRDT room lives at
 * ``/doc/{docId}``.
 */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";

export interface YjsContextValue {
  doc: Y.Doc;
  provider: WebsocketProvider;
  status: "connecting" | "connected" | "disconnected";
}

const YjsContext = createContext<YjsContextValue | null>(null);

const DEFAULT_WS_URL = "wss://collab.vedix.ai";

interface YjsProviderProps {
  docId: string;
  /** Override the base URL used by y-websocket. */
  wsBaseUrl?: string;
  children: ReactNode;
}

export function YjsProvider({
  docId,
  wsBaseUrl,
  children,
}: YjsProviderProps): JSX.Element {
  const [value, setValue] = useState<YjsContextValue | null>(null);

  useEffect(() => {
    const base = (wsBaseUrl ?? import.meta.env.VITE_YJS_WS_URL ?? DEFAULT_WS_URL).replace(
      /\/+$/,
      "",
    );
    const doc = new Y.Doc();
    // y-websocket appends the room name to the base URL as a sub-path.
    // We feed it ``doc/<id>`` so the server, which expects /doc/<id>,
    // sees the same path Python's room parser walks.
    const provider = new WebsocketProvider(base, `doc/${docId}`, doc);
    const next: YjsContextValue = {
      doc,
      provider,
      status: "connecting",
    };
    setValue(next);
    const onStatus = ({ status }: { status: string }): void => {
      setValue((prev) =>
        prev
          ? {
              ...prev,
              status:
                status === "connected"
                  ? "connected"
                  : status === "disconnected"
                    ? "disconnected"
                    : "connecting",
            }
          : prev,
      );
    };
    provider.on("status", onStatus);
    return () => {
      provider.off("status", onStatus);
      provider.destroy();
      doc.destroy();
    };
  }, [docId, wsBaseUrl]);

  if (!value) {
    return (
      <div className="p-8 text-center text-gray-500">
        Connecting to collaboration server…
      </div>
    );
  }
  return <YjsContext.Provider value={value}>{children}</YjsContext.Provider>;
}

export function useYjs(): YjsContextValue {
  const ctx = useContext(YjsContext);
  if (!ctx) {
    throw new Error(
      "useYjs() called outside a <YjsProvider>; wrap the component tree first",
    );
  }
  return ctx;
}
