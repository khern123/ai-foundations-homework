import { Link } from "react-router";
import { formatPrice } from "../api.ts";
import ProductImage from "./ProductImage.tsx";

/** Anything with these fields can be shown as a card: catalogue products and chat matches. */
export interface CardProduct {
  id: string;
  name: string;
  price_cents: number;
  image_url: string | null;
  description: string;
}

interface Props {
  product: CardProduct;
  /** "grid" for the storefront, "compact" (thumbnail row) for the chat panel. */
  variant?: "grid" | "compact";
  testId?: string;
}

export default function ProductCard({ product, variant = "grid", testId = "product-card" }: Props) {
  return (
    <Link to={`/products/${product.id}`} className={`product-card ${variant}`} data-testid={testId}>
      <ProductImage product={product} />
      <div className="product-card-body">
        <h3>{product.name}</h3>
        <p className="price">{formatPrice(product.price_cents)}</p>
        <p className="product-card-desc">{product.description}</p>
      </div>
    </Link>
  );
}
