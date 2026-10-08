import { createContext, useContext, useState, type ReactNode } from "react";
import { TOKEN_KEY, type AuthResult, type User } from "./api.ts";

// Only the public profile (no password, no hash) and the signed session token, for this browser tab.
const STORAGE_KEY = "cc_user";

interface AuthState {
  user: User | null;
  signIn: (result: AuthResult) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function loadUser(): User | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw && sessionStorage.getItem(TOKEN_KEY) ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(loadUser);

  function signIn({ user: u, token }: AuthResult) {
    const { id, first_name, last_name, email } = u;
    const profile = { id, first_name, last_name, email };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
    sessionStorage.setItem(TOKEN_KEY, token);
    setUser(profile);
  }

  function signOut() {
    sessionStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    setUser(null);
  }

  return <AuthContext.Provider value={{ user, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
