import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router";
import { useAuth } from "../auth.tsx";

const LINKS = [
  { to: "/", label: "Home", end: true },
  { to: "/products", label: "Products" },
  { to: "/about", label: "About Us" },
];

export default function Header() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { user, signOut } = useAuth();

  // Close the mobile menu after navigating.
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  function logOut() {
    signOut();
    setOpen(false);
    navigate("/");
  }

  return (
    <header className="site-header">
      <Link to="/" className="brand">
        Campus <span className="accent">Customs</span>
      </Link>

      <button
        className="menu-toggle"
        aria-label="Toggle navigation"
        aria-expanded={open}
        aria-controls="site-nav"
        onClick={() => setOpen((o) => !o)}
      >
        <span />
        <span />
        <span />
      </button>

      <nav id="site-nav" className={`site-nav ${open ? "open" : ""}`} aria-label="Main">
        {LINKS.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end}>
            {l.label}
          </NavLink>
        ))}
        {user ? (
          <>
            <span className="nav-user" data-testid="signed-in-user">
              Hi, {user.first_name}
            </span>
            <button className="nav-logout" onClick={logOut}>
              Log out
            </button>
          </>
        ) : (
          <>
            <NavLink to="/login">Log in</NavLink>
            <NavLink to="/signup" className="nav-cta">
              Create account
            </NavLink>
          </>
        )}
      </nav>
    </header>
  );
}
