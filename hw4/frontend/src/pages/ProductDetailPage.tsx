import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { formatPrice, getProduct, NotFoundError, TYPE_LABELS, type Product } from "../api.ts";
import ProductImage from "../components/ProductImage.tsx";

type State =
  | { kind: "loading" }
  | { kind: "ok"; product: Product }
  | { kind: "missing" }
  | { kind: "error" };

export default function ProductDetailPage() {
  const { productId = "" } = useParams();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    setState({ kind: "loading" });
    getProduct(productId)
      .then((product) => setState({ kind: "ok", product }))
      .catch((err) => setState({ kind: err instanceof NotFoundError ? "missing" : "error" }));
  }, [productId]);

  return (
    <section className="section">
      <Link to="/products" className="text-link back-link">
        ← Back to all products
      </Link>

      {state.kind === "loading" && <p className="muted">Loading…</p>}
      {state.kind === "error" && <p className="error">We couldn't load this item right now. Please try again shortly.</p>}
      {state.kind === "missing" && (
        <div className="empty-state">
          <h1>We couldn't find that item</h1>
          <p className="muted">It may have sold out or moved. Take a look at the full collection instead.</p>
          <Link to="/products" className="btn btn-primary">
            Browse products
          </Link>
        </div>
      )}

      {state.kind === "ok" && <ProductDetail product={state.product} />}
    </section>
  );
}

function ProductDetail({ product }: { product: Product }) {
  return (
    <article className="detail">
      <div className="detail-media">
        <ProductImage product={product} className="detail-img" />
      </div>

      <div className="detail-info">
        <p className="eyebrow">{TYPE_LABELS[product.product_type] ?? product.product_type}</p>
        <h1>{product.name}</h1>
        <p className="price detail-price">{formatPrice(product.price_cents)}</p>
        <p className="detail-desc">{product.description}</p>

        {product.colors.length > 0 && (
          <div className="detail-block">
            <h2>Colors</h2>
            <ul className="tag-list">
              {product.colors.map((c) => (
                <li key={c} className="tag">
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="detail-block">
          <h2>Style</h2>
          <p className="detail-style">{product.garment_type}</p>
        </div>

        {product.tags.length > 0 && (
          <div className="detail-block">
            <h2>Tags</h2>
            <ul className="tag-list">
              {product.tags.map((t) => (
                <li key={t} className="tag">
                  {t}
                </li>
              ))}
            </ul>
          </div>
        )}

        <button className="btn btn-primary" disabled title="Checkout is coming soon">
          Add to bag · coming soon
        </button>
      </div>
    </article>
  );
}
