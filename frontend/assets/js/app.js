/**
 * BUYWISE AI — Application Orchestrator & Client-Side Navigation
 * Coordinates view transitions, API calls, event delegation, and reactive UI state.
 */

import {
  CONFIG,
  getSessionId,
  getSessionIdentifier,
  resetSession,
  formatPrice,
  formatDate,
  getCompareList,
  toggleCompareItem,
  clearCompareList,
} from "./config.js";

import { api, APIError } from "./api.js";

import {
  renderProductCard,
  renderProductDetailModal,
  renderStatusBadge,
  renderSkeletonCard,
  renderEmptyState,
  showToast,
  PLACEHOLDER_IMAGE,
  getSafeImageUrl,
  IMG_FALLBACK_ATTR,
  escapeHtml,
} from "./components.js";

// Global In-Memory State
const state = {
  currentRoute: "home",
  activeMandate: null,
  exploreProducts: [],
  exploreFilters: {
    q: "",
    category: "All",
    brand: "",
    min_price: "",
    max_price: "",
    source: "All",
    page: 1,
    page_size: 12,
  },
  exploreTotalPages: 1,
  selectedProductForModal: null,
};

/**
 * Initialize Application on DOM Ready
 */
document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  initHealthProbe();
  initSessionBadge();
  initModalListeners();
  initComparisonTray();

  // Router listener
  window.addEventListener("hashchange", handleRouteChange);
  handleRouteChange(); // Initial route dispatch
});

/**
 * Client-Side Hash Router
 */
function handleRouteChange() {
  const hash = window.location.hash.replace("#", "") || "home";
  const validRoutes = ["home", "explore", "compare", "mandate", "orders"];
  const route = validRoutes.includes(hash) ? hash : "home";

  state.currentRoute = route;

  // Update navigation visual indicators
  document.querySelectorAll(".nav-link").forEach((link) => {
    const target = link.getAttribute("href").replace("#", "");
    if (target === route) {
      link.classList.add("text-white", "bg-slate-800/90", "border-slate-700");
      link.classList.remove("text-slate-400", "border-transparent");
    } else {
      link.classList.remove("text-white", "bg-slate-800/90", "border-slate-700");
      link.classList.add("text-slate-400", "border-transparent");
    }
  });

  // Switch visible section
  document.querySelectorAll(".page-section").forEach((sec) => {
    sec.classList.add("hidden");
  });
  const activeSec = document.getElementById(`section-${route}`);
  if (activeSec) {
    activeSec.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Load section-specific data
  switch (route) {
    case "home":
      loadHomeSection();
      break;
    case "explore":
      loadExploreSection();
      break;
    case "compare":
      loadCompareSection();
      break;
    case "mandate":
      loadMandateSection();
      break;
    case "orders":
      loadOrdersSection();
      break;
  }

  updateComparisonTray();
}

/**
 * Initialize Desktop & Mobile Navigation
 */
function initNavigation() {
  const mobileToggle = document.getElementById("mobile-menu-toggle");
  const mobileMenu = document.getElementById("mobile-menu");

  if (mobileToggle && mobileMenu) {
    mobileToggle.addEventListener("click", () => {
      mobileMenu.classList.toggle("hidden");
    });

    mobileMenu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        mobileMenu.classList.add("hidden");
      });
    });
  }
}

/**
 * System Health Probe
 */
async function initHealthProbe() {
  const pill = document.getElementById("system-health-pill");
  if (!pill) return;

  try {
    const health = await api.getHealth();
    if (health.status === "healthy" && health.database === "connected") {
      pill.innerHTML = `
        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        <span class="text-xs font-semibold text-emerald-400">System Online</span>
      `;
      pill.className = "flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20";
    } else {
      pill.innerHTML = `
        <span class="w-2 h-2 rounded-full bg-amber-400"></span>
        <span class="text-xs font-semibold text-amber-400">Degraded</span>
      `;
      pill.className = "flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/20";
    }
  } catch {
    pill.innerHTML = `
      <span class="w-2 h-2 rounded-full bg-rose-400"></span>
      <span class="text-xs font-semibold text-rose-400">Offline</span>
    `;
    pill.className = "flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-500/10 border border-rose-500/20";
  }
}

/**
 * Guest Session Header Display
 */
function initSessionBadge() {
  const badge = document.getElementById("session-badge");
  const identifier = getSessionIdentifier();

  if (badge) {
    badge.title = `Guest Session: ${identifier} (Click to reset)`;
    badge.innerHTML = `
      <span class="w-2 h-2 rounded-full bg-slate-400"></span>
      <span class="text-xs text-slate-300 font-mono">${identifier.substring(0, 14)}...</span>
    `;
    badge.addEventListener("click", () => {
      if (confirm("Reset current guest session? This generates a fresh guest identifier.")) {
        const newId = resetSession();
        showToast("Guest session reset successfully.", "info");
        initSessionBadge();
        handleRouteChange();
      }
    });
  }
}

/**
 * Floating Comparison Tray
 */
function initComparisonTray() {
  const clearBtn = document.getElementById("tray-clear-compare");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      clearCompareList();
      updateComparisonTray();
      // Re-render explore cards if in explore view
      if (state.currentRoute === "explore") {
        renderExploreGrid();
      }
      showToast("Comparison list cleared.", "info");
    });
  }
}

function updateComparisonTray() {
  const tray = document.getElementById("comparison-floating-tray");
  const countBadge = document.getElementById("tray-compare-count");
  if (!tray || !countBadge) return;

  const list = getCompareList();
  if (list.length > 0) {
    countBadge.textContent = list.length;
    tray.classList.remove("translate-y-24", "opacity-0");
  } else {
    tray.classList.add("translate-y-24", "opacity-0");
  }
}

/**
 * Global Modal Event Handlers
 */
function initModalListeners() {
  const modal = document.getElementById("app-modal");
  if (!modal) return;

  // Close when clicking backdrop or close buttons
  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.closest(".js-close-modal")) {
      closeModal();
    }
  });

  // ESC key listener
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.classList.contains("hidden")) {
      closeModal();
    }
  });
}

function openModal(htmlContent) {
  const modal = document.getElementById("app-modal");
  const content = document.getElementById("modal-content");
  if (!modal || !content) return;

  content.innerHTML = htmlContent;
  modal.classList.remove("hidden");
  document.body.classList.add("overflow-hidden");
}

function closeModal() {
  const modal = document.getElementById("app-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  document.body.classList.remove("overflow-hidden");
}

// -------------------------------------------------------------------------
// SECTION: HOME
// -------------------------------------------------------------------------

let homeInitialized = false;

function loadHomeSection() {
  if (homeInitialized) return;
  homeInitialized = true;

  // Search input & button
  const searchInput = document.getElementById("home-search-input");
  const searchBtn = document.getElementById("home-search-btn");

  const executeSearch = () => {
    const q = (searchInput?.value || "").trim();
    if (q) {
      state.exploreFilters.q = q;
      state.exploreFilters.page = 1;
      window.location.hash = "#explore";
    }
  };

  if (searchBtn) searchBtn.addEventListener("click", executeSearch);
  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") executeSearch();
    });
  }

  // Quick query chips
  document.querySelectorAll(".js-query-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const query = chip.getAttribute("data-query");
      if (query) {
        state.exploreFilters.q = query;
        state.exploreFilters.page = 1;
        window.location.hash = "#explore";
      }
    });
  });

  // Category browse chips
  document.querySelectorAll(".js-category-card").forEach((card) => {
    card.addEventListener("click", () => {
      const cat = card.getAttribute("data-category");
      if (cat) {
        state.exploreFilters.category = cat;
        state.exploreFilters.q = "";
        state.exploreFilters.page = 1;
        window.location.hash = "#explore";
      }
    });
  });

  // Fetch real featured products from catalog
  fetchHomeFeaturedProducts();
}

async function fetchHomeFeaturedProducts() {
  const container = document.getElementById("home-featured-grid");
  if (!container) return;

  container.innerHTML = Array(4).fill(0).map(() => renderSkeletonCard()).join("");

  try {
    const res = await api.getProducts({ page: 1, page_size: 4 });
    if (res.items && res.items.length > 0) {
      const compareList = getCompareList();
      container.innerHTML = res.items
        .map((p) => renderProductCard(p, compareList.includes(p.id), state.activeMandate))
        .join("");

      bindProductCardEvents(container);
    } else {
      container.innerHTML = `<div class="col-span-full py-8 text-center text-slate-500 text-sm">No featured products available in the catalog.</div>`;
    }
  } catch (err) {
    container.innerHTML = `<div class="col-span-full py-8 text-center text-rose-400 text-sm">Failed to load catalog products: ${err.message}</div>`;
  }
}

// -------------------------------------------------------------------------
// SECTION: EXPLORE
// -------------------------------------------------------------------------

let exploreInitialized = false;

function loadExploreSection() {
  if (!exploreInitialized) {
    exploreInitialized = true;
    initExploreFilters();
  }

  // Synchronize search input if set from Home
  const searchInput = document.getElementById("explore-search-input");
  if (searchInput && state.exploreFilters.q) {
    searchInput.value = state.exploreFilters.q;
  }

  fetchExploreProducts();
}

function initExploreFilters() {
  const searchInput = document.getElementById("explore-search-input");
  const searchBtn = document.getElementById("explore-search-btn");
  const clearBtn = document.getElementById("explore-clear-filters");
  const brandInput = document.getElementById("explore-brand-filter");
  const minPriceInput = document.getElementById("explore-min-price");
  const maxPriceInput = document.getElementById("explore-max-price");
  const sourceSelect = document.getElementById("explore-source-filter");

  // Category filter buttons
  const catContainer = document.getElementById("explore-category-pills");
  if (catContainer) {
    catContainer.innerHTML = CONFIG.CATEGORIES.map(
      (cat) => `
      <button
        type="button"
        class="js-cat-pill px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors border ${
          state.exploreFilters.category === cat
            ? "bg-burnt-orange text-white border-burnt-orange"
            : "bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-white"
        }"
        data-category="${cat}"
      >
        ${cat}
      </button>
    `
    ).join("");

    catContainer.addEventListener("click", (e) => {
      const btn = e.target.closest(".js-cat-pill");
      if (!btn) return;
      const cat = btn.getAttribute("data-category");
      state.exploreFilters.category = cat;
      state.exploreFilters.page = 1;

      // Update pill classes
      catContainer.querySelectorAll(".js-cat-pill").forEach((p) => {
        const isCurrent = p.getAttribute("data-category") === cat;
        p.className = `js-cat-pill px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors border ${
          isCurrent
            ? "bg-burnt-orange text-white border-burnt-orange"
            : "bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-white"
        }`;
      });

      fetchExploreProducts();
    });
  }

  const triggerSearch = () => {
    state.exploreFilters.q = (searchInput?.value || "").trim();
    state.exploreFilters.brand = (brandInput?.value || "").trim();
    state.exploreFilters.min_price = minPriceInput?.value || "";
    state.exploreFilters.max_price = maxPriceInput?.value || "";
    state.exploreFilters.source = sourceSelect?.value || "All";
    state.exploreFilters.page = 1;
    fetchExploreProducts();
  };

  if (searchBtn) searchBtn.addEventListener("click", triggerSearch);
  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") triggerSearch();
    });
  }
  if (brandInput) brandInput.addEventListener("change", triggerSearch);
  if (minPriceInput) minPriceInput.addEventListener("change", triggerSearch);
  if (maxPriceInput) maxPriceInput.addEventListener("change", triggerSearch);
  if (sourceSelect) sourceSelect.addEventListener("change", triggerSearch);

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      state.exploreFilters = {
        q: "",
        category: "All",
        brand: "",
        min_price: "",
        max_price: "",
        source: "All",
        page: 1,
        page_size: 12,
      };
      if (searchInput) searchInput.value = "";
      if (brandInput) brandInput.value = "";
      if (minPriceInput) minPriceInput.value = "";
      if (maxPriceInput) maxPriceInput.value = "";
      if (sourceSelect) sourceSelect.value = "All";

      // Reset category pills
      if (catContainer) {
        catContainer.querySelectorAll(".js-cat-pill").forEach((p) => {
          const isAll = p.getAttribute("data-category") === "All";
          p.className = `js-cat-pill px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors border ${
            isAll
              ? "bg-burnt-orange text-white border-burnt-orange"
              : "bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-white"
          }`;
        });
      }

      fetchExploreProducts();
    });
  }
}

async function fetchExploreProducts() {
  const grid = document.getElementById("explore-product-grid");
  const countLabel = document.getElementById("explore-results-count");
  if (!grid) return;

  grid.innerHTML = Array(6).fill(0).map(() => renderSkeletonCard()).join("");
  if (countLabel) countLabel.textContent = "Loading catalog...";

  try {
    const res = await api.getProducts(state.exploreFilters);
    state.exploreProducts = res.items || [];
    state.exploreTotalPages = res.total_pages || 1;

    if (countLabel) {
      countLabel.textContent = `Showing ${res.items.length} of ${res.total} catalog products (Page ${res.page} of ${res.total_pages})`;
    }

    renderExploreGrid();
    renderPaginationControls(res.page, res.total_pages);
  } catch (err) {
    grid.innerHTML = `
      <div class="col-span-full py-12">
        ${renderEmptyState("Search Error", `Failed to retrieve products from backend: ${err.message}`, "Retry", "btn-retry-explore")}
      </div>
    `;
    const retryBtn = document.getElementById("btn-retry-explore");
    if (retryBtn) retryBtn.addEventListener("click", fetchExploreProducts);
  }
}

function renderExploreGrid() {
  const grid = document.getElementById("explore-product-grid");
  if (!grid) return;

  if (state.exploreProducts.length === 0) {
    grid.innerHTML = `
      <div class="col-span-full py-12">
        ${renderEmptyState(
          "No Products Found",
          "No products match your current keyword or filter criteria. Try broadening your price range or clearing filters.",
          "Clear Filters",
          "btn-empty-clear-filters"
        )}
      </div>
    `;
    const clearBtn = document.getElementById("btn-empty-clear-filters");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        document.getElementById("explore-clear-filters")?.click();
      });
    }
    return;
  }

  const compareList = getCompareList();
  grid.innerHTML = state.exploreProducts
    .map((p) => renderProductCard(p, compareList.includes(p.id), state.activeMandate))
    .join("");

  bindProductCardEvents(grid);
}

function renderPaginationControls(currentPage, totalPages) {
  const container = document.getElementById("explore-pagination");
  if (!container) return;

  if (totalPages <= 1) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = `
    <div class="flex items-center gap-3">
      <button
        type="button"
        id="pag-prev"
        class="px-3.5 py-1.5 rounded-lg border border-slate-700 bg-slate-900 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed"
        ${currentPage <= 1 ? "disabled" : ""}
      >
        ← Previous
      </button>
      <span class="text-xs text-slate-400 font-medium">Page ${currentPage} of ${totalPages}</span>
      <button
        type="button"
        id="pag-next"
        class="px-3.5 py-1.5 rounded-lg border border-slate-700 bg-slate-900 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed"
        ${currentPage >= totalPages ? "disabled" : ""}
      >
        Next →
      </button>
    </div>
  `;

  document.getElementById("pag-prev")?.addEventListener("click", () => {
    if (state.exploreFilters.page > 1) {
      state.exploreFilters.page -= 1;
      fetchExploreProducts();
    }
  });

  document.getElementById("pag-next")?.addEventListener("click", () => {
    if (state.exploreFilters.page < totalPages) {
      state.exploreFilters.page += 1;
      fetchExploreProducts();
    }
  });
}

function bindProductCardEvents(container) {
  // View Details Modal button
  container.querySelectorAll(".js-btn-details").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const productId = btn.getAttribute("data-id");
      if (!productId) return;

      btn.disabled = true;
      btn.textContent = "Loading...";

      try {
        const product = await api.getProductDetail(productId);
        openModal(renderProductDetailModal(product));
      } catch (err) {
        showToast(`Failed to load product details: ${err.message}`, "error");
      } finally {
        btn.disabled = false;
        btn.textContent = "View Offers";
      }
    });
  });

  // Toggle Compare button
  container.querySelectorAll(".js-btn-compare").forEach((btn) => {
    btn.addEventListener("click", () => {
      const productId = btn.getAttribute("data-id");
      if (!productId) return;

      const res = toggleCompareItem(productId);
      if (res.error) {
        showToast(res.error, "warning");
        return;
      }

      if (res.added) {
        btn.textContent = "✓ Compared";
        btn.className = "js-btn-compare w-full py-2 px-3 text-xs font-semibold rounded-lg border transition-colors bg-burnt-orange text-white border-burnt-orange shadow-sm text-center";
        showToast("Product added to comparison.", "success");
      } else {
        btn.textContent = "+ Compare";
        btn.className = "js-btn-compare w-full py-2 px-3 text-xs font-semibold rounded-lg border transition-colors bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700 hover:text-white text-center";
        showToast("Product removed from comparison.", "info");
      }

      updateComparisonTray();
    });
  });
}

// -------------------------------------------------------------------------
// SECTION: COMPARE
// -------------------------------------------------------------------------

async function loadCompareSection() {
  const container = document.getElementById("compare-content-container");
  if (!container) return;

  const compareIds = getCompareList();

  if (compareIds.length === 0) {
    container.innerHTML = renderEmptyState(
      "No Products Selected for Comparison",
      "Select up to 4 products from Explore or Home to view their technical specifications, lowest prices, and retailer offer matrices side by side.",
      "Explore Products",
      "btn-compare-goto-explore"
    );
    document.getElementById("btn-compare-goto-explore")?.addEventListener("click", () => {
      window.location.hash = "#explore";
    });
    return;
  }

  container.innerHTML = `
    <div class="flex items-center justify-center p-12 text-slate-400 text-sm">
      <div class="flex items-center gap-2">
        <svg class="animate-spin h-5 w-5 text-burnt-orange" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
        <span>Retrieving comparison matrix...</span>
      </div>
    </div>
  `;

  try {
    const data = await api.compareProducts(compareIds);
    renderComparisonMatrix(container, data);
  } catch (err) {
    container.innerHTML = renderEmptyState(
      "Comparison Error",
      `Unable to generate comparison matrix: ${err.message}`,
      "Clear Selection",
      "btn-clear-broken-compare"
    );
    document.getElementById("btn-clear-broken-compare")?.addEventListener("click", () => {
      clearCompareList();
      loadCompareSection();
    });
  }
}

function renderComparisonMatrix(container, data) {
  const products = data.products || [];
  if (products.length === 0) {
    container.innerHTML = renderEmptyState(
      "Products Unavailable",
      "The selected products could not be retrieved from the catalog.",
      "Explore Products",
      "btn-compare-goto-explore"
    );
    return;
  }

  // Detect mixed currencies
  const currencies = new Set(products.map((p) => p.currency));
  const hasCurrencyMismatch = currencies.size > 1;

  // Header cards
  const productHeaders = products.map((p) => `
    <th class="py-4 px-4 text-left border-l border-slate-800 bg-slate-900/90 w-64 min-w-[16rem] align-top">
      <div class="relative flex flex-col h-full">
        <button
          type="button"
          class="js-remove-compare absolute -top-1 -right-1 text-slate-500 hover:text-rose-400 p-1"
          data-id="${p.id}"
          title="Remove from comparison"
        >
          ✕
        </button>
        <div class="w-full h-32 bg-slate-950/60 rounded-xl p-3 flex items-center justify-center mb-3 border border-slate-800 overflow-hidden">
          <img src="${getSafeImageUrl(p.image_url)}" alt="${escapeHtml(p.name)}" class="max-h-full object-contain" ${IMG_FALLBACK_ATTR}/>
        </div>
        <div class="text-[10px] font-bold uppercase tracking-wider text-burnt-orange">${escapeHtml(p.brand || "")}</div>
        <div class="text-sm font-bold text-white line-clamp-2 leading-tight mb-2">${escapeHtml(p.name)}</div>
        <div class="mt-auto">
          <div class="text-[11px] text-slate-400">Lowest Price (${escapeHtml(p.best_offer_retailer || "Catalog")})</div>
          <div class="text-lg font-extrabold text-white">${formatPrice(p.lowest_price, p.currency)}</div>
        </div>
      </div>
    </th>
  `).join("");

  // Specification Matrix rows
  const matrix = data.comparison_matrix || {};
  const specRows = Object.entries(matrix).map(([specKey, valMap]) => `
    <tr class="border-b border-slate-800/60 hover:bg-slate-800/30">
      <td class="py-3 px-4 text-xs font-semibold text-slate-400 capitalize bg-slate-950/40 w-48">${specKey.replace(/_/g, " ")}</td>
      ${products.map((p) => {
        const val = valMap[p.id];
        const displayVal = val !== undefined && val !== null ? String(val) : "Not Specified";
        const isMuted = displayVal === "Not Specified";
        return `<td class="py-3 px-4 text-xs ${isMuted ? 'text-slate-500 italic' : 'text-slate-200 font-medium'} border-l border-slate-800">${displayVal}</td>`;
      }).join("")}
    </tr>
  `).join("");

  container.innerHTML = `
    <!-- Top Price Summary & Currency Warnings -->
    ${
      hasCurrencyMismatch
        ? `<div class="mb-6 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 flex items-center gap-3">
             <span class="text-lg">⚠</span>
             <div>
               <strong>Multi-Currency Notice:</strong> The compared products quote prices in different currencies (${Array.from(currencies).join(", ")}). Direct numerical price comparison is withheld to prevent misleading FX valuation without live conversion rates.
             </div>
           </div>`
        : ""
    }

    <!-- Table Container -->
    <div class="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900 shadow-xl">
      <table class="w-full text-left border-collapse">
        <thead>
          <tr class="border-b border-slate-800">
            <th class="py-4 px-4 bg-slate-950/80 text-xs font-bold text-slate-400 uppercase tracking-wider w-48">Feature / Metric</th>
            ${productHeaders}
          </tr>
        </thead>
        <tbody>
          <!-- Availability Row -->
          <tr class="border-b border-slate-800/80 bg-slate-950/20">
            <td class="py-3 px-4 text-xs font-bold text-slate-300">Availability</td>
            ${products.map((p) => `
              <td class="py-3 px-4 text-xs border-l border-slate-800">
                <span class="inline-flex px-2 py-0.5 rounded text-[11px] font-semibold border ${
                  p.overall_availability === "IN_STOCK"
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                    : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                }">
                  ${p.overall_availability.replace(/_/g, " ")}
                </span>
              </td>
            `).join("")}
          </tr>

          <!-- Data Source Row -->
          <tr class="border-b border-slate-800/80 bg-slate-950/20">
            <td class="py-3 px-4 text-xs font-bold text-slate-300">Catalog Source</td>
            ${products.map((p) => `
              <td class="py-3 px-4 text-xs border-l border-slate-800">
                ${
                  p.is_synthetic
                    ? `<span class="text-indigo-400 text-xs font-medium">Synthetic Demo</span>`
                    : `<span class="text-emerald-400 text-xs font-medium">Live Channel3</span>`
                }
              </td>
            `).join("")}
          </tr>

          <!-- Matrix Spec Rows -->
          ${specRows || `<tr><td colspan="${products.length + 1}" class="p-4 text-xs text-slate-500 text-center">No common specifications recorded for matrix comparison.</td></tr>`}
        </tbody>
      </table>
    </div>
  `;

  // Remove buttons
  container.querySelectorAll(".js-remove-compare").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.getAttribute("data-id");
      toggleCompareItem(pid);
      updateComparisonTray();
      loadCompareSection();
      showToast("Removed product from comparison.", "info");
    });
  });
}

// -------------------------------------------------------------------------
// SECTION: SPENDING MANDATE
// -------------------------------------------------------------------------

let mandateInitialized = false;

async function loadMandateSection() {
  const sessionId = getSessionId();

  if (!mandateInitialized) {
    mandateInitialized = true;
    initMandateForms(sessionId);
  }

  fetchMandateDetails(sessionId);
}

async function fetchMandateDetails(sessionId) {
  const overviewCard = document.getElementById("mandate-overview-card");
  if (!overviewCard) return;

  try {
    const mandate = await api.getMandate(sessionId);
    state.activeMandate = mandate;

    if (!mandate) {
      renderNoMandateState(overviewCard);
      return;
    }

    // Fetch order history to compute consumed budget safely (strictly same currency)
    const ordersRes = await api.getOrderHistory(sessionId);
    const completedOrders = (ordersRes.orders || []).filter((o) => o.status === "COMPLETED");
    const mandateCurrency = (mandate.currency || "USD").toUpperCase();
    const sameCurrencyCompletedOrders = completedOrders.filter(
      (o) => (o.currency || "USD").toUpperCase() === mandateCurrency
    );
    const mismatchedOrders = completedOrders.filter(
      (o) => (o.currency || "USD").toUpperCase() !== mandateCurrency
    );
    const spentAmount = sameCurrencyCompletedOrders.reduce((sum, o) => sum + Number(o.total_amount), 0);
    const remainingBudget = Math.max(0, mandate.total_budget - spentAmount);
    const pctUsed = Math.min(100, Math.round((spentAmount / mandate.total_budget) * 100));

    const mismatchedNoticeHtml = mismatchedOrders.length > 0 ? `
      <div class="mb-4 p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs flex items-start gap-2.5">
        <span class="text-base leading-none">⚠</span>
        <div>
          <span class="font-bold">${mismatchedOrders.length} completed order(s) placed in other currencies (${[...new Set(mismatchedOrders.map((o) => o.currency))].join(", ")}).</span>
          <span class="text-slate-300 block mt-0.5">To prevent currency conversion distortion, only orders matching your active mandate currency (${mandateCurrency}) are deducted from this budget ceiling.</span>
        </div>
      </div>
    ` : "";

    overviewCard.innerHTML = `
      ${mismatchedNoticeHtml}
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 p-6 bg-slate-900 border border-slate-800 rounded-2xl mb-8">
        <div class="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80">
          <div class="text-xs text-slate-400 font-medium mb-1">Total Spending Budget</div>
          <div class="text-2xl font-black text-white">${formatPrice(mandate.total_budget, mandate.currency)}</div>
          <div class="text-[11px] text-slate-500 mt-1">Configured Ceiling</div>
        </div>
        
        <div class="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80">
          <div class="text-xs text-slate-400 font-medium mb-1">Consumed / Spent</div>
          <div class="text-2xl font-black text-burnt-orange">${formatPrice(spentAmount, mandate.currency)}</div>
          <div class="text-[11px] text-slate-500 mt-1">${sameCurrencyCompletedOrders.length} completed ${mandateCurrency} purchases</div>
        </div>

        <div class="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80">
          <div class="text-xs text-slate-400 font-medium mb-1">Remaining Available</div>
          <div class="text-2xl font-black text-emerald-400">${formatPrice(remainingBudget, mandate.currency)}</div>
          <div class="text-[11px] text-slate-500 mt-1">${100 - pctUsed}% budget remaining</div>
        </div>

        <div class="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80">
          <div class="text-xs text-slate-400 font-medium mb-1">Item Constraints</div>
          <div class="text-sm font-bold text-white">Max Item: ${formatPrice(mandate.maximum_item_price, mandate.currency)}</div>
          <div class="text-xs text-slate-400 mt-0.5">Max Qty: ${mandate.maximum_quantity} units/order</div>
          <div class="mt-2 inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            ● Policy Active
          </div>
        </div>
      </div>
    `;

    // Populate form fields with current values
    populateMandateForm(mandate);
  } catch (err) {
    overviewCard.innerHTML = `<div class="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">Failed to load mandate: ${err.message}</div>`;
  }
}

function renderNoMandateState(container) {
  container.innerHTML = `
    <div class="p-8 bg-slate-900 border border-slate-800 rounded-2xl text-center mb-8">
      <div class="w-12 h-12 rounded-xl bg-slate-800 flex items-center justify-center text-burnt-orange mx-auto mb-3">
        🛡
      </div>
      <h3 class="text-base font-bold text-white mb-1">No Spending Mandate Configured</h3>
      <p class="text-xs text-slate-400 max-w-md mx-auto mb-4">
        Spending mandates act as deterministic financial guardrails. Configure your maximum budget and item ceilings below to enforce responsible spending.
      </p>
    </div>
  `;
}

function populateMandateForm(mandate) {
  const bInput = document.getElementById("mandate-form-budget");
  const pInput = document.getElementById("mandate-form-item-price");
  const qInput = document.getElementById("mandate-form-quantity");
  const cSelect = document.getElementById("mandate-form-currency");

  if (bInput) bInput.value = mandate.total_budget;
  if (pInput) pInput.value = mandate.maximum_item_price;
  if (qInput) qInput.value = mandate.maximum_quantity;
  if (cSelect) cSelect.value = mandate.currency;
}

function initMandateForms(sessionId) {
  const form = document.getElementById("mandate-config-form");
  const testForm = document.getElementById("mandate-test-form");

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const bVal = parseFloat(document.getElementById("mandate-form-budget").value);
      const pVal = parseFloat(document.getElementById("mandate-form-item-price").value);
      const qVal = parseInt(document.getElementById("mandate-form-quantity").value, 10);
      const cVal = document.getElementById("mandate-form-currency").value;

      if (pVal > bVal) {
        showToast("Maximum item price cannot exceed total budget.", "error");
        return;
      }

      const submitBtn = form.querySelector("button[type='submit']");
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Saving...";
      }

      try {
        const payload = {
          session_identifier: getSessionIdentifier(),
          total_budget: bVal,
          maximum_item_price: pVal,
          maximum_quantity: qVal,
          currency: cVal,
        };

        if (state.activeMandate && state.activeMandate.session_id) {
          await api.updateMandate(state.activeMandate.session_id, payload);
          showToast("Spending mandate updated successfully.", "success");
        } else {
          await api.createMandate(payload);
          showToast("Spending mandate created successfully.", "success");
        }

        fetchMandateDetails(getSessionId());
      } catch (err) {
        showToast(`Failed to save mandate: ${err.message}`, "error");
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Save Mandate Policy";
        }
      }
    });
  }

  // Interactive Policy Verification Sandbox
  if (testForm) {
    testForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const currentSessionId = getSessionId();
      const itemName = document.getElementById("test-item-name").value || "Candidate Purchase";
      const unitPrice = parseFloat(document.getElementById("test-unit-price").value);
      const quantity = parseInt(document.getElementById("test-quantity").value, 10);
      const currency = document.getElementById("test-currency").value;
      const resultBox = document.getElementById("test-policy-result");

      if (!resultBox) return;

      resultBox.innerHTML = `<div class="text-xs text-slate-400 animate-pulse">Evaluating spending rules against backend policy engine...</div>`;

      try {
        const res = await api.validatePurchase(currentSessionId, {
          item_name: itemName,
          unit_price: unitPrice,
          quantity: quantity,
          currency: currency,
        });

        const isAllowed = res.decision === "ALLOWED";
        resultBox.innerHTML = `
          <div class="p-4 rounded-xl border ${
            isAllowed
              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
              : "bg-rose-500/10 border-rose-500/20 text-rose-300"
          }">
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-bold uppercase tracking-wider">${res.decision}: ${isAllowed ? "Policy Compliant" : "Policy Violation"}</span>
              <span class="text-sm font-extrabold">${formatPrice(res.purchase_amount, res.currency)}</span>
            </div>
            <ul class="text-xs space-y-1 list-disc list-inside">
              ${(res.reasons || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("")}
            </ul>
            ${
              res.remaining_budget_after_purchase !== null
                ? `<div class="mt-2 pt-2 border-t border-slate-700/40 text-[11px] text-slate-400">
                     Projected Remaining Budget: <strong class="text-white">${formatPrice(res.remaining_budget_after_purchase, res.currency)}</strong>
                   </div>`
                : ""
            }
          </div>
        `;
      } catch (err) {
        resultBox.innerHTML = `
          <div class="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
            Evaluation failed: ${err.message}. Ensure a mandate is configured first.
          </div>
        `;
      }
    });
  }
}

// -------------------------------------------------------------------------
// SECTION: ORDERS (PURCHASE HISTORY)
// -------------------------------------------------------------------------

async function loadOrdersSection() {
  const container = document.getElementById("orders-content-container");
  if (!container) return;

  const sessionId = getSessionId();

  container.innerHTML = `
    <div class="flex items-center justify-center p-12 text-slate-400 text-sm">
      <div class="flex items-center gap-2">
        <svg class="animate-spin h-5 w-5 text-burnt-orange" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
        <span>Loading purchase history...</span>
      </div>
    </div>
  `;

  try {
    const res = await api.getOrderHistory(sessionId);
    const orders = res.orders || [];

    if (orders.length === 0) {
      container.innerHTML = renderEmptyState(
        "No Orders Found",
        "You have not completed any demonstration purchases in this guest session. Orders placed through the sandbox checkout will appear here with full capture records.",
        "Browse Catalog",
        "btn-orders-goto-explore"
      );
      document.getElementById("btn-orders-goto-explore")?.addEventListener("click", () => {
        window.location.hash = "#explore";
      });
      return;
    }

    const rows = orders.map((o) => `
      <tr class="border-b border-slate-800/60 hover:bg-slate-800/30">
        <td class="py-3.5 px-4 font-mono text-xs font-bold text-white">${escapeHtml(o.internal_order_number)}</td>
        <td class="py-3.5 px-4 text-xs text-slate-400">${formatDate(o.created_at)}</td>
        <td class="py-3.5 px-4 text-xs font-medium text-slate-300">${o.item_count} ${o.item_count === 1 ? 'item' : 'items'}</td>
        <td class="py-3.5 px-4 text-sm font-extrabold text-white">${formatPrice(o.total_amount, o.currency)}</td>
        <td class="py-3.5 px-4">${renderStatusBadge(o.status)}</td>
        <td class="py-3.5 px-4 text-right">
          <button
            type="button"
            class="js-btn-view-receipt px-3 py-1 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
            data-id="${o.id}"
          >
            Receipt
          </button>
        </td>
      </tr>
    `).join("");

    container.innerHTML = `
      <div class="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900 shadow-xl">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="border-b border-slate-800 bg-slate-950/80 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              <th class="py-3 px-4">Order Reference</th>
              <th class="py-3 px-4">Date</th>
              <th class="py-3 px-4">Items</th>
              <th class="py-3 px-4">Total Amount</th>
              <th class="py-3 px-4">Status</th>
              <th class="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      </div>
    `;

    // Bind Receipt View buttons
    container.querySelectorAll(".js-btn-view-receipt").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const orderId = btn.getAttribute("data-id");
        btn.disabled = true;
        btn.textContent = "...";

        try {
          const order = await api.getOrderDetail(orderId, sessionId);
          openModal(renderOrderReceiptModal(order));
        } catch (err) {
          showToast(`Failed to load order receipt: ${err.message}`, "error");
        } finally {
          btn.disabled = false;
          btn.textContent = "Receipt";
        }
      });
    });
  } catch (err) {
    container.innerHTML = renderEmptyState(
      "History Error",
      `Unable to load order history: ${err.message}`,
      "Retry",
      "btn-retry-orders"
    );
    document.getElementById("btn-retry-orders")?.addEventListener("click", loadOrdersSection);
  }
}

function renderOrderReceiptModal(order) {
  const items = order.items || [];
  const captures = order.captures || [];

  const itemRows = items.map((it) => `
    <tr class="border-b border-slate-800/60 last:border-b-0">
      <td class="py-2.5 px-3 text-xs text-white font-medium">
        <div>${escapeHtml(it.product_name)}</div>
        <div class="text-[10px] text-slate-400">${escapeHtml(it.retailer_name || "Catalog")}</div>
      </td>
      <td class="py-2.5 px-3 text-xs text-slate-400">${it.quantity}</td>
      <td class="py-2.5 px-3 text-xs text-slate-400">${formatPrice(it.unit_price, it.currency)}</td>
      <td class="py-2.5 px-3 text-xs font-bold text-white text-right">${formatPrice(it.subtotal, it.currency)}</td>
    </tr>
  `).join("");

  const captureRows = captures.map((c) => `
    <div class="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-300 mb-2">
      <div class="flex items-center justify-between mb-1">
        <span class="font-mono text-emerald-400 font-bold">${escapeHtml(c.paypal_capture_id)}</span>
        <span class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Verified Capture</span>
      </div>
      <div class="text-[11px] text-slate-400">Settled: ${formatPrice(c.captured_amount, c.currency)} • ${formatDate(c.captured_at)}</div>
      ${c.paypal_payer_email_masked ? `<div class="text-[11px] text-slate-500">Payer: ${escapeHtml(c.paypal_payer_email_masked)}</div>` : ""}
    </div>
  `).join("");

  return `
    <div class="p-6">
      <div class="flex items-start justify-between pb-4 border-b border-slate-800 mb-4">
        <div>
          <div class="text-xs text-slate-400 font-medium">Order Receipt</div>
          <div class="text-lg font-mono font-bold text-white">${escapeHtml(order.internal_order_number)}</div>
          <div class="text-xs text-slate-400">${formatDate(order.created_at)}</div>
        </div>
        <div>
          ${renderStatusBadge(order.status)}
        </div>
      </div>

      <!-- Item Snapshot Table -->
      <div class="mb-6">
        <h4 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Purchased Items</h4>
        <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/40">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="border-b border-slate-800 bg-slate-900/80 text-[10px] font-semibold text-slate-400 uppercase">
                <th class="py-2 px-3">Product</th>
                <th class="py-2 px-3">Qty</th>
                <th class="py-2 px-3">Unit Price</th>
                <th class="py-2 px-3 text-right">Subtotal</th>
              </tr>
            </thead>
            <tbody>
              ${itemRows || `<tr><td colspan="4" class="p-3 text-xs text-slate-500 text-center">No item snapshots recorded.</td></tr>`}
            </tbody>
            <tfoot>
              <tr class="border-t border-slate-800 bg-slate-900/40">
                <td colspan="3" class="py-2.5 px-3 text-xs font-bold text-slate-300">Total Settled Amount</td>
                <td class="py-2.5 px-3 text-sm font-black text-white text-right">${formatPrice(order.total_amount, order.currency)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      <!-- Verified Settlement Record -->
      <div>
        <h4 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">PayPal Settlement Proof</h4>
        ${captureRows || `<div class="text-xs text-slate-500 italic p-3 bg-slate-950/40 rounded-lg border border-slate-800">No settled captures associated with this order.</div>`}
      </div>

      <div class="mt-6 pt-4 border-t border-slate-800 text-right">
        <button type="button" class="js-close-modal px-4 py-2 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors">
          Close Receipt
        </button>
      </div>
    </div>
  `;
}
