import { useState } from "react";
import { imageSrc } from "../api.ts";

interface Props {
  product: { name: string; image_url: string | null };
  className?: string;
}

/** Product photo with a styled fallback when the image is missing or fails to load. */
export default function ProductImage({ product, className = "" }: Props) {
  const src = imageSrc(product);
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div
        className={`product-img img-fallback ${className}`}
        role="img"
        aria-label={`${product.name} (photo coming soon)`}
        data-testid="img-fallback"
      >
        <span className="fallback-mark">CC</span>
        <span className="fallback-text">Photo coming soon</span>
      </div>
    );
  }

  return (
    <img
      className={`product-img ${className}`}
      src={src}
      alt={product.name}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
