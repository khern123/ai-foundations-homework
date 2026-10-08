import { Link } from "react-router";

export default function NotFoundPage() {
  return (
    <section className="section empty-state">
      <h1>Page not found</h1>
      <p className="muted">That page wandered off campus.</p>
      <Link to="/" className="btn btn-primary">
        Back home
      </Link>
    </section>
  );
}
