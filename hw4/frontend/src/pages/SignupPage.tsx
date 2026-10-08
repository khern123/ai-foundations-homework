import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { ApiError, register, type RegisterInput } from "../api.ts";
import { useAuth } from "../auth.tsx";
import Field, { EMAIL_RE } from "../components/Field.tsx";

const MIN_PASSWORD = 8;

const EMPTY: RegisterInput = { first_name: "", last_name: "", email: "", password: "", confirm_password: "" };

function validate(v: RegisterInput): Record<string, string> {
  const e: Record<string, string> = {};
  if (!v.first_name.trim()) e.first_name = "Enter your first name.";
  if (!v.last_name.trim()) e.last_name = "Enter your last name.";
  if (!EMAIL_RE.test(v.email.trim())) e.email = "Enter a valid email address.";
  if (v.password.length < MIN_PASSWORD) e.password = `Use at least ${MIN_PASSWORD} characters.`;
  if (!v.confirm_password) e.confirm_password = "Confirm your password.";
  else if (v.password !== v.confirm_password) e.confirm_password = "Passwords do not match.";
  return e;
}

export default function SignupPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [values, setValues] = useState<RegisterInput>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (key: keyof RegisterInput) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const next = validate(values);
    setErrors(next);
    setFormError("");
    if (Object.keys(next).length) return;

    setBusy(true);
    try {
      signIn(await register({ ...values, email: values.email.trim() }));
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError) {
        // A server "Passwords do not match." has no field; show it on the confirmation box.
        const fieldErrors = { ...err.fieldErrors };
        if (err.message === "Passwords do not match.") fieldErrors.confirm_password = err.message;
        if (err.status === 409) fieldErrors.email = err.message;
        setErrors(fieldErrors);
        setFormError(err.status === 409 ? "" : err.message);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  const input = (key: keyof RegisterInput, type: string, autoComplete: string) => (
    <input
      id={key}
      name={key}
      type={type}
      autoComplete={autoComplete}
      value={values[key]}
      onChange={set(key)}
      aria-invalid={!!errors[key]}
      aria-describedby={errors[key] ? `${key}-error` : undefined}
    />
  );

  return (
    <section className="section auth">
      <form className="auth-card" onSubmit={onSubmit} noValidate>
        <p className="eyebrow">Join Campus Customs</p>
        <h1>Create account</h1>

        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}

        <div className="field-row">
          <Field label="First name" name="first_name" error={errors.first_name}>
            {input("first_name", "text", "given-name")}
          </Field>
          <Field label="Last name" name="last_name" error={errors.last_name}>
            {input("last_name", "text", "family-name")}
          </Field>
        </div>
        <Field label="Email" name="email" error={errors.email}>
          {input("email", "email", "email")}
        </Field>
        <Field label="Password" name="password" error={errors.password}>
          {input("password", "password", "new-password")}
        </Field>
        <Field label="Confirm password" name="confirm_password" error={errors.confirm_password}>
          {input("confirm_password", "password", "new-password")}
        </Field>
        <p className="hint muted">At least {MIN_PASSWORD} characters.</p>

        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Creating account…" : "Create account"}
        </button>

        <p className="muted switch">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </form>
    </section>
  );
}
