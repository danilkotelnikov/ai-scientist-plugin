/**
 * Lightweight JWT storage. The backend issues tokens via `POST /v1/api/auth/login`
 * (Block 8); we just hold the token in localStorage and inject it via the API
 * client's `Authorization: Bearer …` header. SSE uses a `?token=` query param
 * since EventSource cannot set request headers.
 */

const KEY = "vedix_jwt";
const STORAGE_EVENT = "vedix-auth-changed";

function safeStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    // Storage can throw in private-mode Safari or sandboxed iframes.
    return null;
  }
}

export function setToken(token: string): void {
  const storage = safeStorage();
  if (!storage) return;
  storage.setItem(KEY, token);
  window.dispatchEvent(new CustomEvent(STORAGE_EVENT));
}

export function getToken(): string | null {
  const storage = safeStorage();
  if (!storage) return null;
  return storage.getItem(KEY);
}

export function clearToken(): void {
  const storage = safeStorage();
  if (!storage) return;
  storage.removeItem(KEY);
  window.dispatchEvent(new CustomEvent(STORAGE_EVENT));
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}

/**
 * Subscribe to token changes. Returns the unsubscribe callback.
 *
 * Listens to both the standard `storage` event (fires when another tab
 * mutates localStorage) and our custom `vedix-auth-changed` event (fires
 * in the current tab on `setToken` / `clearToken`).
 */
export function onAuthChange(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => callback();
  window.addEventListener("storage", handler);
  window.addEventListener(STORAGE_EVENT, handler);
  return () => {
    window.removeEventListener("storage", handler);
    window.removeEventListener(STORAGE_EVENT, handler);
  };
}
