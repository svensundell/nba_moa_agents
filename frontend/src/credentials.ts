/** Session-scoped app access token and OpenRouter BYOK key. */

const OPENROUTER_KEY = "nba_moa_openrouter_key";
const APP_ACCESS_KEY = "nba_moa_app_access_token";

export function getOpenRouterKey(): string {
  return sessionStorage.getItem(OPENROUTER_KEY)?.trim() ?? "";
}

export function setOpenRouterKey(value: string): void {
  const trimmed = value.trim();
  if (trimmed) sessionStorage.setItem(OPENROUTER_KEY, trimmed);
  else sessionStorage.removeItem(OPENROUTER_KEY);
}

export function getAppAccessToken(): string {
  return sessionStorage.getItem(APP_ACCESS_KEY)?.trim() ?? "";
}

export function setAppAccessToken(value: string): void {
  const trimmed = value.trim();
  if (trimmed) sessionStorage.setItem(APP_ACCESS_KEY, trimmed);
  else sessionStorage.removeItem(APP_ACCESS_KEY);
}

export function authHeaders(): HeadersInit {
  const headers: Record<string, string> = {};
  const openrouter = getOpenRouterKey();
  const appToken = getAppAccessToken();
  if (openrouter) headers["X-OpenRouter-Key"] = openrouter;
  if (appToken) headers["X-App-Access-Token"] = appToken;
  return headers;
}

export function hasRunCredentials(health: { app_access_required?: boolean } | null): boolean {
  if (!health) return false;
  if (health.app_access_required && !getAppAccessToken()) return false;
  if (!getOpenRouterKey()) return false;
  return true;
}
