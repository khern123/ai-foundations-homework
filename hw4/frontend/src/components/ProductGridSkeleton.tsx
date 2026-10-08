/** Placeholder cards shown while products load (announced once to screen readers). */
export default function ProductGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div className="product-grid" role="status" aria-label="Loading products">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="product-card skeleton" aria-hidden="true">
          <div className="skeleton-img" />
          <div className="product-card-body">
            <div className="skeleton-line w-70" />
            <div className="skeleton-line w-30" />
            <div className="skeleton-line" />
          </div>
        </div>
      ))}
    </div>
  );
}
