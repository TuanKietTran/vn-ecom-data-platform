"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { ChatReply, Deal, Product, Turn } from "@hunt/contracts";

type View = "home" | "hunt" | "discover" | "saved";
type UpcomingDeal = {
  code: string;
  platform: string;
  seller: string | null;
  product_keys: string[];
  starts_at: string;
  expires_at: string;
  discount_vnd: number;
  percent: number;
  cap_vnd: number | null;
  min_spend_vnd: number;
  eligibility: string[];
  checkout_payment_method: string | null;
  cashback_vnd: number;
  evidence_source: string;
  evidence_url: string | null;
  as_of: string;
  synthetic: boolean;
};
type UpcomingResponse = {
  deals: UpcomingDeal[];
  synthetic_included: boolean;
  notice: string;
};
type DealResults = {
  eligible: Deal[];
  conditional: Deal[];
  fewest_conditions: Deal[];
  price_history?: Deal[];
  notice: string;
};
const money = (v: number | null | undefined) =>
  v == null ? "Not provided" : new Intl.NumberFormat("vi-VN").format(v) + " ₫";
async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch("/api/" + path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(data.message || data.detail || "The service is unavailable.");
  return data as T;
}
export function Workspace({ view }: { view: View }) {
  const [upcoming, setUpcoming] = useState<UpcomingResponse | null>(null);
  const [watchlist, setWatchlist] = useState<Deal[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DealResults | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [includeSynthetic, setIncludeSynthetic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Turn[]>([]);
  useEffect(() => {
    let cancelled = false;
    api<UpcomingResponse>("upcoming?limit=20")
      .then((data) => !cancelled && setUpcoming(data))
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : "Upcoming vouchers unavailable."));
    try {
      const prior = JSON.parse(localStorage.getItem("hunt.watchlist.v1") || "[]");
      if (Array.isArray(prior)) setWatchlist(prior.filter((d) => d?.offer?.offer_id).slice(0, 50));
    } catch {
      setError("This device could not read its saved watchlist.");
    }
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    try { localStorage.setItem("hunt.watchlist.v1", JSON.stringify(watchlist)); }
    catch { setError("Device storage is unavailable; watchlist changes may not persist."); }
  }, [watchlist]);
  async function loadUpcoming(optIn = includeSynthetic) {
    setError("");
    try {
      setUpcoming(await api<UpcomingResponse>(`upcoming?limit=20&include_synthetic=${optIn}`));
    } catch (e) { setError(e instanceof Error ? e.message : "Upcoming vouchers unavailable."); }
  }
  async function search(event?: React.FormEvent) {
    event?.preventDefault();
    if (query.trim().length < 2) { setError("Enter at least two characters."); return; }
    setBusy(true); setError("");
    try {
      if (view === "discover") {
        const response = await api<{ products: Product[] }>(`products?query=${encodeURIComponent(query)}&include_synthetic=${includeSynthetic}`);
        setProducts(response.products);
      } else {
        setResults(await api<DealResults>("deals", { query: query.trim(), include_synthetic: includeSynthetic, eligibility: {} }));
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Search failed."); }
    finally { setBusy(false); }
  }
  async function sendChat(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    const history = messages.slice(-20);
    setMessages((prior) => [...prior, { role: "user", content: text }]);
    setDraft(""); setBusy(true); setError("");
    try {
      const response = await api<ChatReply>("chat?mode=data", { message: text, history });
      setMessages((prior) => [...prior, { role: "assistant", content: response.answer }]);
    } catch (e) { setError(e instanceof Error ? e.message : "Chat unavailable."); }
    finally { setBusy(false); }
  }
  function toggle(deal: Deal) {
    setWatchlist((prior) => prior.some((item) => item.offer.offer_id === deal.offer.offer_id)
      ? prior.filter((item) => item.offer.offer_id !== deal.offer.offer_id)
      : [deal, ...prior].slice(0, 50));
  }
  const nav = [["/", "Home"], ["/hunt", "Hunt"], ["/discover", "Discover"], ["/saved", "Saved"]];
  return <div className="app-shell">
    <header className="topbar">
      <Link href="/" className="wordmark" aria-label="hunt home"><span className="mark">h</span><span>hunt</span></Link>
      <nav aria-label="Main navigation">{nav.map(([href, label]) => <Link key={href} href={href} aria-current={(href === "/" ? view === "home" : href.slice(1) === view) ? "page" : undefined}>{label}{label === "Saved" && watchlist.length > 0 ? ` (${watchlist.length})` : ""}</Link>)}</nav>
    </header>
    <main>
      {error && <p className="alert" role="alert">{error}</p>}
      {view === "home" && <>
        <section className="home-intro"><p className="kicker">Good finds, grounded in evidence.</p><h1>Ask. Explore. Hunt.</h1><p>Compare what is actually in the supplied catalog. No invented prices or availability.</p><Link className="button primary" href="/hunt">Start a hunt</Link></section>
        <section className="panel chat-panel" aria-labelledby="chat-title"><div className="panel-head"><div><p className="kicker">CHAT</p><h2 id="chat-title">Ask about your shopping data</h2></div><span className="muted">Evidence-backed data mode</span></div>
          <div className="conversation" aria-live="polite">{messages.length === 0 && <p className="muted">Ask a question. Answers use available platform data, not live model output.</p>}{messages.map((message, index) => <article key={index} className="message"><b>{message.role === "user" ? "You" : "Hunt"}</b><p>{message.content}</p></article>)}{busy && <p role="status">Checking supplied data…</p>}</div>
          <form onSubmit={sendChat} className="chat-form"><label className="sr-only" htmlFor="chat-input">Message</label><input id="chat-input" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ask a question" maxLength={8000} /><button className="button primary" disabled={busy || !draft.trim()}>Send</button></form>
        </section>
        <UpcomingWidget data={upcoming} includeSynthetic={includeSynthetic} onOptIn={(next) => { setIncludeSynthetic(next); void loadUpcoming(next); }} />
      </>}
      {(view === "hunt" || view === "discover") && <section>
        <div className="page-heading"><p className="kicker">{view === "hunt" ? "DEAL SEARCH" : "PRODUCT CATALOG"}</p><h1>{view === "hunt" ? "Find a good deal." : "Discover products."}</h1><p>Only supplied catalog records are shown. Prices and stock are not inferred.</p></div>
        <form className="search-form" onSubmit={search}><label htmlFor="query">Product or model</label><div className="search-line"><input id="query" value={query} onChange={(e) => setQuery(e.target.value)} minLength={2} maxLength={300} placeholder="Product name or model" required /><button className="button primary" disabled={busy}>{busy ? "Searching…" : "Search"}</button></div><label className="opt-in"><input type="checkbox" checked={includeSynthetic} onChange={(e) => setIncludeSynthetic(e.target.checked)} /> Include explicitly labelled synthetic examples</label></form>
        {view === "hunt" && results && <><p className="notice">{results.notice}</p><div className="cards">{[...results.eligible, ...results.conditional].map((deal) => <DealCard key={deal.offer.offer_id} deal={deal} saved={watchlist.some((x) => x.offer.offer_id === deal.offer.offer_id)} onToggle={() => toggle(deal)} />)}</div>{!results.eligible.length && !results.conditional.length && <p className="empty">No matching deal evidence in the catalog.</p>}</>}
        {view === "discover" && <div className="product-list">{products.map((product) => <article className="product-row" key={product.index_id}><div><span className="tag">{product.source_tier}{product.source_tier === "synthetic" ? " · SYNTHETIC" : ""}</span><h2>{product.title}</h2><p>{product.platform} · Captured {new Date(product.captured_at).toLocaleString()}</p></div><strong>{money(product.price_vnd)}</strong>{product.url && <a href={product.url} target="_blank" rel="noreferrer">Source ↗</a>}</article>)}</div>}
      </section>}
      {view === "saved" && <section><div className="page-heading"><p className="kicker">ON THIS DEVICE</p><h1>Your watchlist.</h1><p>Stored on this device only. Hunt does not send notifications.</p></div><div className="cards">{watchlist.map((deal) => <DealCard key={deal.offer.offer_id} deal={deal} saved onToggle={() => toggle(deal)} snapshot />)}</div>{!watchlist.length && <p className="empty">No saved deals on this device.</p>}</section>}
    </main>
    <footer><Link href="/" className="wordmark"><span className="mark">h</span> hunt</Link><p>Voucher evidence and estimates are not checkout guarantees. Cashback is separate from payment due.</p></footer>
  </div>;
}
function UpcomingWidget({ data, includeSynthetic, onOptIn }: { data: UpcomingResponse | null; includeSynthetic: boolean; onOptIn: (enabled: boolean) => void }) {
  return <section className="panel upcoming" aria-labelledby="upcoming-title"><div className="panel-head"><div><p className="kicker">VOUCHER WINDOWS</p><h2 id="upcoming-title">Upcoming deals</h2></div><label className="opt-in"><input type="checkbox" checked={includeSynthetic} onChange={(e) => onOptIn(e.target.checked)} /> Include synthetic data</label></div><p className="notice">{data?.notice || "Windows appear only when present in supplied voucher data. No countdown, price or availability is implied."}</p>{data?.deals.map((deal) => <article className="upcoming-row" key={`${deal.platform}:${deal.code}`}><div className="upcoming-title"><span className="tag">{deal.synthetic ? "SYNTHETIC · DEMO" : deal.evidence_source.toUpperCase()}</span><h3>{deal.code}</h3><p>{deal.platform}{deal.seller ? ` · ${deal.seller}` : ""}</p></div><dl><div><dt>Window</dt><dd>{new Date(deal.starts_at).toLocaleString()} – {new Date(deal.expires_at).toLocaleString()}</dd></div><div><dt>Discount</dt><dd>{deal.percent ? `${deal.percent}%` : money(deal.discount_vnd)}{deal.cap_vnd !== null ? ` · cap ${money(deal.cap_vnd)}` : ""}</dd></div><div><dt>Minimum spend</dt><dd>{money(deal.min_spend_vnd)}</dd></div><div><dt>Checkout payment</dt><dd>{deal.checkout_payment_method || "Not specified"}</dd></div><div><dt>Cashback · separate</dt><dd>{money(deal.cashback_vnd)}</dd></div><div><dt>Eligibility</dt><dd>{deal.eligibility.length ? deal.eligibility.join("; ") : "No additional conditions supplied"}</dd></div><div><dt>Evidence · as of</dt><dd>{deal.evidence_url ? <a href={deal.evidence_url} target="_blank" rel="noreferrer">{deal.evidence_source} ↗</a> : deal.evidence_source} · {new Date(deal.as_of).toLocaleString()}</dd></div></dl></article>)}{data && data.deals.length === 0 && <p className="empty">No upcoming voucher windows are present in the supplied catalog.</p>}</section>;
}
function DealCard({ deal, saved, onToggle, snapshot = false }: { deal: Deal; saved: boolean; onToggle: () => void; snapshot?: boolean }) {
  const offer = deal.offer;
  return <article className="deal-card"><div className="card-top"><span className="tag">{offer.source_tier === "synthetic" ? "SYNTHETIC · DEMO" : offer.source_tier.toUpperCase()}</span><button className="save-button" onClick={onToggle} aria-pressed={saved}>{saved ? "Saved" : "Save"}</button></div><h2>{offer.title}</h2><p>{offer.seller} · {offer.platform}</p><p className="price">{deal.checkout_vnd === null ? "Checkout total unknown" : money(deal.checkout_vnd)}</p><p className="muted">Estimated checkout · confirm at purchase</p>{snapshot && <p className="notice">Saved snapshot. Recheck listing and voucher evidence before purchase.</p>}<details><summary>Evidence and breakdown</summary><dl><div><dt>Item price</dt><dd>{money(offer.price_vnd)}</dd></div>{deal.discounts.map((d) => <div key={d.code}><dt>{d.code} · {d.scope}</dt><dd>−{money(d.discount_vnd)}</dd></div>)}<div><dt>Delivery after vouchers</dt><dd>{money(deal.shipping_after_discount_vnd)}</dd></div><div><dt>Payable estimate</dt><dd>{money(deal.checkout_vnd)}</dd></div><div><dt>Cashback · separate</dt><dd>{money(deal.cashback_vnd)}</dd></div></dl><p>Variant: {offer.product_key}</p><p>Observed: {new Date(offer.observed_at).toLocaleString()} · {offer.source}</p>{offer.url && <a href={offer.url} target="_blank" rel="noreferrer">Listing source ↗</a>}</details>{deal.conditions.length > 0 && <ul>{deal.conditions.map((condition) => <li key={condition}>{condition}</li>)}</ul>}</article>;
}
