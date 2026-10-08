import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { ApiError, searchProducts, TYPE_LABELS, type SearchResult } from "../api.ts";
import ProductCard from "../components/ProductCard.tsx";
import ProductGridSkeleton from "../components/ProductGridSkeleton.tsx";
import { useProducts } from "../useProducts.ts";

const EXAMPLES = ["hoodies", "tees", "1/4 zip", "grey crewneck", "Davenport", "dad"];

type SearchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: SearchResult }
  | { kind: "error"; message: string; requestId: string | null };

export default function ProductsPage() {
  const state = useProducts();
  const [params, setParams] = useSearchParams();
  const activeType = params.get("type");
  const q = params.get("q") ?? "";
  const [draft, setDraft] = useState(q);
  const [search, setSearch] = useState<SearchState>({ kind: "idle" });

  // Keep the box in sync with the URL (back/forward, example links).
  useEffect(() => setDraft(q), [q]);

  // Debounce typing into the URL (?q=), so results are shareable and back/forward works.
  useEffect(() => {
    if (draft === q) return;
    const t = setTimeout(() => update({ q: draft.trim() || null }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  // Run the backend's normalized search whenever the query or category changes.
  useEffect(() => {
    if (!q.trim()) {
      setSearch({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setSearch({ kind: "loading" });
    searchProducts(q, activeType)
      .then((data) => !cancelled && setSearch({ kind: "ok", data }))
      .catch((err) => {
        if (cancelled) return;
        const e = err instanceof ApiError ? err : null;
        setSearch({ kind: "error", message: e?.message ?? "Search failed. Please try again.", requestId: e?.requestId ?? null });
      });
    return () => {
      cancelled = true;
    };
  }, [q, activeType]);

  function update(next: { q?: string | null; type?: string | null }) {
    // Start from the live URL, not a captured copy: a debounced search must not overwrite a category chip
    // clicked meanwhile (React Router's functional updater still sees the render-time params).
    const p = new URLSearchParams(window.location.search);
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    setParams(p, { replace: true });
  }

  const products = state.kind === "ok" ? state.products : [];
  const types = Object.keys(TYPE_LABELS).filter((t) => products.some((p) => p.product_type === t));
  const browsing = !q.trim();
  const shown = browsing
    ? activeType
      ? products.filter((p) => p.product_type === activeType)
      : products
    : search.kind === "ok"
      ? search.data.results
      : [];

  return (
    <section className="section">
      <div className="page-head">
        <p className="eyebrow">The collection</p>
        <h1>Shop Campus Customs</h1>
        <p className="lede">College crests, varsity sports and family-name favorites, ready for your next trip across the quad.</p>
      </div>

      <form className="product-search" role="search" onSubmit={(e) => { e.preventDefault(); update({ q: draft.trim() || null }); }}>
        <label htmlFor="product-search" className="visually-hidden">Search products</label>
        <input
          id="product-search"
          type="search"
          placeholder='Search: "hoodies", "1/4 zip", "grey crewneck", "Davenport"…'
          value={draft}
          maxLength={100}
          onChange={(e) => setDraft(e.target.value)}
          autoComplete="off"
        />
        {draft && (
          <button type="button" className="search-clear" onClick={() => { setDraft(""); update({ q: null }); }}>
            Clear
          </button>
        )}
      </form>

      {state.kind === "ok" && (
        <div className="filters" role="group" aria-label="Filter by style">
          <button className={!activeType ? "chip active" : "chip"} aria-pressed={!activeType} onClick={() => update({ type: null })}>
            All
          </button>
          {types.map((t) => (
            <button
              key={t}
              className={activeType === t ? "chip active" : "chip"}
              aria-pressed={activeType === t}
              onClick={() => update({ type: t })}
            >
              {TYPE_LABELS[t]}
            </button>
          ))}
        </div>
      )}

      <p className="result-status muted" role="status" aria-live="polite" data-testid="result-status">
        {browsing && state.kind === "ok" && `${shown.length} items`}
        {!browsing && search.kind === "loading" && "Searching…"}
        {!browsing && search.kind === "ok" &&
          `${search.data.total} result${search.data.total === 1 ? "" : "s"} for “${q}”` +
            (search.data.relaxed ? " · no exact match, showing closest results" : "")}
      </p>

      {state.kind === "loading" && <ProductGridSkeleton count={8} />}
      {state.kind === "error" && <p className="error">We couldn't load products right now. Please try again shortly.</p>}

      {search.kind === "error" && (
        <div className="empty-state" role="alert">
          <h2>Search isn't working right now</h2>
          <p className="muted">
            {search.message}
            {search.requestId && <span className="ref"> (ref {search.requestId})</span>}
          </p>
        </div>
      )}

      {!browsing && search.kind === "ok" && search.data.total === 0 && (
        <div className="empty-state" data-testid="search-empty">
          <h2>No products match “{q}”</h2>
          <p className="muted">Try one of these:</p>
          <div className="example-chips">
            {EXAMPLES.map((ex) => (
              <button key={ex} className="chip" onClick={() => update({ q: ex })}>
                {ex}
              </button>
            ))}
          </div>
        </div>
      )}

      {state.kind === "ok" && shown.length > 0 && (
        <div className="product-grid">
          {shown.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}
    </section>
  );
}
