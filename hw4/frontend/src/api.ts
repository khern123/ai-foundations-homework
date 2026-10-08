export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
}

export interface Product {
  id: string;
  name: string;
  product_type: string;
  price_cents: number;
  description: string;
  image_path: string | null;
  /** Null when the database has no image path or the file is missing. */
  image_url: string | null;
  colors: string[];
  garment_type: string;
  tags: string[];
}

export class NotFoundError extends Error {}

/** API error: a short safe message, per-field messages (422), the server's error code and request id. */
export class ApiError extends Error {
  status: number;
  fieldErrors: Record<string, string>;
  code: string;
  requestId: string | null;

  constructor(
    status: number,
    message: string,
    fieldErrors: Record<string, string> = {},
    code = status === 0 ? "offline" : "error",
    requestId: string | null = null,
  ) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.code = code;
    this.requestId = requestId;
  }
}

const NETWORK_MESSAGE = "We couldn't reach Campus Customs. Check your connection and try again.";

/** Turn the backend's {detail, code, request_id} error body into an ApiError. */
async function toApiError(res: Response): Promise<ApiError> {
  const data = await res.json().catch(() => ({}));
  const requestId = data.request_id ?? res.headers.get("X-Request-ID");
  // 422 detail is a list of {field, msg}; other errors use a plain string.
  if (Array.isArray(data.detail)) {
    const fieldErrors: Record<string, string> = {};
    let general = "Please fix the highlighted fields.";
    for (const e of data.detail as { field: string | null; msg: string }[]) {
      if (e.field && !(e.field in fieldErrors)) fieldErrors[e.field] = e.msg;
      else if (!e.field) general = e.msg;
    }
    return new ApiError(res.status, general, fieldErrors, data.code, requestId);
  }
  const message = typeof data.detail === "string" ? data.detail : "Something went wrong. Please try again.";
  return new ApiError(res.status, message, {}, data.code, requestId);
}

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { headers: authHeader() });
  } catch {
    throw new ApiError(0, NETWORK_MESSAGE);
  }
  if (res.status === 404) throw new NotFoundError("Not found");
  if (!res.ok) throw await toApiError(res);
  return res.json();
}

// Session token from sign-in (kept in sessionStorage by auth.tsx). Sent only to our own API.
export const TOKEN_KEY = "cc_token";

function authHeader(): Record<string, string> {
  const token = sessionStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, NETWORK_MESSAGE);
  }
  if (!res.ok) throw await toApiError(res);
  return res.json();
}

export interface SearchResult {
  query: string;
  terms: string[];
  category: string | null;
  relaxed: boolean;
  total: number;
  results: Product[];
}

/** Normalized, deduplicated catalogue search (same engine as the chat assistant). */
export const searchProducts = (q: string, type: string | null) =>
  getJson<SearchResult>(
    `/api/products/search?${new URLSearchParams({ q, ...(type ? { type } : {}) }).toString()}`,
  );

export interface User {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
}

export interface RegisterInput {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  confirm_password: string;
}

/** A database-grounded product card returned by POST /api/chat. */
export interface ProductMatch {
  id: string;
  name: string;
  image_path: string | null;
  image_url: string | null;
  price_cents: number;
  price_display: string;
  short_description: string;
}

export interface ChatReply {
  reply: string;
  matches: ProductMatch[];
  total_matches: number;
  view_all_url: string | null;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

/** history is only used for guests; signed-in users' context comes from their saved history. */
export const sendChat = (message: string, history: ChatTurn[], productId: string | null) =>
  postJson<ChatReply>("/api/chat", { message, history, product_id: productId });

export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
  matches: ProductMatch[];
  created_at: string;
}

export const getChatHistory = () =>
  getJson<{ messages: HistoryMessage[] }>("/api/chat/history").then((r) => r.messages);

export interface AuthResult {
  user: User;
  token: string;
}

export const register = (input: RegisterInput) => postJson<AuthResult>("/api/auth/register", input);
export const login = (email: string, password: string) =>
  postJson<AuthResult>("/api/auth/login", { email, password });

export const getHealth = () => getJson<HealthResponse>("/api/health");
export const getProducts = () => getJson<Product[]>("/api/products");
export const getProduct = (id: string) =>
  getJson<Product>(`/api/products/${encodeURIComponent(id)}`);

export function imageSrc(product: { image_url: string | null }): string | null {
  return product.image_url ? `${API_BASE_URL}${product.image_url}` : null;
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
export const formatPrice = (cents: number) => usd.format(cents / 100);

export const TYPE_LABELS: Record<string, string> = {
  "t-shirt": "Tees",
  "long-sleeve": "Long sleeves",
  crewneck: "Crewnecks",
  hoodie: "Hoodies",
  "quarter-zip": "Quarter-zips",
  jacket: "Jackets",
};
