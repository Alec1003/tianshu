const CURRENT_PREFIX = "tianshu";
const LEGACY_PREFIX = "ai" + "cc";

export function legacyStorageKey(key: string): string {
  return key.split(CURRENT_PREFIX).join(LEGACY_PREFIX);
}

export function readStorageItem(key: string): string | null {
  if (typeof window === "undefined") return null;
  const current = window.localStorage.getItem(key);
  if (current !== null) return current;

  const legacyKey = legacyStorageKey(key);
  const legacy = window.localStorage.getItem(legacyKey);
  if (legacy !== null) {
    try {
      window.localStorage.setItem(key, legacy);
    } catch {
      // ignore quota / privacy mode errors
    }
  }
  return legacy;
}

export function writeStorageItem(key: string, value: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(key, value);
  window.localStorage.removeItem(legacyStorageKey(key));
}

export function removeStorageItem(key: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(key);
  window.localStorage.removeItem(legacyStorageKey(key));
}

export function legacyEventName(eventName: string): string {
  return eventName.split(CURRENT_PREFIX).join(LEGACY_PREFIX);
}
