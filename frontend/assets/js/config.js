/**
 * BUYWISE AI — Frontend Configuration & Utilities
 * Client-side session management, formatting, and comparison state.
 * Strictly zero backend secrets or API keys.
 */

export const CONFIG = {
  APP_NAME: "BUYWISE AI",
  TAGLINE: "Discover smarter. Compare deeper. Spend responsibly.",
  API_BASE: "", // Same-origin relative path
  DEFAULT_CURRENCY: "USD",
  MAX_COMPARE_ITEMS: 4,
  STORAGE_KEYS: {
    SESSION_ID: "buywise_guest_session_id",
    SESSION_IDENTIFIER: "buywise_guest_session_identifier",
    COMPARE_IDS: "buywise_compare_ids",
  },
  CATEGORIES: [
    "All",
    "Audio",
    "Wearables",
    "Computing",
    "Electronics",
    "Smart Home",
    "Gaming",
  ],
};

/**
 * Generate a random UUID v4 string for guest identification.
 */
export function generateUUID() {
  if (crypto && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Retrieve or generate the persistent guest session identifier.
 */
export function getSessionIdentifier() {
  let identifier = localStorage.getItem(CONFIG.STORAGE_KEYS.SESSION_IDENTIFIER);
  if (!identifier) {
    identifier = `guest_${generateUUID().replace(/-/g, "").substring(0, 16)}`;
    localStorage.setItem(CONFIG.STORAGE_KEYS.SESSION_IDENTIFIER, identifier);
  }
  return identifier;
}

/**
 * Retrieve the canonical database session ID if resolved, otherwise fallback to identifier.
 */
export function getSessionId() {
  return localStorage.getItem(CONFIG.STORAGE_KEYS.SESSION_ID) || getSessionIdentifier();
}

/**
 * Store canonical backend-assigned ShoppingSession UUID.
 */
export function setSessionId(sessionId) {
  if (sessionId) {
    localStorage.setItem(CONFIG.STORAGE_KEYS.SESSION_ID, sessionId);
  }
}

/**
 * Reset the guest session and clear session-specific local state.
 */
export function resetSession() {
  localStorage.removeItem(CONFIG.STORAGE_KEYS.SESSION_ID);
  localStorage.removeItem(CONFIG.STORAGE_KEYS.SESSION_IDENTIFIER);
  localStorage.removeItem(CONFIG.STORAGE_KEYS.COMPARE_IDS);
  return getSessionIdentifier();
}

/**
 * Format numerical prices with localized currency formatting.
 */
export function formatPrice(amount, currency = "USD") {
  if (amount === null || amount === undefined || isNaN(amount)) {
    return "N/A";
  }
  const curr = (currency || "USD").toUpperCase();
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: curr,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${curr} ${Number(amount).toFixed(2)}`;
  }
}

/**
 * Format ISO datetime strings to human-readable format.
 */
export function formatDate(isoString) {
  if (!isoString) return "N/A";
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

/**
 * Get list of product IDs selected for comparison.
 */
export function getCompareList() {
  try {
    const raw = localStorage.getItem(CONFIG.STORAGE_KEYS.COMPARE_IDS);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/**
 * Toggle a product ID in the comparison list (maximum 4).
 * Returns { added: boolean, list: string[], error: string | null }
 */
export function toggleCompareItem(productId) {
  let list = getCompareList();
  const exists = list.includes(productId);

  if (exists) {
    list = list.filter((id) => id !== productId);
    localStorage.setItem(CONFIG.STORAGE_KEYS.COMPARE_IDS, JSON.stringify(list));
    return { added: false, list, error: null };
  }

  if (list.length >= CONFIG.MAX_COMPARE_ITEMS) {
    return {
      added: false,
      list,
      error: `Comparison limit reached (max ${CONFIG.MAX_COMPARE_ITEMS} products). Remove one to add another.`,
    };
  }

  list.push(productId);
  localStorage.setItem(CONFIG.STORAGE_KEYS.COMPARE_IDS, JSON.stringify(list));
  return { added: true, list, error: null };
}

/**
 * Clear all items from comparison list.
 */
export function clearCompareList() {
  localStorage.removeItem(CONFIG.STORAGE_KEYS.COMPARE_IDS);
  return [];
}
