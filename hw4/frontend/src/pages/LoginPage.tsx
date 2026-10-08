import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { ApiError, login } from "../api.ts";
import { useAuth } from "../auth.tsx";
import Field, { EMAIL_RE } from "../components/Field.tsx";

export default function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!EMAIL_RE.test(email.trim())) next.email = "Enter a valid email address.";
    if (!password) next.password = "Enter your password.";
    setErrors(next);
    setFormError("");
    if (Object.keys(next).length) return;

    setBusy(true);
    try {
      signIn(await login(email.trim(), password));
      navigate("/");
    } catch (err) {
      setPassword(""); // never keep a rejected password around
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setFormError(err.message);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="section auth">
      <form className="auth-card" onSubmit={onSubmit} noValidate>
        <p className="eyebrow">Welcome back</p>
        <h1>Log in</h1>

        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}

        <Field label="Email" name="email" error={errors.email}>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={!!errors.email}
            aria-describedby={errors.email ? "email-error" : undefined}
          />
        </Field>
        <Field label="Password" name="password" error={errors.password}>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!errors.password}
            aria-describedby={errors.password ? "password-error" : undefined}
          />
        </Field>

        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Logging in…" : "Log in"}
        </button>

        <p className="muted switch">
          New here? <Link to="/signup">Create account</Link>
        </p>
      </form>
    </section>
  );
}
