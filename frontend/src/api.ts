/**
 * JSON HTTP helpers (Bearer from localStorage).
 */
const tokenKey = "r3_token";

export function getToken(): string | null {
  return localStorage.getItem(tokenKey);
}

export function setToken(t: string | null): void {
  if (t) {
    localStorage.setItem(tokenKey, t);
  } else {
    localStorage.removeItem(tokenKey);
  }
}

/**
 * Build Authorization headers when a token exists.
 */
function authHeader(): Record<string, string> {
  const t = getToken();
  if (!t) {
    return {};
  }
  return { Authorization: `Bearer ${t}` };
}

/**
 * Call JSON API; throws on !ok with Error(message).
 */
export async function jsonFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader(), ...init.headers },
  });
  if (r.status === 401) {
    setToken(null);
  }
  if (!r.ok) {
    const text = await r.text();
    let msg = text;
    try {
      const j = JSON.parse(text) as { detail?: string };
      if (j.detail) {
        msg = j.detail;
      }
    } catch {
      // keep raw
    }
    throw new Error(msg || r.statusText);
  }
  if (r.status === 204) {
    return undefined as T;
  }
  return (await r.json()) as T;
}
