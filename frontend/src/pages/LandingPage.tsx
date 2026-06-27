import { Link } from 'react-router-dom';
import {
  Tray,
  Scan,
  Brain,
  SealCheck,
  ShieldCheck,
  StackSimple,
  ArrowRight,
  ChatCircleDots,
  Translate,
  CloudSlash,
  Database,
} from '@phosphor-icons/react';

/* MedArchive landing page.
   Content from README.md; on the app's existing clinical cyan + green tokens.
   Redesign per taste-skill: asymmetric-split hero with a REAL product
   screenshot, 2 eyebrows max, Phosphor icons, showcase capabilities.
   Note: Russian тире (—) is correct, required punctuation here — the
   English em-dash ban does not apply to Russian copy. */

const METRICS = [
  { value: '93.9%', label: 'Авто-нормализация', sub: 'цель ≥ 70%' },
  { value: '5', label: 'Форматов + OCR', sub: 'PDF · скан · DOCX · XLSX · XLS' },
  { value: '4', label: 'Уровня сопоставления', sub: 'точное → эмбеддинги' },
  { value: '∞', label: 'История цен', sub: 'каждая загрузка версионируется' },
];

const CAPS = [
  { icon: Tray, title: 'Приём и парсинг', body: 'ZIP через интерфейс или CLI, авто-определение формата, фоновая очередь; оригиналы и сырой текст не удаляются.' },
  { icon: Scan, title: 'Любой формат', body: 'Текстовый PDF, скан через Tesseract OCR (rus+kaz+eng), все листы XLSX/XLS, DOCX с принятием правок.' },
  { icon: Brain, title: 'Нормализация', body: 'Точное → синонимы → нечёткое → эмбеддинги, настраиваемый порог и очередь несопоставленных для оператора.' },
  { icon: SealCheck, title: 'Валидация', body: 'Цена > 0, нерезидент ≥ резидент, без будущих дат; скачок цены свыше 50 % помечается как аномалия.' },
  { icon: ShieldCheck, title: 'Аккаунты и доступ', body: 'Каталог открыт для всех; админ-панель только для администраторов (HMAC-токены, pbkdf2-пароли).' },
];

const TECH = ['Python 3.11+', 'FastAPI', 'React 18', 'TypeScript', 'SQLite → PostgreSQL', 'SQLAlchemy', 'Tesseract OCR', 'RapidFuzz', 'multilingual-e5', 'pdfplumber', 'PyMuPDF', 'Vite'];

export function LandingPage() {
  return (
    <main className="lp">
      {/* ---- Hero: asymmetric split (text left, real dashboard right) ---- */}
      <section className="lp-hero">
        <div className="lp-container lp-hero-grid">
          <div className="lp-hero-text">
            <span className="lp-eyebrow">MedTech Hackathon 2026 · Кейс 2</span>
            <h1 className="lp-h1">
              Прайс-листы клиник —{' '}
              <span className="lp-h1-accent">единая база услуг и цен</span>
            </h1>
            <p className="lp-lead">
              Клиники-партнёры присылают прайсы в виде текстовых PDF, сканов, многолистовых Excel
              и Word с правками. MedArchive принимает архив, распознаёт каждый файл, нормализует
              названия услуг в единый каталог, проверяет и версионирует цены.
            </p>
            <div className="lp-cta-row">
              <Link to="/search" className="lp-btn lp-btn-primary">
                Поиск в каталоге <ArrowRight size={18} weight="bold" />
              </Link>
              <Link to="/assistant" className="lp-btn lp-btn-ghost">
                <ChatCircleDots size={18} weight="bold" /> Попробовать ассистент
              </Link>
            </div>
            <ul className="lp-trust-row" aria-label="Что важно знать">
              <li className="lp-trust-item"><Database size={18} weight="bold" aria-hidden="true" /> Каталог открыт без регистрации</li>
              <li className="lp-trust-item"><Translate size={18} weight="bold" aria-hidden="true" /> ru · kz · en</li>
              <li className="lp-trust-item"><CloudSlash size={18} weight="bold" aria-hidden="true" /> Работает офлайн</li>
            </ul>
          </div>
          <figure className="lp-hero-media">
            <div className="lp-shot">
              <img src="/shots/dashboard-ru.png" alt="Дашборд оператора MedArchive с метриками качества" loading="eager" width={1360} height={900} />
              <span className="lp-shot-callout">
                <SealCheck size={18} weight="fill" aria-hidden="true" /> <b>93.9%</b> авто-нормализация
              </span>
            </div>
          </figure>
        </div>
      </section>

      {/* ---- Metrics band (moved out of the hero) ---- */}
      <section className="lp-metrics-band">
        <div className="lp-container">
          <dl className="lp-metrics">
            {METRICS.map((m) => (
              <div key={m.label} className="lp-metric">
                <dt className="lp-metric-value">{m.value}</dt>
                <dd className="lp-metric-label">{m.label}<span className="lp-metric-sub">{m.sub}</span></dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ---- Pipeline (no eyebrow) ---- */}
      <section className="lp-section lp-container" aria-labelledby="lp-pipeline-h">
        <h2 id="lp-pipeline-h" className="lp-h2">ZIP на входе, чистый каталог на выходе</h2>
        <p className="lp-section-lead">
          Каждый архив распаковывается, каждый файл ставится в очередь и проходит единый конвейер.
          Новый формат добавляется новым парсером, без изменения ядра.
        </p>
        <figure className="lp-anim lp-anim-wide">
          <img
            src="/assets/pipeline.svg"
            alt="Конвейер: определение → парсинг → нормализация → валидация → версии → хранение"
            loading="lazy"
            width={1160}
            height={220}
          />
        </figure>
      </section>

      {/* ---- Matching cascade (keeps an eyebrow — signature concept) ---- */}
      <section className="lp-section lp-cascade-wrap" aria-labelledby="lp-cascade-h">
        <div className="lp-container">
          <p className="lp-kicker"><StackSimple size={18} weight="bold" /> Каскад сопоставления</p>
          <h2 id="lp-cascade-h" className="lp-h2">Дёшево → дорого, до первого уверенного совпадения</h2>
          <p className="lp-section-lead">
            Порог авто-сопоставления настраивается (по умолчанию <code>0.85</code>); серая зона уходит
            в очередь <code>needs_review</code>, остальное — в <code>unmatched</code>. Эмбеддинги
            работают офлайн; без них сопоставитель деградирует до лексической цепочки, и демо всё равно
            работает.
          </p>
          <figure className="lp-anim">
            <img
              src="/assets/normalization.svg"
              alt="Каскад сопоставления: точное → синонимы → нечёткое → эмбеддинги"
              loading="lazy"
              width={1080}
              height={320}
            />
          </figure>
        </div>
      </section>

      {/* ---- Capabilities: showcase (real search shot) + icon list ---- */}
      <section className="lp-section lp-container" aria-labelledby="lp-caps-h">
        <h2 id="lp-caps-h" className="lp-h2">Всё необходимое для бэк-офиса</h2>
        <div className="lp-showcase">
          <figure className="lp-showcase-media">
            <div className="lp-shot">
              <img src="/shots/search-ru.png" alt="Поиск услуги в каталоге MedArchive" loading="lazy" width={1360} height={900} />
            </div>
            <figcaption className="lp-showcase-cap">
              Найдите услугу — получите все клиники-партнёры с ценами для резидентов и нерезидентов.
            </figcaption>
          </figure>
          <ul className="lp-cap-list">
            {CAPS.map((c) => (
              <li key={c.title} className="lp-cap-row">
                <span className="lp-cap-icon"><c.icon size={26} weight="duotone" /></span>
                <div>
                  <h3 className="lp-cap-title">{c.title}</h3>
                  <p className="lp-cap-body">{c.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ---- Assistant (no eyebrow) ---- */}
      <section className="lp-section lp-container" aria-labelledby="lp-assistant-h">
        <div className="lp-assistant">
          <div className="lp-assistant-text">
            <h2 id="lp-assistant-h" className="lp-h2">Спросите обычным языком</h2>
            <p className="lp-section-lead">
              Ассистент извлекает из свободного запроса услугу, бюджет, город, резидент / нерезидент,
              сортировку и «топ N», фильтрует каталог и возвращает лучшие предложения клиник с
              прозрачным разбором. Понимает <strong>ru / kz / en</strong>, работает офлайн на правилах
              и опционально подключает Claude.
            </p>
            <Link to="/assistant" className="lp-btn lp-btn-primary">
              Открыть ассистент <ArrowRight size={18} weight="bold" />
            </Link>
          </div>
          <ul className="lp-prompt-list" aria-label="Примеры запросов">
            <li>«анализ крови в Алматы дешевле 5000 ₸ для нерезидента»</li>
            <li>«самое дешёвое УЗИ»</li>
            <li>«консультация терапевта не дороже 8000»</li>
            <li>«cheapest MRI brain under 50k in Astana»</li>
          </ul>
        </div>
      </section>

      {/* ---- Tech (no eyebrow) ---- */}
      <section className="lp-section lp-container" aria-labelledby="lp-tech-h">
        <h2 id="lp-tech-h" className="lp-h2">Надёжный, проверенный стек</h2>
        <ul className="lp-tech">
          {TECH.map((t) => (
            <li key={t} className="lp-tech-chip">{t}</li>
          ))}
        </ul>
      </section>

      {/* ---- Final CTA (inverted teal panel — the closing moment) ---- */}
      <section className="lp-cta-band lp-cta-band--dark">
        <div className="lp-container lp-cta-band-inner">
          <h2 className="lp-h2 lp-cta-band-h">Посмотрите на реальных прайс-листах</h2>
          <p className="lp-section-lead">
            Поищите в начальном каталоге, спросите ассистента или войдите в дашборд оператора.
          </p>
          <div className="lp-cta-row lp-cta-row-center">
            <Link to="/search" className="lp-btn lp-btn-on-dark">Поиск в каталоге <ArrowRight size={18} weight="bold" /></Link>
            <Link to="/login" className="lp-btn lp-btn-on-dark-ghost">Вход для оператора</Link>
          </div>
        </div>
      </section>

      {/* ---- Footer ---- */}
      <footer className="lp-footer">
        <div className="lp-container lp-footer-inner">
          <div className="lp-footer-brand">
            <span className="lp-footer-word">Med<b>Archive</b></span>
            <p className="lp-footer-tag">
              Прайс-листы клиник — в единую, поисковую, версионированную базу услуг и цен.
            </p>
          </div>
          <nav className="lp-footer-nav" aria-label="Footer">
            <Link to="/search">Поиск</Link>
            <Link to="/assistant">Ассистент</Link>
            <Link to="/services">Услуги</Link>
            <Link to="/partners">Партнёры</Link>
            <Link to="/login">Вход</Link>
          </nav>
          <p className="lp-footer-legal">© 2026 MedArchive · MedTech Hackathon 2026, Кейс 2</p>
        </div>
      </footer>
    </main>
  );
}
