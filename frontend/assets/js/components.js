/**
 * BUYWISE AI — Reusable UI Components
 * Accessible, semantic HTML renderers for products, badges, modals, and toasts.
 */

import { formatPrice, formatDate } from "./config.js";

/**
 * Fallback SVG image placeholder when product image is missing or invalid.
 * Uses a pure base64-encoded SVG data URI to completely eliminate HTML attribute
 * escaping bugs, syntax errors, and literal text leaks in img onerror handlers.
 */
export const PLACEHOLDER_IMAGE = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIzMDAiIGhlaWdodD0iMjAwIiB2aWV3Qm94PSIwIDAgMzAwIDIwMCIgZmlsbD0ibm9uZSI+PHJlY3Qgd2lkdGg9IjMwMCIgaGVpZ2h0PSIyMDAiIGZpbGw9IiMxZTI5M2IiLz48cGF0aCBkPSJNMTAwIDYwaDEwMHY4MEgxMDB6IiBzdHJva2U9IiM0NzU1NjkiIHN0cm9rZS13aWR0aD0iMiIvPjxwYXRoIGQ9Ik0xMTAgMTIwbDIwLTI1IDIwIDE1IDI1LTMwIDI1IDQwSDEwMHoiIGZpbGw9IiM0NzU1NjkiLz48Y2lyY2xlIGN4PSIxMjUiIGN5PSI4NSIgcj0iOSIgZmlsbD0iIzQ3NTU2OSIvPjwvc3ZnPg==";

/**
 * Validates an image URL and returns either the clean URL or the safe placeholder.
 */
export function getSafeImageUrl(url) {
  if (!url || typeof url !== "string") {
    return PLACEHOLDER_IMAGE;
  }
  const clean = url.trim();
  if (clean.startsWith("https://") || clean.startsWith("http://") || clean.startsWith("data:image/")) {
    return clean;
  }
  return PLACEHOLDER_IMAGE;
}

/**
 * Standardized, safe onerror attribute string for <img> tags.
 */
export const IMG_FALLBACK_ATTR = `onerror="this.onerror=null;this.src='${PLACEHOLDER_IMAGE}';this.classList.add('opacity-60');"`;

/**
 * Render a product card for grids.
 */
export function renderProductCard(product, isCompared = false, activeMandate = null) {
  const offerCurrency = (product.offers?.[0]?.currency || "USD").toUpperCase();
  const lowestPrice = product.lowest_price !== null ? formatPrice(product.lowest_price, offerCurrency) : "Check Offers";
  const offersCount = product.offers ? product.offers.length : 0;
  const bestRetailer = product.lowest_price_retailer || product.offers?.[0]?.retailer_name || "Catalog";
  const isSynthetic = product.is_synthetic !== false;
  const warnings = product.data_quality_warnings || [];
  const hasWarnings = warnings.length > 0;

  // Check currency alignment with active mandate if configured
  const mandateCurrency = activeMandate?.currency ? activeMandate.currency.toUpperCase() : null;
  const isCurrencyMismatch = mandateCurrency && mandateCurrency !== offerCurrency;

  // Star rating representation
  let ratingHtml = "";
  if (product.rating) {
    const stars = Math.min(5, Math.max(0, Math.round(product.rating)));
    const starsStr = "★".repeat(stars) + "☆".repeat(5 - stars);
    ratingHtml = `
      <div class="flex items-center gap-1.5 text-xs text-amber-400">
        <span class="tracking-widest">${starsStr}</span>
        <span class="text-slate-400 font-medium">(${product.rating.toFixed(1)}${product.rating_count ? ` / ${product.rating_count}` : ""})</span>
      </div>
    `;
  }

  const compareBtnClass = isCompared
    ? "bg-burnt-orange text-white border-burnt-orange shadow-sm"
    : "bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700 hover:text-white";

  return `
    <div class="group flex flex-col bg-slate-900 border border-slate-800/80 rounded-2xl overflow-hidden hover:border-slate-700 transition-all duration-300 hover:shadow-xl hover:shadow-black/40" data-product-id="${product.id}">
      <!-- Image & Badges Container -->
      <div class="relative w-full h-48 bg-slate-950/60 flex items-center justify-center overflow-hidden p-4 border-b border-slate-800/60">
        <img
          src="${getSafeImageUrl(product.image_url)}"
          alt="${escapeHtml(product.name)}"
          class="max-h-full max-w-full object-contain transition-transform duration-300 group-hover:scale-105"
          loading="lazy"
          ${IMG_FALLBACK_ATTR}
        />
        
        <!-- Provenance & Quality Badges -->
        <div class="absolute top-3 left-3 flex flex-col gap-1.5 max-w-[70%]">
          ${
            isSynthetic
              ? `<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 backdrop-blur-sm">
                   <span class="w-1.5 h-1.5 rounded-full bg-indigo-400"></span> Synthetic Demo
                 </span>`
              : `<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 backdrop-blur-sm">
                   <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> Live Channel3
                 </span>`
          }
          ${
            hasWarnings
              ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-500/10 text-amber-300 border border-amber-500/30 truncate" title="${escapeHtml(warnings.join(' | '))}">
                   ⚠ Data Notice
                 </span>`
              : ""
          }
          ${
            isCurrencyMismatch
              ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-rose-500/10 text-rose-300 border border-rose-500/30" title="Item currency is ${offerCurrency}, but your active mandate is in ${mandateCurrency}. Cross-currency purchases are blocked by policy.">
                   ⚠ ${offerCurrency} vs ${mandateCurrency}
                 </span>`
              : ""
          }
        </div>

        <!-- Category Badge -->
        <div class="absolute top-3 right-3">
          <span class="px-2.5 py-1 rounded-full text-[11px] font-medium bg-slate-800/80 text-slate-300 border border-slate-700/60 backdrop-blur-sm">
            ${escapeHtml(product.category)}
          </span>
        </div>
      </div>

      <!-- Card Body -->
      <div class="flex-1 flex flex-col p-5">
        <div class="mb-1 flex items-center justify-between">
          <span class="text-xs font-semibold uppercase tracking-wider text-burnt-orange">
            ${escapeHtml(product.brand)}
          </span>
        </div>
        <h3 class="text-base font-bold text-white line-clamp-2 leading-snug mb-2" title="${escapeHtml(product.name)}">
          ${escapeHtml(product.name)}
        </h3>

        ${ratingHtml}

        <p class="text-xs text-slate-400 line-clamp-2 mt-2 mb-4 leading-relaxed">
          ${escapeHtml(product.description || "Specifications and multi-retailer price comparison available.")}
        </p>

        <!-- Pricing & Best Offer -->
        <div class="mt-auto pt-3 border-t border-slate-800/80 flex items-end justify-between">
          <div>
            <div class="text-[11px] text-slate-400 font-medium">Best Offer (${escapeHtml(bestRetailer)})</div>
            <div class="text-xl font-extrabold text-white tracking-tight">${lowestPrice}</div>
          </div>
          <div class="text-right">
            <span class="inline-block text-[11px] font-medium text-slate-400 bg-slate-800/60 px-2 py-1 rounded-md border border-slate-700/40">
              ${offersCount} ${offersCount === 1 ? "offer" : "offers"}
            </span>
          </div>
        </div>

        <!-- Action Controls -->
        <div class="mt-4 grid grid-cols-2 gap-2 pt-2">
          <button
            type="button"
            class="js-btn-details w-full py-2 px-3 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors focus:ring-2 focus:ring-burnt-orange/50 focus:outline-none text-center"
            data-id="${product.id}"
          >
            View Offers
          </button>
          <button
            type="button"
            class="js-btn-compare w-full py-2 px-3 text-xs font-semibold rounded-lg border transition-colors focus:ring-2 focus:ring-burnt-orange/50 focus:outline-none text-center ${compareBtnClass}"
            data-id="${product.id}"
          >
            ${isCompared ? "✓ Compared" : "+ Compare"}
          </button>
        </div>
      </div>
    </div>
  `;
}

/**
 * Render complete Product Detail modal content.
 */
export function renderProductDetailModal(product) {
  const isSynthetic = product.is_synthetic !== false;
  const lowestPrice = product.lowest_price !== null ? formatPrice(product.lowest_price, product.offers?.[0]?.currency || "USD") : "N/A";
  const bestRetailer = product.lowest_price_retailer || "Catalog Best";
  const offers = product.offers || [];

  // Specifications rows
  const specs = product.specifications || {};
  const specRows = Object.entries(specs)
    .filter(([key]) => !key.startsWith("_") && key !== "rating" && key !== "rating_count")
    .map(([key, val]) => `
      <tr class="border-b border-slate-800/60 last:border-b-0 hover:bg-slate-800/30">
        <td class="py-2.5 px-3 text-xs font-semibold text-slate-400 capitalize w-1/3">${escapeHtml(key.replace(/_/g, " "))}</td>
        <td class="py-2.5 px-3 text-xs text-white font-medium">${escapeHtml(typeof val === "object" ? JSON.stringify(val) : String(val))}</td>
      </tr>
    `)
    .join("");

  // Competing Retailer Offers rows
  const offerRows = offers.map((offer) => {
    const isOfferSynthetic = offer.is_synthetic !== false;
    const isStock = ["IN_STOCK", "LIMITED_STOCK", "LOW_STOCK"].includes(offer.availability.toUpperCase());
    const stockClass = isStock ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" : "text-rose-400 bg-rose-500/10 border-rose-500/20";
    const strikePrice = offer.compare_at_price && offer.compare_at_price > offer.price
      ? `<span class="line-through text-slate-500 text-xs mr-1.5">${formatPrice(offer.compare_at_price, offer.currency)}</span>`
      : "";

    return `
      <tr class="border-b border-slate-800/60 last:border-b-0 hover:bg-slate-800/30">
        <td class="py-3 px-3">
          <div class="font-bold text-white text-xs">${escapeHtml(offer.retailer_name)}</div>
          <div class="text-[10px] text-slate-400">${isOfferSynthetic ? "Simulated Demo Store" : "Verified Merchant"}</div>
        </td>
        <td class="py-3 px-3">
          <div class="text-sm font-extrabold text-white">${strikePrice}${formatPrice(offer.price, offer.currency)}</div>
        </td>
        <td class="py-3 px-3">
          <span class="inline-flex px-2 py-0.5 rounded text-[10px] font-semibold border ${stockClass}">
            ${escapeHtml(offer.availability.replace(/_/g, " "))}
          </span>
        </td>
        <td class="py-3 px-3 text-right">
          <a
            href="${offer.product_url}"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg bg-burnt-orange hover:bg-burnt-orange/90 text-white transition-colors"
          >
            Visit Merchant ↗
          </a>
        </td>
      </tr>
    `;
  }).join("");

  return `
    <div class="p-6">
      <!-- Modal Header -->
      <div class="flex items-start justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="text-xs font-bold uppercase tracking-wider text-burnt-orange">${escapeHtml(product.brand)}</span>
            <span class="text-slate-500">•</span>
            <span class="text-xs font-medium text-slate-400">${escapeHtml(product.category)}</span>
            ${
              isSynthetic
                ? `<span class="ml-2 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">Synthetic Demo Item</span>`
                : `<span class="ml-2 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Live Channel3 Item</span>`
            }
          </div>
          <h2 class="text-xl font-extrabold text-white">${escapeHtml(product.name)}</h2>
        </div>
        <button type="button" class="js-close-modal p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>

      <!-- Main Overview Grid -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6 py-6 border-b border-slate-800">
        <div class="bg-slate-950/60 rounded-xl p-4 flex items-center justify-center border border-slate-800/80">
          <img
            src="${getSafeImageUrl(product.image_url)}"
            alt="${escapeHtml(product.name)}"
            class="max-h-48 object-contain"
            ${IMG_FALLBACK_ATTR}
          />
        </div>
        <div class="md:col-span-2 flex flex-col justify-between">
          <div>
            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">Description</h4>
            <p class="text-sm text-slate-300 leading-relaxed">${escapeHtml(product.description || "No marketing description provided.")}</p>
            
            ${
              product.data_quality_warnings && product.data_quality_warnings.length > 0
                ? `<div class="mt-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300">
                     <strong class="font-semibold block mb-0.5">Data Quality Notices:</strong>
                     <ul class="list-disc list-inside space-y-0.5 text-[11px] text-amber-400/90">
                       ${product.data_quality_warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}
                     </ul>
                   </div>`
                : ""
            }
          </div>

          <!-- Lowest Price Summary Box -->
          <div class="mt-4 p-4 rounded-xl bg-slate-800/60 border border-slate-700/60 flex items-center justify-between">
            <div>
              <span class="text-xs text-slate-400 font-medium">Lowest Available Price</span>
              <div class="text-2xl font-black text-white">${lowestPrice}</div>
              <div class="text-xs text-slate-400">Sold by <strong class="text-white">${escapeHtml(bestRetailer)}</strong></div>
            </div>
            <div class="text-right">
              <span class="inline-flex items-center gap-1 px-3 py-1 rounded-md text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Verified Lowest
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Competing Retailer Offers Section -->
      <div class="py-6 border-b border-slate-800">
        <h3 class="text-sm font-bold text-white uppercase tracking-wider mb-3">All Retailer Offers (${offers.length})</h3>
        <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/40">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="border-b border-slate-800 bg-slate-900/80 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                <th class="py-2.5 px-3">Merchant</th>
                <th class="py-2.5 px-3">Offer Price</th>
                <th class="py-2.5 px-3">Availability</th>
                <th class="py-2.5 px-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              ${offerRows || `<tr><td colspan="4" class="py-4 text-center text-xs text-slate-500">No retailer offers found for this product.</td></tr>`}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Specifications Matrix Section -->
      <div class="pt-6">
        <h3 class="text-sm font-bold text-white uppercase tracking-wider mb-3">Technical Specifications</h3>
        <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/40 max-h-60 overflow-y-auto">
          <table class="w-full text-left border-collapse">
            <tbody>
              ${specRows || `<tr><td class="py-4 text-center text-xs text-slate-500">No technical specifications recorded.</td></tr>`}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

/**
 * Render order status badge.
 */
export function renderStatusBadge(status) {
  const norm = (status || "").toUpperCase();
  const styles = {
    COMPLETED: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    CREATED: "bg-sky-500/10 text-sky-400 border-sky-500/20",
    APPROVED: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
    CAPTURE_PENDING: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    FAILED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
    CANCELLED: "bg-slate-500/10 text-slate-400 border-slate-500/20",
    EXPIRED: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
  };
  const activeClass = styles[norm] || "bg-slate-700/20 text-slate-300 border-slate-700";

  return `
    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${activeClass}">
      <span class="w-1.5 h-1.5 rounded-full bg-current"></span>
      ${escapeHtml(norm)}
    </span>
  `;
}

/**
 * Render loading skeleton placeholder for cards.
 */
export function renderSkeletonCard() {
  return `
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col gap-4 animate-pulse">
      <div class="w-full h-44 bg-slate-800/80 rounded-xl"></div>
      <div class="space-y-2">
        <div class="h-3 bg-slate-800 rounded w-1/4"></div>
        <div class="h-4 bg-slate-800 rounded w-3/4"></div>
        <div class="h-3 bg-slate-800/60 rounded w-full"></div>
      </div>
      <div class="mt-auto pt-3 border-t border-slate-800 flex justify-between items-center">
        <div class="h-5 bg-slate-800 rounded w-1/3"></div>
        <div class="h-8 bg-slate-800 rounded w-1/4"></div>
      </div>
    </div>
  `;
}

/**
 * Render empty state card with optional action button.
 */
export function renderEmptyState(title, description, actionText = null, actionId = null) {
  return `
    <div class="flex flex-col items-center justify-center text-center p-12 bg-slate-900/60 border border-slate-800 rounded-2xl max-w-lg mx-auto">
      <div class="w-14 h-14 rounded-2xl bg-slate-800/80 border border-slate-700 flex items-center justify-center text-slate-400 mb-4">
        <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
      </div>
      <h3 class="text-base font-bold text-white mb-1.5">${escapeHtml(title)}</h3>
      <p class="text-xs text-slate-400 max-w-sm mb-6 leading-relaxed">${escapeHtml(description)}</p>
      ${
        actionText && actionId
          ? `<button type="button" id="${actionId}" class="px-4 py-2 text-xs font-semibold rounded-lg bg-burnt-orange hover:bg-burnt-orange/90 text-white transition-colors">
               ${escapeHtml(actionText)}
             </button>`
          : ""
      }
    </div>
  `;
}

/**
 * Render floating toast notifications.
 */
export function showToast(message, type = "info", duration = 4000) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  const colors = {
    success: "bg-emerald-950 border-emerald-500/40 text-emerald-200",
    error: "bg-rose-950 border-rose-500/40 text-rose-200",
    warning: "bg-amber-950 border-amber-500/40 text-amber-200",
    info: "bg-slate-900 border-slate-700 text-slate-200",
  };
  const colorClass = colors[type] || colors.info;

  toast.className = `flex items-center gap-2.5 px-4 py-3 rounded-xl border shadow-xl text-xs font-medium transition-all duration-300 transform translate-y-2 opacity-0 ${colorClass}`;
  toast.innerHTML = `
    <span class="text-sm font-bold">${type === "success" ? "✓" : type === "error" ? "✕" : "ℹ"}</span>
    <span class="flex-1">${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);
  requestAnimationFrame(() => {
    toast.classList.remove("translate-y-2", "opacity-0");
  });

  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-2");
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/**
 * Basic HTML escaping helper.
 */
export function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Lightweight inline markdown formatter (bold, italic, inline code).
 * Text MUST be HTML-escaped before passing into this function.
 */
function formatInlineMarkdown(text) {
  if (!text) return "";
  return text
    .replace(/`([^`\n]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-slate-800 text-amber-300 font-mono text-[11px] sm:text-xs border border-slate-700/60">$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-white">$1</strong>')
    .replace(/__(.+?)__/g, '<strong class="font-semibold text-white">$1</strong>')
    .replace(/\*([^\*\n]+)\*/g, '<em class="italic text-slate-200">$1</em>')
    .replace(/(?:^|\s)_([^_]+)_(?=\s|$|[.,!?:;])/g, (match, p1) => {
      const leadingSpace = match.startsWith(" ") ? " " : "";
      return `${leadingSpace}<em class="italic text-slate-200">${p1}</em>`;
    });
}

/**
 * Lightweight, safe Markdown renderer for assistant messages.
 * Escapes HTML first to strictly prevent arbitrary script/HTML execution,
 * then formats headings (###, ##, #), lists (ordered, unordered),
 * horizontal rules (---), bold, italic, and inline code.
 */
export function renderMarkdown(raw) {
  if (!raw) return "";
  const lines = String(raw).split(/\r?\n/);
  const out = [];
  let inList = null; // "ul" or "ol"

  function closeList() {
    if (inList) {
      out.push(inList === "ul" ? "</ul>" : "</ol>");
      inList = null;
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const trimmed = rawLine.trim();

    if (!trimmed) {
      closeList();
      continue;
    }

    // Horizontal rule: ---, ***, ___
    if (/^(?:---|\*\*\*|___)\s*$/.test(trimmed)) {
      closeList();
      out.push('<hr class="my-3 border-slate-700/80" />');
      continue;
    }

    // Headings: ###, ##, #
    const h3Match = trimmed.match(/^###\s+(.+)$/);
    if (h3Match) {
      closeList();
      const escaped = escapeHtml(h3Match[1]);
      out.push(`<h4 class="text-sm font-bold text-white mt-3 mb-1.5">${formatInlineMarkdown(escaped)}</h4>`);
      continue;
    }

    const h2Match = trimmed.match(/^##\s+(.+)$/);
    if (h2Match) {
      closeList();
      const escaped = escapeHtml(h2Match[1]);
      out.push(`<h3 class="text-base font-bold text-white mt-4 mb-2">${formatInlineMarkdown(escaped)}</h3>`);
      continue;
    }

    const h1Match = trimmed.match(/^#\s+(.+)$/);
    if (h1Match) {
      closeList();
      const escaped = escapeHtml(h1Match[1]);
      out.push(`<h2 class="text-lg font-bold text-white mt-4 mb-2">${formatInlineMarkdown(escaped)}</h2>`);
      continue;
    }

    // Unordered list item: - item, * item, ? item (\u2022)
    const ulMatch = trimmed.match(/^[-*?\u2022]\s+(.+)$/);
    if (ulMatch) {
      if (inList !== "ul") {
        closeList();
        out.push('<ul class="list-disc list-inside space-y-1 my-2 pl-1 text-slate-300">');
        inList = "ul";
      }
      const escaped = escapeHtml(ulMatch[1]);
      out.push(`<li class="leading-relaxed">${formatInlineMarkdown(escaped)}</li>`);
      continue;
    }

    // Ordered list item: 1. item, 2. item
    const olMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (olMatch) {
      if (inList !== "ol") {
        closeList();
        out.push('<ol class="list-decimal list-inside space-y-1 my-2 pl-1 text-slate-300">');
        inList = "ol";
      }
      const escaped = escapeHtml(olMatch[1]);
      out.push(`<li class="leading-relaxed">${formatInlineMarkdown(escaped)}</li>`);
      continue;
    }

    // Normal paragraph
    closeList();
    const escaped = escapeHtml(trimmed);
    out.push(`<p class="mb-2 last:mb-0">${formatInlineMarkdown(escaped)}</p>`);
  }

  closeList();
  return out.join("");
}


/**
 * =========================================================================
 * AI SHOPPING ASSISTANT UI COMPONENTS
 * =========================================================================
 */

/**
 * Welcome screen rendered when the assistant conversation is empty.
 */
export function renderAssistantWelcome() {
  const examplePrompts = [
    "Find a laptop for coding with at least 16GB RAM under $1500",
    "Recommend wireless noise-cancelling headphones for travel under $250",
    "Find Nike running shoes for training under $120",
    "Finde Laufschuhe unter 150 Dollar",
  ];

  return `
    <div id="assistant-welcome-screen" class="py-6 sm:py-10 flex flex-col items-center text-center max-w-2xl mx-auto space-y-6">
      <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-burnt-orange to-amber-600 flex items-center justify-center shadow-xl shadow-burnt-orange/20">
        <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
      </div>

      <div class="space-y-2">
        <h2 class="text-xl sm:text-2xl font-heading font-extrabold text-white">How can I assist your shopping today?</h2>
        <p class="text-xs sm:text-sm text-slate-400 leading-relaxed">
          I extract your criteria, aggregate live offers across retailers via Channel3, assess technical trade-offs with Gemini 3.6 Flash, and verify your spending mandate.
        </p>
      </div>

      <!-- Quick Suggestion Prompt Chips -->
      <div class="w-full space-y-2 pt-2">
        <span class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Try one of these queries:</span>
        <div class="flex flex-wrap justify-center gap-2">
          ${examplePrompts
            .map(
              (prompt) => `
            <button
              type="button"
              class="js-assistant-prompt-chip text-left px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-burnt-orange/60 text-xs text-slate-300 hover:text-white transition-all duration-200"
              data-prompt="${escapeHtml(prompt)}"
            >
              💬 ${escapeHtml(prompt)}
            </button>
          `
            )
            .join("")}
        </div>
      </div>
    </div>
  `;
}

/**
 * User speech bubble.
 */
export function renderAssistantUserMessage(content) {
  return `
    <div class="flex justify-end items-start gap-3">
      <div class="max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-tr-none px-4 py-3 bg-burnt-orange text-white text-xs sm:text-sm leading-relaxed shadow-lg">
        <p class="whitespace-pre-wrap">${escapeHtml(content)}</p>
      </div>
      <div class="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0 text-[11px] font-bold text-slate-300">
        You
      </div>
    </div>
  `;
}

/**
 * Assistant speech bubble with conversational guidance, notices, and recommended products.
 */
export function renderAssistantMessage(data, isComparedList = [], activeMandate = null) {
  const isDegraded = Boolean(data.is_ai_degraded);
  const degradedReason = data.degraded_reason || "";
  const mandateEval = data.mandate_evaluation || null;
  const products = data.products || [];
  const eligibilityList = data.eligibility_details || [];
  const intelligenceList = data.ai_analyses || [];

  // Build maps for fast O(1) lookup
  const eligibilityMap = {};
  for (const item of eligibilityList) {
    if (item && item.product_id) eligibilityMap[item.product_id] = item;
  }

  const intelligenceMap = {};
  for (const item of intelligenceList) {
    if (item && item.product_id) intelligenceMap[item.product_id] = item;
  }

  // Format assistant message text with safe markdown rendering
  const rawMessage = data.assistant_message || "Here are the top options matching your search.";
  const formattedMessage = renderMarkdown(rawMessage);

  return `
    <div class="flex items-start gap-3">
      <div class="w-8 h-8 rounded-full bg-burnt-orange/20 border border-burnt-orange/40 flex items-center justify-center shrink-0 text-burnt-orange text-xs font-bold shadow-md">
        AI
      </div>
      <div class="flex-1 max-w-[95%] sm:max-w-[85%] rounded-2xl rounded-tl-none p-4 sm:p-5 bg-slate-900 border border-slate-800 text-xs sm:text-sm text-slate-200 space-y-4 shadow-xl">
        <!-- AI Degradation / High Traffic Notice -->
        ${
          isDegraded
            ? `
          <div class="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2">
            <span class="text-amber-400 mt-0.5 text-sm">⚠</span>
            <div>
              <span class="font-semibold block">High Demand Grounded Notice</span>
              <span class="text-[11px] text-amber-200/90 leading-relaxed">
                Live Gemini reasoning experienced high traffic. Switched to deterministic rule-based analysis and verified live Channel3 results.
                ${degradedReason ? `(${escapeHtml(degradedReason)})` : ""}
              </span>
            </div>
          </div>
        `
            : ""
        }

        <!-- Spending Mandate Policy Banner -->
        ${
          mandateEval
            ? `
          <div class="p-3 rounded-xl text-xs flex items-start gap-2 ${
            mandateEval.decision === "ALLOWED"
              ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-300"
              : "bg-rose-500/10 border border-rose-500/30 text-rose-300"
          }">
            <span class="mt-0.5">${mandateEval.decision === "ALLOWED" ? "✅" : "⚠️"}</span>
            <div>
              <span class="font-semibold block">Spending Mandate Evaluation: ${escapeHtml(mandateEval.decision)}</span>
              <span class="text-[11px] opacity-90 leading-relaxed">
                ${
                  mandateEval.decision === "ALLOWED"
                    ? "Purchase of top recommended item satisfies your active session spending ceilings."
                    : escapeHtml((mandateEval.reasons || []).join(" ") || "Blocked by active mandate policy restrictions.")
                }
              </span>
            </div>
          </div>
        `
            : ""
        }

        <!-- Conversational Message Body -->
        <div class="text-slate-300 leading-relaxed font-normal">
          ${formattedMessage}
        </div>

        <!-- Recommended Product Cards Grid -->
        ${
          products.length > 0
            ? `
          <div class="pt-2 border-t border-slate-800/80">
            <div class="mb-3 flex items-center justify-between">
              <span class="text-xs font-semibold uppercase tracking-wider text-burnt-orange">
                Recommended Live Products (${products.length})
              </span>
              <span class="text-[11px] text-slate-500">Grounded &amp; Policy Evaluated</span>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              ${products
                .map((product) =>
                  renderAssistantProductCard(
                    product,
                    eligibilityMap[product.id] || null,
                    intelligenceMap[product.id] || null,
                    isComparedList.includes(product.id),
                    activeMandate
                  )
                )
                .join("")}
            </div>
          </div>
        `
            : ""
        }
      </div>
    </div>
  `;
}

/**
 * Compact Product Recommendation Card tailored for the Assistant stream.
 */
export function renderAssistantProductCard(product, eligibility = null, intelligence = null, isCompared = false, activeMandate = null) {
  const offerCurrency = (product.offers?.[0]?.currency || "USD").toUpperCase();
  const lowestPrice = product.lowest_price !== null ? formatPrice(product.lowest_price, offerCurrency) : "Check Offers";
  const bestRetailer = product.lowest_price_retailer || product.offers?.[0]?.retailer_name || "Catalog";
  const offersCount = product.offers ? product.offers.length : 0;
  const isSynthetic = product.is_synthetic !== false;

  // Eligibility Status Pill
  let eligibilityPill = "";
  if (eligibility) {
    if (eligibility.status === "QUALIFIED") {
      eligibilityPill = `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> ✓ Qualified
        </span>
      `;
    } else if (eligibility.status === "CURRENCY_MISMATCH") {
      eligibilityPill = `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30" title="Cross-currency comparison caution">
          <span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span> ⚠ Currency Notice
        </span>
      `;
    } else if (eligibility.status === "UNVERIFIED_SPECS") {
      eligibilityPill = `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
          <span class="w-1.5 h-1.5 rounded-full bg-indigo-400"></span> ℹ Unverified Specs
        </span>
      `;
    } else {
      eligibilityPill = `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
          <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span> ✕ Excluded
        </span>
      `;
    }
  }

  // Eligibility Reasons
  let reasonsHtml = "";
  if (eligibility && eligibility.reasons && eligibility.reasons.length > 0) {
    reasonsHtml = `
      <ul class="space-y-0.5 my-2">
        ${eligibility.reasons
          .slice(0, 2)
          .map(
            (r) => `
          <li class="text-[11px] text-slate-400 flex items-start gap-1 leading-snug">
            <span class="text-slate-600 shrink-0">•</span>
            <span>${escapeHtml(r)}</span>
          </li>
        `
          )
          .join("")}
      </ul>
    `;
  }

  // AI Intelligence highlights
  let aiIntelHtml = "";
  if (intelligence && (intelligence.suitability || (intelligence.strengths && intelligence.strengths.length > 0))) {
    aiIntelHtml = `
      <div class="mt-2.5 p-2 rounded-lg bg-slate-950/80 border border-slate-800/80 space-y-1">
        ${
          intelligence.suitability
            ? `<p class="text-[11px] text-slate-300 leading-snug line-clamp-2"><strong class="text-burnt-orange font-semibold">Suitability:</strong> ${escapeHtml(
                intelligence.suitability
              )}</p>`
            : ""
        }
        ${
          intelligence.strengths && intelligence.strengths.length > 0
            ? `
          <div class="pt-0.5">
            <span class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Strengths:</span>
            <ul class="space-y-0.5 mt-0.5">
              ${intelligence.strengths
                .slice(0, 2)
                .map(
                  (s) => `
                <li class="text-[11px] text-slate-400 flex items-start gap-1 leading-snug">
                  <span class="text-emerald-400 shrink-0">✓</span>
                  <span>${escapeHtml(s)}</span>
                </li>
              `
                )
                .join("")}
            </ul>
          </div>
        `
            : ""
        }
      </div>
    `;
  }

  const compareBtnClass = isCompared
    ? "bg-burnt-orange text-white border-burnt-orange shadow-sm"
    : "bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700 hover:text-white";

  return `
    <div class="flex flex-col bg-slate-950 border border-slate-800/90 rounded-xl overflow-hidden hover:border-slate-700 transition-all shadow-md" data-product-id="${product.id}">
      <!-- Header row with Image and Info -->
      <div class="p-3 flex gap-3 border-b border-slate-800/60">
        <div class="w-16 h-16 bg-slate-900 rounded-lg p-1.5 flex items-center justify-center shrink-0 border border-slate-800/80 overflow-hidden">
          <img
            src="${getSafeImageUrl(product.image_url)}"
            alt="${escapeHtml(product.name)}"
            class="max-h-full max-w-full object-contain"
            loading="lazy"
            ${IMG_FALLBACK_ATTR}
          />
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-1.5 flex-wrap mb-0.5">
            <span class="text-[10px] font-bold uppercase tracking-wider text-burnt-orange">${escapeHtml(product.brand)}</span>
            ${
              isSynthetic
                ? `<span class="px-1.5 py-0.2 rounded text-[9px] font-medium bg-indigo-500/10 text-indigo-400">Demo</span>`
                : `<span class="px-1.5 py-0.2 rounded text-[9px] font-medium bg-emerald-500/10 text-emerald-400">Live</span>`
            }
            ${eligibilityPill}
          </div>
          <h4 class="text-xs font-bold text-white line-clamp-1 leading-snug" title="${escapeHtml(product.name)}">
            ${escapeHtml(product.name)}
          </h4>
          <div class="mt-1 flex items-baseline gap-2">
            <span class="text-sm font-extrabold text-white">${lowestPrice}</span>
            <span class="text-[10px] text-slate-400">via ${escapeHtml(bestRetailer)} (${offersCount} ${offersCount === 1 ? "offer" : "offers"})</span>
          </div>
        </div>
      </div>

      <!-- Card Body: Eligibility reasons and AI suitability -->
      <div class="p-3 flex-1 flex flex-col justify-between">
        <div>
          ${reasonsHtml}
          ${aiIntelHtml}
        </div>

        <!-- Action Buttons -->
        <div class="mt-3 grid grid-cols-2 gap-2 pt-2 border-t border-slate-800/60">
          <button
            type="button"
            class="js-btn-details w-full py-1.5 px-2 text-[11px] font-semibold rounded-lg bg-burnt-orange hover:bg-burnt-orange/90 text-white transition-colors text-center"
            data-id="${product.id}"
          >
            View Offers
          </button>
          <button
            type="button"
            class="js-btn-compare w-full py-1.5 px-2 text-[11px] font-semibold rounded-lg border transition-colors text-center ${compareBtnClass}"
            data-id="${product.id}"
          >
            ${isCompared ? "✓ Compared" : "+ Compare"}
          </button>
        </div>
      </div>
    </div>
  `;
}

/**
 * Animated Loading Indicator for Assistant queries.
 */
export function renderAssistantLoading() {
  return `
    <div id="assistant-loading-indicator" class="flex items-start gap-3">
      <div class="w-8 h-8 rounded-full bg-burnt-orange/20 border border-burnt-orange/40 flex items-center justify-center shrink-0 text-burnt-orange text-xs font-bold shadow-md">
        AI
      </div>
      <div class="px-4 py-3 rounded-2xl rounded-tl-none bg-slate-900 border border-slate-800 text-xs text-slate-300 flex items-center gap-3 shadow-xl">
        <span class="flex gap-1.5">
          <span class="w-2 h-2 rounded-full bg-burnt-orange animate-bounce"></span>
          <span class="w-2 h-2 rounded-full bg-burnt-orange animate-bounce [animation-delay:0.2s]"></span>
          <span class="w-2 h-2 rounded-full bg-burnt-orange animate-bounce [animation-delay:0.4s]"></span>
        </span>
        <span class="font-medium">Extracting criteria &amp; retrieving live offers...</span>
      </div>
    </div>
  `;
}

/**
 * Assistant Error Bubble with Retry option.
 */
export function renderAssistantError(errorMessage, retryQuery = "") {
  return `
    <div class="flex items-start gap-3">
      <div class="w-8 h-8 rounded-full bg-rose-500/20 border border-rose-500/40 flex items-center justify-center shrink-0 text-rose-400 text-xs font-bold shadow-md">
        !
      </div>
      <div class="px-4 py-3 rounded-2xl rounded-tl-none bg-rose-950/40 border border-rose-500/30 text-xs text-rose-300 space-y-2 shadow-xl max-w-[85%]">
        <p class="font-medium">Failed to process assistant query: ${escapeHtml(errorMessage)}</p>
        ${
          retryQuery
            ? `
          <button
            type="button"
            class="js-btn-retry-assistant px-3 py-1.5 rounded-lg bg-rose-900/60 hover:bg-rose-900 border border-rose-700/60 text-xs font-semibold text-rose-200 transition-colors"
            data-query="${escapeHtml(retryQuery)}"
          >
            ↻ Retry Query
          </button>
        `
            : ""
        }
      </div>
    </div>
  `;
}
