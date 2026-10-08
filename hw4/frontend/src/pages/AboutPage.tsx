import { Link } from "react-router";

export default function AboutPage() {
  return (
    <section className="section narrow">
      <p className="eyebrow">About us</p>
      <h1>
        Made on campus, <span className="accent">for campus.</span>
      </h1>
      <p className="lede">
        Campus Customs started with a simple idea: the gear you wear around New Haven should feel as personal as the
        memories you make here.
      </p>
      <p>
        We bring together residential college crests, graduate school marks, varsity sports designs and family-name
        classics, so a first-year in Davenport, a med student on the late shift and a proud grandparent in the stands
        can all find something that fits their story.
      </p>
      <p>
        Every piece is picked for comfort and staying power: heavyweight fleece for January, breathable tees for move-in
        week, and layers that look sharp at a recruiting dinner or a Saturday tailgate.
      </p>

      <div className="about-grid">
        <div className="perk">
          <h3>Student-first</h3>
          <p>Designed around the way students actually live, study and cheer.</p>
        </div>
        <div className="perk">
          <h3>For the whole family</h3>
          <p>Mom, Dad, Aunt, Grandpa: the Bulldog spirit runs in the family.</p>
        </div>
        <div className="perk">
          <h3>Built to last</h3>
          <p>Quality blanks and clean prints that survive countless laundry days.</p>
        </div>
      </div>

      <Link to="/products" className="btn btn-primary">
        Explore the collection
      </Link>
    </section>
  );
}
