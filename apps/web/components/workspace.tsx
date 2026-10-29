"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type {
  ChatReply,
  ChatStatus,
  Deal,
  DealResults,
  Product,
  Turn,
} from "@shoplens/contracts";

type View = "hunt" | "discover" | "chat" | "saved";
const currency = (value: number | null) =>
  value === null
    ? "Not yet known"
    : new Intl.NumberFormat("vi-VN").format(value) + " ₫";
async function request<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const r = await fetch("/api/" + path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  let data;
  try {
    data = await r.json();
  } catch {
    throw new Error("The service returned an unreadable response.");
  }
  if (!r.ok)
    throw new Error(
      typeof data.message === "string"
        ? data.message
        : typeof data.detail === "string"
          ? data.detail
          : "The request could not be completed.",
    );
  return data;
}
function Arrow() {
  return (
    <svg
      className="arrow-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      aria-hidden="true"
    >
      <path d="M5 19 19 5M5 5h14v14" />
    </svg>
  );
}
function Spark() {
  return (
    <svg
      className="spark-icon"
      viewBox="0 0 32 32"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="m14 0 4 0 1 10 8-6 3 4-8 7 10 0v4l-10 1 6 8-4 3-7-9-1 10h-4l-1-10-8 6-3-4 9-7L0 16v-4l10-1-6-8 4-3 7 9Z" />
    </svg>
  );
}
function Heart({ filled = false }: { filled?: boolean }) {
  return (
    <svg
      className="heart-icon"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
    >
      <path d="M12 21 3.5 12.7C-2 7.1 5 0 12 7c7-7 14 .1 8.5 5.7Z" />
    </svg>
  );
}
function Headphones() {
  return (
    <svg className="headphones" viewBox="0 0 300 310" aria-hidden="true">
      <path
        d="M61 175V131C61 17 239 17 239 131V175"
        fill="none"
        stroke="currentColor"
        strokeWidth="28"
      />
      <path
        d="M62 155V130C62 23 238 23 238 130V155"
        fill="none"
        stroke="#f3eedf"
        strokeWidth="5"
      />
      <rect
        x="35"
        y="151"
        width="62"
        height="107"
        rx="28"
        fill="currentColor"
        transform="rotate(-10 65 200)"
      />
      <rect
        x="203"
        y="151"
        width="62"
        height="107"
        rx="28"
        fill="currentColor"
        transform="rotate(10 235 200)"
      />
      <path d="M75 176v60M225 176v60" stroke="#f3eedf" strokeWidth="3" />
      <path d="M127 279h46" stroke="currentColor" strokeWidth="3" />
    </svg>
  );
}
export function Workspace({ view }: { view: View }) {
  const [status, setStatus] = useState<ChatStatus | null>(null),
    [connection, setConnection] = useState("Connecting");
  const [query, setQuery] = useState(""),
    [budget, setBudget] = useState(""),
    [payment, setPayment] = useState(""),
    [memberships, setMemberships] = useState(""),
    [newUser, setNewUser] = useState(""),
    [variant, setVariant] = useState(""),
    [includeDemo, setIncludeDemo] = useState(false),
    [filters, setFilters] = useState(false);
  const [results, setResults] = useState<DealResults | null>(null),
    [group, setGroup] = useState("eligible"),
    [products, setProducts] = useState<Product[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [searched, setSearched] = useState(false);
  const [saved, setSaved] = useState<Deal[]>([]),
    [storageReady, setStorageReady] = useState(false),
    [storageError, setStorageError] = useState("");
  const [messages, setMessages] = useState<Turn[]>([]),
    [draft, setDraft] = useState(""),
    [modelMode, setModelMode] = useState(false);
  const chatEnd = useRef<HTMLDivElement>(null),
    pending = useRef<AbortController | null>(null),
    searchId = useRef(0);
  useEffect(() => {
    const controller = new AbortController();
    request<ChatStatus>("status", undefined, controller.signal)
      .then((data) => {
        setStatus(data);
        setConnection(
          data.data_available ? "Platform connected" : "Data not ready",
        );
      })
      .catch(() => setConnection("Platform offline"));
    return () => controller.abort();
  }, []);
  useEffect(() => {
    try {
      const data = JSON.parse(
        localStorage.getItem("shoplens.saved.v1") || "[]",
      );
      if (Array.isArray(data))
        setSaved(
          data
            .filter(
              (d) => d?.offer?.offer_id && typeof d?.checked_at === "string",
            )
            .slice(0, 50),
        );
    } catch {
      setStorageError("Saved deals could not be restored in this browser.");
    }
    setStorageReady(true);
  }, []);
  useEffect(() => {
    if (storageReady)
      try {
        localStorage.setItem("shoplens.saved.v1", JSON.stringify(saved));
      } catch {
        setStorageError(
          "Browser storage is unavailable. Saved deals will last for this visit only.",
        );
      }
  }, [saved, storageReady]);
  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);
  useEffect(
    () => () => {
      pending.current?.abort();
    },
    [],
  );
  function toggleSaved(deal: Deal) {
    setSaved((current) =>
      current.some((d) => d.offer.offer_id === deal.offer.offer_id)
        ? current.filter((d) => d.offer.offer_id !== deal.offer.offer_id)
        : [deal, ...current].slice(0, 50),
    );
  }
  async function search(demo = includeDemo, text = query) {
    if (text.trim().length < 2) {
      setError("Give us at least two characters to find your product.");
      return;
    }
    const id = ++searchId.current;
    setBusy(true);
    setError("");
    setSearched(true);
    try {
      if (view === "discover") {
        const data = await request<{ products: Product[] }>(
          "products?" +
            new URLSearchParams({
              query: text,
              include_synthetic: String(demo),
            }),
        );
        if (id === searchId.current) setProducts(data.products);
      } else {
        const data = await request<DealResults>("deals", {
          query: text.trim(),
          target_vnd: budget ? Number(budget) : null,
          product_key: variant.trim() || null,
          include_synthetic: demo,
          eligibility: {
            payment_method: payment.trim() || null,
            memberships: memberships.trim()
              ? memberships.split(",").map((v) => v.trim())
              : null,
            new_user: newUser ? newUser === "yes" : null,
          },
        });
        if (id === searchId.current) {
          setResults(data);
          setGroup(data.eligible.length ? "eligible" : "conditional");
        }
      }
    } catch (e) {
      if (id === searchId.current)
        setError(e instanceof Error ? e.message : "Please try again.");
    } finally {
      if (id === searchId.current) setBusy(false);
    }
  }
  function demo() {
    setIncludeDemo(true);
    setQuery("Sony WH-1000XM5");
    void search(true, "Sony WH-1000XM5");
  }
  async function send() {
    const text = draft.trim();
    if (!text || busy) return;
    const controller = new AbortController();
    pending.current = controller;
    const history = messages
      .slice(-20)
      .map((m) => ({ ...m, content: m.content.slice(0, 8000) }));
    setMessages((m) => [...m, { role: "user", content: text }]);
    setDraft("");
    setBusy(true);
    setError("");
    try {
      const result = await request<ChatReply>(
        "chat?mode=" + (modelMode ? "model" : "data"),
        { message: text, history },
        controller.signal,
      );
      setMessages((m) => [...m, { role: "assistant", content: result.answer }]);
    } catch (e) {
      setError(
        controller.signal.aborted
          ? "Response stopped."
          : e instanceof Error
            ? e.message
            : "Could not send your message.",
      );
    } finally {
      setBusy(false);
      pending.current = null;
    }
  }
  const offers = results?.[group as keyof DealResults];
  const visibleDeals = Array.isArray(offers) ? (offers as Deal[]) : [];
  return (
    <div className="site">
      <header className="masthead">
        <Link href="/" className="brand" aria-label="ShopLens home">
          <span className="brand-mark">
            S
            <span>
              <Spark />
            </span>
          </span>
          <span>
            SHOP
            <br />
            LENS<span className="brand-period">.</span>
          </span>
        </Link>
        <nav aria-label="Main navigation">
          {(
            [
              ["hunt", "/", "Deal hunt"],
              ["discover", "/discover", "Discover"],
              ["chat", "/chat", "Ask ShopLens"],
              ["saved", "/saved", "Saved"],
            ] as const
          ).map(([id, url, label]) => (
            <Link
              key={id}
              href={url}
              aria-current={view === id ? "page" : undefined}
            >
              {label}
              {id === "saved" && saved.length > 0 && (
                <span className="count">{saved.length}</span>
              )}
            </Link>
          ))}
        </nav>
        <div className="connection">
          <i className={status?.data_available ? "online" : ""} />
          {connection}
        </div>
      </header>
      {view === "hunt" && (
        <>
          <section className="hero">
            <div className="hero-copy">
              <div className="eyebrow">
                <span className="tiny-star">
                  <Spark />
                </span>{" "}
                YOUR INVITE TO THE DEAL AFTERPARTY
              </div>
              <h1>
                THE DEAL
                <br />
                <em>AFTERPARTY.</em>
              </h1>
              <p>
                The product you came for. The codes you didn’t see coming.
                <br />
                One checkout total. Every condition in the open.
              </p>
              <div className="hero-actions">
                <a className="button ink" href="#hunt">
                  Let’s find your deal{" "}
                  <span>
                    <Arrow />
                  </span>
                </a>
                <button className="text-button" onClick={demo} disabled={busy}>
                  Take the demo for a spin <Arrow />
                </button>
              </div>
              <div className="hero-foot">
                <span>01 / EXACT PRODUCT</span>
                <span>02 / ELIGIBLE CODES</span>
                <span>03 / THE FULL MATH</span>
              </div>
            </div>
            <div className="hero-art" aria-hidden="true">
              <span className="art-orbit orbit-one" />
              <span className="art-orbit orbit-two" />
              <div className="poster-ticket">
                <div className="ticket-top">
                  THE DEAL YOU CAME FOR <span>№ 001</span>
                </div>
                <Headphones />
                <div className="poster-bottom">
                  <b>
                    LESS HYPE.
                    <br />
                    MORE HEADROOM.
                  </b>
                  <span className="barcode" />
                </div>
              </div>
              <div className="lime-sticker">
                YOU’RE
                <br />
                ON THE
                <br />
                <b>LIST.</b>
              </div>
              <span className="art-star">
                <Spark />
              </span>
              <span className="art-caption">
                ILLUSTRATION / NOT A LIVE OFFER
              </span>
            </div>
          </section>
          <div className="ticker">
            <span>NO MYSTERY TOTALS</span>
            <b>
              <Spark />
            </b>
            <span>NO CASHBACK CONFUSION</span>
            <b>
              <Spark />
            </b>
            <span>NO MADE-UP DISCOUNTS</span>
            <b>
              <Spark />
            </b>
            <span>JUST THE FULL PICTURE</span>
          </div>
        </>
      )}
      <main className="main">
        {view !== "chat" && (
          <div className="section-heading">
            <div>
              <span className="eyebrow">
                {view === "hunt"
                  ? "THE MAIN EVENT"
                  : view === "discover"
                    ? "THE PRODUCT FLOOR"
                    : "YOUR SHORTLIST"}
              </span>
              <h2>
                {view === "hunt"
                  ? "Your next good find."
                  : view === "discover"
                    ? "Specific beats endless scrolling."
                    : "Good finds. Kept close."}
              </h2>
            </div>
            <span className="section-caption">
              {view === "saved"
                ? "Saved on this device. Recheck before buying."
                : "Facts first. Confetti second."}
            </span>
          </div>
        )}
        {storageError && (
          <p className="notice" role="status">
            {storageError}
          </p>
        )}
        {(view === "hunt" || view === "discover") && (
          <section id="hunt" className="search-panel">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void search();
              }}
            >
              <div className="search-row">
                <label className="search-input">
                  <span>WHAT ARE WE HUNTING?</span>
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    minLength={2}
                    maxLength={300}
                    placeholder={
                      view === "discover"
                        ? "A product, model, or brand…"
                        : "Sony WH-1000XM5, iPhone 16, your next obsession…"
                    }
                    required
                  />
                </label>
                {view === "hunt" && (
                  <label className="budget-input">
                    <span>YOUR CEILING / VND</span>
                    <input
                      type="number"
                      min="0"
                      step="1"
                      placeholder="6,000,000"
                      value={budget}
                      onChange={(e) => setBudget(e.target.value)}
                    />
                  </label>
                )}
                <button className="button red" disabled={busy}>
                  {busy
                    ? "Searching…"
                    : view === "discover"
                      ? "Search products"
                      : "Find my deal"}{" "}
                  <span>
                    <Arrow />
                  </span>
                </button>
              </div>
              <div className="search-options">
                <label className="check">
                  <input
                    type="checkbox"
                    checked={includeDemo}
                    onChange={(e) => setIncludeDemo(e.target.checked)}
                  />
                  Include clearly labeled synthetic demo data
                </label>
                {view === "hunt" && (
                  <button
                    type="button"
                    className="text-button"
                    aria-expanded={filters}
                    onClick={() => setFilters(!filters)}
                  >
                    Eligibility & exact variant {filters ? "−" : "+"}
                  </button>
                )}
              </div>
              {filters && view === "hunt" && (
                <div className="filter-grid">
                  <label>
                    Payment method
                    <input
                      placeholder="Unknown / e.g. Demo Bank"
                      value={payment}
                      onChange={(e) => setPayment(e.target.value)}
                    />
                  </label>
                  <label>
                    Exact variant key
                    <input
                      placeholder="Model, color, capacity, warranty"
                      value={variant}
                      onChange={(e) => setVariant(e.target.value)}
                    />
                  </label>
                  <label>
                    Memberships
                    <input
                      placeholder="Comma-separated, or leave unknown"
                      value={memberships}
                      onChange={(e) => setMemberships(e.target.value)}
                    />
                  </label>
                  <label>
                    New-user eligibility
                    <select
                      value={newUser}
                      onChange={(e) => setNewUser(e.target.value)}
                    >
                      <option value="">Unknown</option>
                      <option value="yes">Eligible</option>
                      <option value="no">Not eligible</option>
                    </select>
                  </label>
                </div>
              )}
            </form>
          </section>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {view === "hunt" && (
          <>
            {results && (
              <>
                <div className="result-tabs" aria-label="Deal ranking">
                  {[
                    ["eligible", "Lowest eligible"],
                    ["conditional", "Worth checking"],
                    ["fewest_conditions", "Fewer hoops"],
                    ["price_history", "Price history"],
                  ].map(([key, label]) => (
                    <button
                      key={key}
                      className={group === key ? "selected" : ""}
                      onClick={() => setGroup(key)}
                    >
                      {label}{" "}
                      <small>
                        {Array.isArray(results[key as keyof DealResults])
                          ? (results[key as keyof DealResults] as Deal[]).length
                          : 0}
                      </small>
                    </button>
                  ))}
                </div>
                <p className="result-note">{results.notice}</p>
              </>
            )}
            <div className="deal-grid">
              {visibleDeals.map((deal, i) => (
                <DealCard
                  key={deal.offer.offer_id}
                  deal={deal}
                  number={i + 1}
                  saved={saved.some(
                    (s) => s.offer.offer_id === deal.offer.offer_id,
                  )}
                  onSave={() => toggleSaved(deal)}
                />
              ))}
            </div>
            {!busy && visibleDeals.length === 0 && (
              <div className="empty-state">
                <span className="empty-stamp">
                  <Spark />
                </span>
                <h3>
                  {searched
                    ? "No matching tickets. Yet."
                    : "Your best deal starts with a name."}
                </h3>
                <p>
                  {searched
                    ? "Try a specific product or change your eligibility. Live offers need a validated feed."
                    : "Search an exact product to compare checkout estimates, not just sticker prices."}
                </p>
                <button className="text-button" onClick={demo}>
                  Try the synthetic deal demo <Arrow />
                </button>
              </div>
            )}
          </>
        )}
        {view === "discover" && (
          <div className="product-list">
            {products.map((p) => (
              <article key={p.index_id} className="product-row">
                <div className="product-initial">{p.title.slice(0, 1)}</div>
                <div>
                  <span className="eyebrow">
                    {p.platform} / {p.source_tier}
                  </span>
                  <h3>{p.title}</h3>
                  <p>
                    Observed {new Date(p.captured_at).toLocaleString()} ·
                    Variant equivalence unverified
                  </p>
                </div>
                <div className="product-price">
                  <b>{currency(p.price_vnd)}</b>
                  {safeUrl(p.url) && (
                    <a href={p.url} target="_blank" rel="noopener noreferrer">
                      View listing <Arrow />
                    </a>
                  )}
                </div>
              </article>
            ))}
            {!busy && products.length === 0 && (
              <div className="empty-state">
                <h3>
                  {searched
                    ? "Nothing fresh matches that search."
                    : "Skip the rabbit hole."}
                </h3>
                <p>
                  Search the indexed catalog. Results are listing candidates;
                  delivery and vouchers are not included.
                </p>
              </div>
            )}
          </div>
        )}
        {view === "saved" && (
          <>
            <div className="deal-grid">
              {saved.map((deal, i) => (
                <DealCard
                  key={deal.offer.offer_id}
                  deal={deal}
                  number={i + 1}
                  saved
                  onSave={() => toggleSaved(deal)}
                  snapshot
                />
              ))}
            </div>
            {saved.length === 0 && (
              <div className="empty-state">
                <span className="empty-stamp">
                  <Heart />
                </span>
                <h3>Make a little room for a good find.</h3>
                <p>
                  Save a deal from the hunt to keep its price breakdown here. No
                  account required.
                </p>
                <Link className="button ink" href="/">
                  Start a deal hunt <Arrow />
                </Link>
              </div>
            )}
          </>
        )}
        {view === "chat" && (
          <section className="chat-room">
            <div className="chat-heading">
              <div>
                <span className="eyebrow">A SECOND PAIR OF EYES</span>
                <h2>Ask before you add to cart.</h2>
              </div>
              <button
                className="text-button"
                onClick={() => {
                  setMessages([]);
                  setError("");
                }}
                disabled={busy}
              >
                New conversation <Arrow />
              </button>
            </div>
            <p className="result-note">
              {modelMode
                ? "Messages and gold context go to the configured model provider."
                : "Platform data mode. Fixed analytics and indexed products, without an LLM."}{" "}
              Conversations stay in this page session.
            </p>
            <div className="chat-messages" aria-live="polite">
              {messages.length === 0 && (
                <div className="chat-suggestions">
                  {[
                    "Compare GMV yesterday",
                    "Find a cheaper phone",
                    "Help me combine vouchers",
                  ].map((prompt) => (
                    <button key={prompt} onClick={() => setDraft(prompt)}>
                      {prompt}
                      <span>
                        <Arrow />
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {messages.map((message, i) => (
                <article className={"chat-message " + message.role} key={i}>
                  <b>{message.role === "user" ? "YOU" : "SHOPLENS"}</b>
                  <p>{message.content}</p>
                  {message.role === "assistant" &&
                    message.content.includes("Deal hunt") && (
                      <Link href="/">
                        Open Deal hunt <Arrow />
                      </Link>
                    )}
                </article>
              ))}
              {busy && <p role="status">Checking the evidence…</p>}
              <div ref={chatEnd} />
            </div>
            <form
              className="chat-composer"
              onSubmit={(e) => {
                e.preventDefault();
                if (busy) pending.current?.abort();
                else void send();
              }}
            >
              <textarea
                aria-label="Message"
                maxLength={8000}
                placeholder="Ask about your data or your next find…"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (
                    e.key === "Enter" &&
                    !e.shiftKey &&
                    !e.nativeEvent.isComposing
                  ) {
                    e.preventDefault();
                    if (!busy) void send();
                  }
                }}
              />
              <div>
                <label>
                  <input
                    type="checkbox"
                    checked={modelMode}
                    disabled={!status?.model_configured || busy}
                    onChange={(e) => setModelMode(e.target.checked)}
                  />
                  {status?.model_configured
                    ? "Use " + status.model
                    : "Model not connected · Data mode available"}
                </label>
                <button
                  className="button ink"
                  disabled={!busy && !draft.trim()}
                >
                  {busy ? (
                    "Stop"
                  ) : (
                    <>
                      Send <Arrow />
                    </>
                  )}
                </button>
              </div>
            </form>
          </section>
        )}
      </main>
      <footer className="footer">
        <span className="footer-brand">
          SHOPLENS <Spark />
        </span>
        <p>
          Good prices deserve good evidence.
          <br />
          Estimates are not checkout guarantees. Synthetic data is always
          labeled.
        </p>
        <span>MADE FOR THE FIND.</span>
      </footer>
    </div>
  );
}
function safeUrl(value?: string | null) {
  try {
    return Boolean(
      value && ["https:", "http:"].includes(new URL(value).protocol),
    );
  } catch {
    return false;
  }
}
function DealCard({
  deal,
  number,
  saved,
  onSave,
  snapshot = false,
}: {
  deal: Deal;
  number: number;
  saved: boolean;
  onSave: () => void;
  snapshot?: boolean;
}) {
  const offer = deal.offer;
  return (
    <article className="deal-ticket">
      <div className="deal-ticket-top">
        <span>ADMIT ONE GOOD FIND / {String(number).padStart(3, "0")}</span>
        <button
          onClick={onSave}
          aria-label={saved ? "Remove saved deal" : "Save deal"}
          aria-pressed={saved}
        >
          <Heart filled={saved} />
        </button>
      </div>
      <div className="deal-body">
        <div className="deal-tags">
          <span
            className={offer.source_tier === "synthetic" ? "tag demo" : "tag"}
          >
            {offer.source_tier === "synthetic"
              ? "SYNTHETIC DEMO"
              : offer.source_tier.toUpperCase()}
          </span>
          <span className="tag">
            {deal.eligible ? "ELIGIBLE ESTIMATE" : "CONDITIONS APPLY"}
          </span>
        </div>
        <h3>{offer.title}</h3>
        <p className="seller">
          {offer.seller}{" "}
          <span>
            <Arrow />
          </span>{" "}
          {offer.platform}
        </p>
        <div className="deal-price">
          <small>ESTIMATED CHECKOUT</small>
          <strong>{currency(deal.checkout_vnd)}</strong>
        </div>
        {deal.within_target !== null && (
          <span
            className={
              "target-note" + (deal.within_target ? "" : " over-target")
            }
          >
            {deal.within_target ? "Within your target" : "Above your target"}
          </span>
        )}
        {snapshot && (
          <p className="warning">
            Saved snapshot · Recheck the current listing and voucher
            availability.
          </p>
        )}
        <details>
          <summary>
            Show me the math <span>+</span>
          </summary>
          <dl>
            <div>
              <dt>Item price</dt>
              <dd>{currency(offer.price_vnd)}</dd>
            </div>
            {deal.discounts.map((d) => (
              <div key={d.code}>
                <dt>
                  {d.code} · {d.scope}
                </dt>
                <dd>−{currency(d.discount_vnd)}</dd>
              </div>
            ))}
            <div>
              <dt>Delivery after vouchers</dt>
              <dd>{currency(deal.shipping_after_discount_vnd)}</dd>
            </div>
            <div className="total">
              <dt>Payable estimate</dt>
              <dd>{currency(deal.checkout_vnd)}</dd>
            </div>
            <div>
              <dt>Future cashback · separate</dt>
              <dd>{currency(deal.cashback_vnd)}</dd>
            </div>
          </dl>
          <p className="fine-print">
            Variant: {offer.product_key}
            <br />
            Observed: {new Date(offer.observed_at).toLocaleString()}
            <br />
            Source: {offer.source}
          </p>
          <p className="fine-print">
            {deal.lowest_observed_item_price_vnd !== null
              ? `Prior item-price low: ${currency(deal.lowest_observed_item_price_vnd)} across ${deal.price_history_days} observed dates. Gaps may exist; before vouchers.`
              : "No prior item-price history. A recent-low claim cannot be verified."}
          </p>
        </details>
        {deal.conditions.length > 0 && (
          <ul className="conditions">
            {deal.conditions.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        )}
      </div>
      <div className="deal-tear" />
      <div className="deal-ticket-bottom">
        <span>
          {deal.voucher_codes.length
            ? deal.voucher_codes.length +
              " CODE" +
              (deal.voucher_codes.length === 1 ? "" : "S") +
              " IN THE MIX"
            : "NO VOUCHER REQUIRED"}
        </span>
        {safeUrl(offer.url) ? (
          <a href={offer.url!} target="_blank" rel="noopener noreferrer">
            Check listing <Arrow />
          </a>
        ) : (
          <span className="fine-print">
            {offer.source_tier === "synthetic"
              ? "DEMO / NO LIVE LISTING"
              : "NO LISTING LINK"}
          </span>
        )}
      </div>
    </article>
  );
}
