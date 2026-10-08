import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router";
import { ApiError, getChatHistory, sendChat, type ChatTurn, type ProductMatch, type User } from "../api.ts";
import { useAuth } from "../auth.tsx";
import ProductCard from "./ProductCard.tsx";

interface Message {
  from: "bot" | "user";
  text: string;
  matches?: ProductMatch[];
  totalMatches?: number;
  viewAllUrl?: string | null;
  error?: boolean;
  /** For error bubbles: the message that failed, so it can be retried. */
  retryText?: string;
  requestId?: string | null;
  greeting?: boolean;
}

const MAX_CHARS = 500;
const COUNTER_FROM = 400; // show "430 / 500" once the message gets long
const HISTORY_TURNS = 8; // must match the backend's MAX_HISTORY_TURNS
const OFFLINE = "You're offline. Check your connection, then tap Retry.";

const GENERAL_SUGGESTIONS = ["What hoodies do you have?", "Gift ideas for my dad", "Tees under $40"];
const PRODUCT_SUGGESTIONS = ["What colors does this come in?", "Is this in stock in a medium?", "How much is this?"];

function greeting(user: User | null): Message {
  const hi = user ? `Hi ${user.first_name}!` : "Hi!";
  return {
    from: "bot",
    greeting: true,
    text: `${hi} I'm the Campus Customs assistant. Ask me about styles, colleges, prices or gift ideas.`,
  };
}

/** Guests only: earlier exchanges in this tab (no greeting, no error bubbles) sent as context. */
function toHistory(messages: Message[]): ChatTurn[] {
  return messages
    .filter((m) => !m.greeting && !m.error)
    .slice(-HISTORY_TURNS)
    .map((m) => ({ role: m.from === "user" ? "user" : "assistant", content: m.text.slice(0, 2000) }));
}

/** "/products/davenport-college-crewneck" -> "davenport-college-crewneck" */
function pageProductId(pathname: string): string | null {
  return /^\/products\/([a-z0-9-]+)\/?$/.exec(pathname)?.[1] ?? null;
}

export default function ChatWidget() {
  const { user, signOut } = useAuth();
  const productId = pageProductId(useLocation().pathname);
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>(() => [greeting(user)]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);

  // Signed in: reload this user's saved conversation. Signed out: clear it from the screen (shared computers).
  useEffect(() => {
    setMessages([greeting(user)]);
    if (!user) return;
    let cancelled = false;
    setHistoryLoading(true);
    getChatHistory()
      .then((history) => {
        if (cancelled) return;
        setMessages([
          greeting(user),
          ...history.map((h): Message => ({
            from: h.role === "user" ? "user" : "bot",
            text: h.content,
            matches: h.matches,
            totalMatches: h.matches.length,
          })),
        ]);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) signOut(); // expired session
        else setMessages([greeting(user), { from: "bot", text: "We couldn't load your earlier messages.", error: true }]);
      })
      .finally(() => !cancelled && setHistoryLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    // Listen on window so Escape works even when focus has left the panel.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const last = list.lastElementChild as HTMLElement | null;
    const lastMsg = messages[messages.length - 1];
    // A reply with product cards can be taller than the panel: show its text first, not the last card.
    if (!pending && last && lastMsg?.from === "bot" && lastMsg.matches?.length) {
      list.scrollTop = last.offsetTop - list.offsetTop - 8;
    } else {
      list.scrollTop = list.scrollHeight;
    }
  }, [messages, pending]);

  function close() {
    setOpen(false);
    launcherRef.current?.focus(); // return focus to where the user was
  }

  async function ask(text: string) {
    if (!text || pending) return;
    const history = user ? [] : toHistory(messages); // signed-in history lives on the server
    setMessages((m) => [...m, { from: "user", text }]);
    setDraft("");

    if (!navigator.onLine) {
      setMessages((m) => [...m, { from: "bot", text: OFFLINE, error: true, retryText: text }]);
      return;
    }
    setPending(true);
    try {
      const res = await sendChat(text, history, productId);
      setMessages((m) => [
        ...m,
        { from: "bot", text: res.reply, matches: res.matches, totalMatches: res.total_matches, viewAllUrl: res.view_all_url },
      ]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        signOut(); // expired or invalid session: fall back to guest
        setMessages([greeting(null), { from: "bot", text: err.message, error: true }]);
        return;
      }
      const e = err instanceof ApiError ? err : null;
      const text422 = e?.fieldErrors.message;
      setMessages((m) => [
        ...m,
        {
          from: "bot",
          text: text422 ?? e?.message ?? "The assistant couldn't answer right now. Please try again.",
          error: true,
          retryText: text422 ? undefined : text, // a validation error won't succeed on retry
          requestId: e?.requestId ?? null,
        },
      ]);
    } finally {
      setPending(false);
      inputRef.current?.focus();
    }
  }

  function retry(index: number) {
    const failed = messages[index];
    if (!failed.retryText) return;
    // Drop the failed question and its error bubble, then ask again.
    setMessages((m) => m.slice(0, index - 1));
    setTimeout(() => ask(failed.retryText!), 0);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    ask(draft.trim());
  }

  const hasAsked = messages.some((m) => m.from === "user");
  const suggestions = productId ? PRODUCT_SUGGESTIONS : hasAsked ? [] : GENERAL_SUGGESTIONS;
  const showSuggestions = !pending && !historyLoading && !draft && suggestions.length > 0;

  return (
    <div className={`chat ${open ? "open" : ""}`}>
      {open && (
        <section id="chat-panel" className="chat-panel" role="dialog" aria-modal="false" aria-label="Campus Customs chat">
          <header className="chat-header">
            <div>
              <strong>Campus Customs</strong>
              <span className="chat-sub" data-testid="chat-context">
                {productId ? "Asking about this product" : user ? "Chat history saved to your account" : "Guest chat · not saved"}
              </span>
            </div>
            <button className="chat-close" aria-label="Close chat" onClick={close}>
              ×
            </button>
          </header>

          <div
            className="chat-messages"
            ref={listRef}
            role="log"
            aria-live="polite"
            aria-relevant="additions"
            aria-label="Conversation"
          >
            {messages.map((m, i) => (
              <div key={i} className={`chat-msg ${m.from} ${m.error ? "error" : ""}`} data-testid={`chat-${m.from}`}>
                <span className="visually-hidden">{m.from === "user" ? "You:" : "Assistant:"} </span>
                <p>{m.text}</p>
                {m.error && (m.retryText || m.requestId) && (
                  <div className="chat-error-actions">
                    {m.retryText && (
                      <button className="chat-retry" onClick={() => retry(i)} disabled={pending}>
                        Retry
                      </button>
                    )}
                    {m.requestId && <span className="ref">Ref {m.requestId}</span>}
                  </div>
                )}
                {m.matches && m.matches.length > 0 && (
                  <>
                    <ul className="chat-products">
                      {m.matches.map((p) => (
                        <li key={p.id}>
                          <ProductCard product={{ ...p, description: p.short_description }} variant="compact" testId="chat-product" />
                        </li>
                      ))}
                    </ul>
                    {(m.totalMatches ?? 0) > m.matches.length && (
                      <p className="chat-more">
                        Showing {m.matches.length} of {m.totalMatches}
                        {m.viewAllUrl && (
                          <>
                            {" · "}
                            <Link to={m.viewAllUrl} data-testid="chat-view-all">
                              View all
                            </Link>
                          </>
                        )}
                      </p>
                    )}
                  </>
                )}
              </div>
            ))}
            {historyLoading && (
              <div className="chat-msg bot loading" role="status" data-testid="chat-history-loading">
                Loading your conversation…
              </div>
            )}
            {pending && (
              <div className="chat-msg bot typing" role="status" aria-label="Assistant is typing">
                <span className="visually-hidden">Assistant is typing…</span>
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            )}
          </div>

          {showSuggestions && (
            <div className="chat-suggestions" role="group" aria-label="Suggested questions">
              {suggestions.map((s) => (
                <button key={s} className="chat-suggestion" onClick={() => ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}

          <form className="chat-form" onSubmit={onSubmit}>
            <input
              ref={inputRef}
              value={draft}
              maxLength={MAX_CHARS}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask about styles, colleges, gifts…"
              aria-label="Chat message"
              aria-describedby={draft.length >= COUNTER_FROM ? "chat-counter" : undefined}
            />
            <button type="submit" disabled={!draft.trim() || pending} aria-label="Send message">
              {pending ? "…" : "Send"}
            </button>
          </form>
          {draft.length >= COUNTER_FROM && (
            <p id="chat-counter" className="chat-counter" aria-live="polite">
              {draft.length} / {MAX_CHARS}
            </p>
          )}
        </section>
      )}

      <button
        ref={launcherRef}
        className="chat-launcher"
        aria-label={open ? "Close chat" : "Open chat"}
        aria-expanded={open}
        aria-controls="chat-panel"
        aria-haspopup="dialog"
        onClick={() => (open ? close() : setOpen(true))}
      >
        {open ? "×" : "Chat"}
      </button>
    </div>
  );
}
