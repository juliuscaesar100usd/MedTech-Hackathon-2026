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
  { value: '93.9%', label: 'Авто-нормализация', sub: 'цель ≥ 70%' },
  { value: '5', label: 'Форматы + OCR', sub: 'PDF · scan · DOCX · XLSX · XLS' },
  { value: '4', label: 'Каскад сопоставления', sub: 'точное → эмбеддинги' },
  { value: '∞', label: 'История цен', sub: 'каждая загрузка версионируется' },
];

const PIPELINE = ['Определение', 'Парсинг', 'Нормализация', 'Валидация', 'Версионирование', 'Сохранение'];

const CASCADE = [
  { n: 1, name: 'Точное', method: 'Сравнение нормализованных строк', when: 'Одинаковые названия' },
  { n: 2, name: 'Синонимы', method: 'Словарь синонимов каталога', when: '"ОАК" → "Общий анализ крови"' },
  { n: 3, name: 'Нечёткое', method: 'RapidFuzz token-set ratio', when: 'Опечатки, перестановка слов' },
  { n: 4, name: 'Эмбеддинги', method: 'multilingual-e5 (cosine)', when: 'Семантическое сопоставление ru / kz' },
];

const FEATURES = [
  { icon: IconInbox, title: 'Приём и парсинг', body: 'ZIP-архивы через интерфейс или CLI, авто-определение формата, фоновая очередь обработки; оригиналы и сырой текст не удаляются.' },
  { icon: IconScan, title: 'Любой формат', body: 'Текстовый PDF (таблицы), сканированный PDF через Tesseract OCR (rus+kaz+eng), все листы XLSX/XLS, DOCX с принятием отслеживаемых изменений.' },
  { icon: IconBrain, title: 'Нормализация', body: 'Точное → синонимы → нечёткое → эмбеддинги, настраиваемый порог уверенности и очередь несопоставленных для ручного сопоставления оператором.' },
  { icon: IconCheck, title: 'Валидация', body: 'Цена > 0, нерезидент ≥ резидент, нет будущих дат; скачок цены > 50% помечается как аномалия для проверки.' },
  { icon: IconSearch, title: 'Поиск и сравнение', body: 'Найдите услугу, посмотрите все клиники-партнёры с ценами для резидентов / нерезидентов, перейдите на страницу партнёра с контактами и датами.' },
  { icon: IconShield, title: 'Аккаунты и администрирование', body: 'Каталог открыт для всех; административная панель доступна только администраторам (HMAC-токены, pbkdf2-пароли). 401 без токена, 403 для неадминистраторов.' },
];

const TECH = ['Python 3.11+', 'FastAPI', 'React 18', 'TypeScript', 'SQLite → PostgreSQL', 'SQLAlchemy', 'Tesseract OCR', 'RapidFuzz', 'multilingual-e5', 'pdfplumber', 'PyMuPDF', 'Vite'];

export function LandingPage() {
  return (
    <main className="lp">
      {/* ---- Hero ---- */}
      <section className="lp-hero">
        <div className="lp-container lp-hero-inner">
          <span className="lp-eyebrow">MedTech Hackathon 2026 · Кейс 2</span>
          <h1 className="lp-h1">
            Прайс-лист любой клиники —<br />
            <span className="lp-h1-accent">единая база услуг и цен с поиском</span>
          </h1>
          <p className="lp-lead">
            Клиники-партнёры присылают прайсы в виде текстовых PDF, сканов, многолистовых Excel
            и Word с отслеживанием изменений. MedArchive принимает архив, распознаёт каждый файл,
            нормализует названия услуг в единый каталог, проверяет и версионирует цены, и
            предоставляет всё это через поиск, ИИ-ассистент и дашборд оператора.
          </p>
          <div className="lp-cta-row">
            <Link to="/search" className="lp-btn lp-btn-primary">
              Поиск в каталоге <IconArrow className="lp-btn-icon" />
            </Link>
            <Link to="/assistant" className="lp-btn lp-btn-ghost">
              <IconChat className="lp-btn-icon" /> Попробовать ИИ-ассистент
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
        <p className="lp-kicker">Как это работает</p>
        <h2 id="lp-pipeline-h" className="lp-h2">ZIP на входе — чистый каталог на выходе</h2>
        <p className="lp-section-lead">
          Каждый загруженный архив распаковывается, каждый файл ставится в очередь и проходит
          единый конвейер — добавьте новый формат с новым парсером, без изменения ядра.
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
          <p className="lp-kicker"><IconLayers className="lp-kicker-icon" /> Каскад сопоставления</p>
          <h2 id="lp-cascade-h" className="lp-h2">Дёшево → дорого, останавливается на первом уверенном совпадении</h2>
          <p className="lp-section-lead">
            Порог авто-сопоставления настраивается (по умолчанию <code>0.85</code>); серая зона
            попадает в очередь <code>needs_review</code>, остальное — в <code>unmatched</code>.
            Эмбеддинги загружаются офлайн — без них сопоставитель корректно деградирует до
            лексической цепочки, и демо всё равно работает.
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
        <p className="lp-kicker">Возможности</p>
        <h2 id="lp-features-h" className="lp-h2">Всё необходимое для бэк-офиса</h2>
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
            <p className="lp-kicker"><IconChat className="lp-kicker-icon" /> ИИ-ассистент</p>
            <h2 id="lp-assistant-h" className="lp-h2">Спросите на обычном языке — получите ранжированные результаты</h2>
            <p className="lp-section-lead">
              Ассистент извлекает структуру запроса в свободной форме — услугу, бюджет, город,
              резидент / нерезидент, сортировку, «топ N» — фильтрует каталог и возвращает лучшие
              предложения клиник с прозрачным объяснением того, как вас понял. Распознаёт{' '}
              <strong>ru / kz / en</strong>, работает офлайн на правилах по умолчанию и опционально
              подключается к Claude.
            </p>
            <Link to="/assistant" className="lp-btn lp-btn-primary">
              Открыть ассистент <IconArrow className="lp-btn-icon" />
            </Link>
          </div>
          <ul className="lp-prompt-list" aria-label="Примеры запросов">
            <li>"анализ крови в Алматы дешевле 5000 ₸ для нерезидента"</li>
            <li>"самое дешёвое УЗИ"</li>
            <li>"консультация терапевта не дороже 8000"</li>
            <li>"cheapest MRI brain under 50k in Astana"</li>
          </ul>
        </div>
      </section>

      {/* ---- Tech ---- */}
      <section className="lp-section lp-container" aria-labelledby="lp-tech-h">
        <p className="lp-kicker">Технологии</p>
        <h2 id="lp-tech-h" className="lp-h2">Надёжно, проверено, заменяемо</h2>
        <ul className="lp-tech">
          {TECH.map((t) => (
            <li key={t} className="lp-tech-chip">{t}</li>
          ))}
        </ul>
      </section>

      {/* ---- Final CTA ---- */}
      <section className="lp-cta-band">
        <div className="lp-container lp-cta-band-inner">
          <h2 className="lp-h2 lp-cta-band-h">Посмотрите на реальных прайс-листах</h2>
          <p className="lp-section-lead">
            Поищите в начальном каталоге, спросите ассистента или войдите в дашборд оператора.
          </p>
          <div className="lp-cta-row lp-cta-row-center">
            <Link to="/search" className="lp-btn lp-btn-primary">Поиск в каталоге <IconArrow className="lp-btn-icon" /></Link>
            <Link to="/login" className="lp-btn lp-btn-ghost">Вход для оператора</Link>
          </div>
        </div>
      </section>
    </main>
  );
}
