import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';

/* MedArchive landing page.
   Content sourced from README.md; styled with the app's existing design tokens
   (clinical cyan + health green). SVG icons only (no emoji), WCAG-minded. */

// --- Minimal inline stroke icons (Lucide-style, currentColor) ------------- //
type IconProps = { className?: string };
const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.7,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};
const Svg = ({ children, className }: { children: ReactNode; className?: string }) => (
  <svg viewBox="0 0 24 24" width="24" height="24" className={className} aria-hidden="true" {...stroke}>
    {children}
  </svg>
);
const IconInbox = (p: IconProps) => (
  <Svg {...p}><path d="M3 12h4l2 3h6l2-3h4" /><path d="M5 5h14l2 7v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6z" /></Svg>
);
const IconScan = (p: IconProps) => (
  <Svg {...p}><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2" /><path d="M4 12h16" /></Svg>
);
const IconBrain = (p: IconProps) => (
  <Svg {...p}><path d="M9 3a3 3 0 0 0-3 3 3 3 0 0 0-1 5 3 3 0 0 0 1 5 3 3 0 0 0 3 3 2.5 2.5 0 0 0 3-1V4a2.5 2.5 0 0 0-3-1Z" /><path d="M15 3a3 3 0 0 1 3 3 3 3 0 0 1 1 5 3 3 0 0 1-1 5 3 3 0 0 1-3 3 2.5 2.5 0 0 1-3-1" /></Svg>
);
const IconCheck = (p: IconProps) => (
  <Svg {...p}><path d="M9 12.5l2 2 4-4.5" /><circle cx="12" cy="12" r="9" /></Svg>
);
const IconSearch = (p: IconProps) => (
  <Svg {...p}><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></Svg>
);
const IconChat = (p: IconProps) => (
  <Svg {...p}><path d="M21 12a8 8 0 0 1-11.5 7.2L4 21l1.8-5.5A8 8 0 1 1 21 12Z" /><path d="M8.5 11h7M8.5 14h4" /></Svg>
);
const IconShield = (p: IconProps) => (
  <Svg {...p}><path d="M12 3l7 3v5c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6l7-3Z" /><path d="m9 12 2 2 4-4" /></Svg>
);
const IconLayers = (p: IconProps) => (
  <Svg {...p}><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /></Svg>
);
const IconArrow = (p: IconProps) => (
  <Svg {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Svg>
);

// --- Data (from README) --------------------------------------------------- //
const METRICS = [
  { value: '93.9%', label: 'Auto-normalization', sub: 'target ≥ 70%' },
  { value: '5', label: 'Formats + OCR', sub: 'PDF · scan · DOCX · XLSX · XLS' },
  { value: '4', label: 'Matching cascade', sub: 'exact → embedding' },
  { value: '∞', label: 'Price history', sub: 'every re-upload versioned' },
];

const PIPELINE = ['Detect', 'Parse', 'Normalize', 'Validate', 'Version', 'Persist'];

const CASCADE = [
  { n: 1, name: 'Exact', method: 'Normalized string match', when: 'Identical names' },
  { n: 2, name: 'Synonym', method: 'Catalog synonym dictionary', when: '“ОАК” → “Общий анализ крови”' },
  { n: 3, name: 'Fuzzy', method: 'RapidFuzz token-set ratio', when: 'Typos, reordered words' },
  { n: 4, name: 'Embedding', method: 'multilingual-e5 (cosine)', when: 'Semantic ru / kz match' },
];

const FEATURES = [
  { icon: IconInbox, title: 'Intake & parse', body: 'ZIP archives via UI or CLI, format auto-detection, a queued background worker, and originals + raw text never deleted.' },
  { icon: IconScan, title: 'Every format', body: 'Text PDF (tables), scanned PDF via Tesseract OCR (rus+kaz+eng), all XLSX/XLS sheets, and DOCX with tracked changes accepted.' },
  { icon: IconBrain, title: 'Normalization', body: 'Exact → synonym → fuzzy → embeddings, a configurable confidence threshold, and an unmatched queue for manual operator mapping.' },
  { icon: IconCheck, title: 'Validation', body: 'Price > 0, non-resident ≥ resident, no future dates, and a > 50% price jump flagged as an anomaly for review.' },
  { icon: IconSearch, title: 'Search & compare', body: 'Find a service, see every partner clinic with resident / non-resident prices, plus full partner pages with contacts and dates.' },
  { icon: IconShield, title: 'Accounts & admin', body: 'Public catalog; the admin back office is gated to admins (HMAC tokens, pbkdf2 passwords). 401 without a token, 403 for non-admins.' },
];

const TECH = ['Python 3.11+', 'FastAPI', 'React 18', 'TypeScript', 'SQLite → PostgreSQL', 'SQLAlchemy', 'Tesseract OCR', 'RapidFuzz', 'multilingual-e5', 'pdfplumber', 'PyMuPDF', 'Vite'];

export function LandingPage() {
  return (
    <main className="lp">
      {/* ---- Hero ---- */}
      <section className="lp-hero">
        <div className="lp-container lp-hero-inner">
          <span className="lp-eyebrow">MedTech Hackathon 2026 · Case 2</span>
          <h1 className="lp-h1">
            Any clinic price list,<br />
            <span className="lp-h1-accent">one searchable base of services &amp; prices</span>
          </h1>
          <p className="lp-lead">
            Partner clinics send prices as text PDFs, scans, multi-sheet Excel and tracked-changes Word.
            MedArchive ingests the archive, recognizes every file, normalizes service names to a single
            catalog, validates and versions prices, and serves it all through search, an AI assistant,
            and an operator dashboard.
          </p>
          <div className="lp-cta-row">
            <Link to="/search" className="lp-btn lp-btn-primary">
              Search the catalog <IconArrow className="lp-btn-icon" />
            </Link>
            <Link to="/assistant" className="lp-btn lp-btn-ghost">
              <IconChat className="lp-btn-icon" /> Try the AI assistant
            </Link>
          </div>
          <dl className="lp-stat-strip">
            {METRICS.map((m) => (
              <div key={m.label} className="lp-stat">
                <dt className="lp-stat-value">{m.value}</dt>
                <dd className="lp-stat-label">{m.label}<span className="lp-stat-sub">{m.sub}</span></dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ---- Pipeline ---- */}
      <section className="lp-section lp-container" aria-labelledby="lp-pipeline-h">
        <p className="lp-kicker">How it works</p>
        <h2 id="lp-pipeline-h" className="lp-h2">A ZIP in, a clean catalog out</h2>
        <p className="lp-section-lead">
          Each uploaded archive is unpacked, queued per file, and run through one pipeline — add a new
          format with a new parser, never a core change.
        </p>
        <ol className="lp-pipeline">
          {PIPELINE.map((step, i) => (
            <li key={step} className="lp-pipe-step">
              <span className="lp-pipe-num">{i + 1}</span>
              <span className="lp-pipe-name">{step}</span>
              {i < PIPELINE.length - 1 && <IconArrow className="lp-pipe-arrow" />}
            </li>
          ))}
        </ol>
      </section>

      {/* ---- Matching cascade ---- */}
      <section className="lp-section lp-cascade-wrap" aria-labelledby="lp-cascade-h">
        <div className="lp-container">
          <p className="lp-kicker"><IconLayers className="lp-kicker-icon" /> The matching cascade</p>
          <h2 id="lp-cascade-h" className="lp-h2">Cheap → expensive, stops at the first confident hit</h2>
          <p className="lp-section-lead">
            The auto-match threshold is configurable (default <code>0.85</code>); the gray zone goes to a
            <code>needs_review</code> queue, the rest to <code>unmatched</code>. Embeddings load offline —
            without them the matcher gracefully degrades to the lexical chain and the demo still works.
          </p>
          <ol className="lp-cascade">
            {CASCADE.map((c) => (
              <li key={c.n} className="lp-cascade-step">
                <span className="lp-cascade-num">{c.n}</span>
                <div className="lp-cascade-body">
                  <h3 className="lp-cascade-name">{c.name}</h3>
                  <p className="lp-cascade-method">{c.method}</p>
                  <p className="lp-cascade-when">{c.when}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ---- Capabilities ---- */}
      <section className="lp-section lp-container" aria-labelledby="lp-features-h">
        <p className="lp-kicker">Capabilities</p>
        <h2 id="lp-features-h" className="lp-h2">Everything the back office needs</h2>
        <div className="lp-grid">
          {FEATURES.map((f) => (
            <article key={f.title} className="lp-card">
              <span className="lp-card-icon"><f.icon /></span>
              <h3 className="lp-card-title">{f.title}</h3>
              <p className="lp-card-body">{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ---- Assistant highlight ---- */}
      <section className="lp-section lp-container" aria-labelledby="lp-assistant-h">
        <div className="lp-assistant">
          <div className="lp-assistant-text">
            <p className="lp-kicker"><IconChat className="lp-kicker-icon" /> AI assistant</p>
            <h2 id="lp-assistant-h" className="lp-h2">Ask in plain language, get ranked results</h2>
            <p className="lp-section-lead">
              The assistant extracts the structure of a free-text request — service, budget, city,
              resident / non-resident, sorting, “top N” — filters the catalog and returns the best clinic
              offers, with a transparent read-out of how it understood you. Recognizes <strong>ru / kz / en</strong>,
              works offline rule-based by default, and optionally upgrades to Claude.
            </p>
            <Link to="/assistant" className="lp-btn lp-btn-primary">
              Open the assistant <IconArrow className="lp-btn-icon" />
            </Link>
          </div>
          <ul className="lp-prompt-list" aria-label="Example queries">
            <li>“анализ крови в Алматы дешевле 5000 ₸ для нерезидента”</li>
            <li>“самое дешёвое УЗИ”</li>
            <li>“консультация терапевта не дороже 8000”</li>
            <li>“cheapest MRI brain under 50k in Astana”</li>
          </ul>
        </div>
      </section>

      {/* ---- Tech ---- */}
      <section className="lp-section lp-container" aria-labelledby="lp-tech-h">
        <p className="lp-kicker">Built with</p>
        <h2 id="lp-tech-h" className="lp-h2">Boring, proven, swappable</h2>
        <ul className="lp-tech">
          {TECH.map((t) => (
            <li key={t} className="lp-tech-chip">{t}</li>
          ))}
        </ul>
      </section>

      {/* ---- Final CTA ---- */}
      <section className="lp-cta-band">
        <div className="lp-container lp-cta-band-inner">
          <h2 className="lp-h2 lp-cta-band-h">See it on real price lists</h2>
          <p className="lp-section-lead">
            Search the seeded catalog, ask the assistant, or sign in to the operator dashboard.
          </p>
          <div className="lp-cta-row lp-cta-row-center">
            <Link to="/search" className="lp-btn lp-btn-primary">Search the catalog <IconArrow className="lp-btn-icon" /></Link>
            <Link to="/login" className="lp-btn lp-btn-ghost">Operator sign in</Link>
          </div>
        </div>
      </section>
    </main>
  );
}
