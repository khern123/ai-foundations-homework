import { Link } from "react-router";
import ProductCard from "../components/ProductCard.tsx";
import ProductGridSkeleton from "../components/ProductGridSkeleton.tsx";
import { useProducts } from "../useProducts.ts";

const FEATURED_IDS = [
  "2025-yale-vs-harvard-t-shirt",
  "champion-reverse-weave-hoodie-1",
  "davenport-college-crewneck",
  "benjamin-franklin-1-4-zip",
];

const PERKS = [
  { title: "Every corner of campus", text: "Residential colleges, grad schools, varsity teams and family favorites, all in one place." },
  { title: "Made to be worn", text: "Heavyweight fleece, soft tri-blends and layers that hold up from first-year move-in to reunion weekend." },
  { title: "Gifts that land", text: "Mom, Dad, Grandpa and the cousin who visits every fall: there's a piece with their name on it." },
];

export default function HomePage() {
  const state = useProducts();
  const featured =
    state.kind === "ok"
      ? FEATURED_IDS.map((id) => state.products.find((p) => p.id === id)).filter((p) => p !== undefined)
      : [];

  return (
    <>
      <section className="hero">
        <p className="eyebrow">New Haven, CT · Est. by students</p>
        <h1>
          Wear your campus. <span className="accent">Own your story.</span>
        </h1>
        <p className="lede">
          Campus Customs is the go-to closet for Bulldogs and the people who cheer them on: crewnecks, hoodies, tees
          and quarter-zips built for game days, all-nighters and everything in between.
        </p>
        <div className="hero-actions">
          <Link to="/products" className="btn btn-primary">
            Shop the collection
          </Link>
          <Link to="/about" className="btn btn-ghost">
            Our story
          </Link>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Fan favorites</h2>
          <Link to="/products" className="text-link">
            View all →
          </Link>
        </div>
        {state.kind === "loading" && <ProductGridSkeleton count={4} />}
        {state.kind === "error" && <p className="error">We couldn't load products right now. Please try again shortly.</p>}
        {state.kind === "ok" && (
          <div className="product-grid">
            {featured.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        )}
      </section>

      <section className="section perks">
        {PERKS.map((perk) => (
          <div key={perk.title} className="perk">
            <h3>{perk.title}</h3>
            <p>{perk.text}</p>
          </div>
        ))}
      </section>
    </>
  );
}
