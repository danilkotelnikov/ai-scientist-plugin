/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  // Yjs WebSocket reconciliation server base URL (Block 11 §5.10 / §5.11).
  // Defaults to wss://collab.vedix.ai when unset.
  readonly VITE_YJS_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
