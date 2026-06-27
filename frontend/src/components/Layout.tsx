import { Suspense } from 'react';
import { NavLink, Link, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useScrollReveal } from '../lib/useScrollReveal';
import { Loading } from './States';

/* Brand mark: teal chip + medical cross over a faint "archive" shelf line.
   Kept in sync with public/logo.svg (favicon). The mark carries the medical
   meaning; the wordmark carries "Archive". */
function BrandMark() {
  return (
    <svg className="logo" width={30} height={30} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="ma-grad" x1="4" y1="3" x2="28" y2="29" gradientUnits="userSpaceOnUse">
          <stop stopColor="#0891b2" />
          <stop offset="1" stopColor="#0e7490" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#ma-grad)" />
      <rect x="14" y="7" width="4" height="18" rx="2" fill="#ffffff" />
      <rect x="8" y="11" width="16" height="4" rx="2" fill="#ffffff" />
      <rect x="10.5" y="21.5" width="11" height="2.5" rx="1.25" fill="#ffffff" fillOpacity="0.5" />
    </svg>
  );
}

const baseNav = [
  { to: '/', label: 'Главная', end: true },
  { to: '/search', label: 'Поиск' },
  { to: '/assistant', label: 'Ассистент' },
  { to: '/services', label: 'Услуги' },
  { to: '/partners', label: 'Партнёры' },
];

export function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const items = user?.role === 'admin' ? [...baseNav, { to: '/admin', label: 'Админ' }] : baseNav;

  function onLogout() {
    logout();
    navigate('/', { replace: true });
  }

  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <Link to="/" className="brand" aria-label="MedArchive — на главную">
          <BrandMark />
          <span className="brand-name">
            Med<b>Archive</b>
          </span>
        </Link>
        <div className="nav-links">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={(item as { end?: boolean }).end}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </div>
        <div className="nav-auth">
          {user ? (
            <>
              <span className="nav-user" title={user.email}>{user.email}</span>
              <button type="button" className="nav-logout" onClick={onLogout}>Выйти</button>
            </>
          ) : (
            <NavLink to="/login" className="nav-link">Войти</NavLink>
          )}
        </div>
      </div>
    </nav>
  );
}

export function Layout() {
  // Key on pathname (not search) so each navigation remounts the view and
  // replays the entrance animation, while ?q= changes don't re-trigger it.
  const { pathname } = useLocation();
  useScrollReveal();
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Перейти к содержимому
      </a>
      <NavBar />
      <div className="route-view" id="main-content" tabIndex={-1} key={pathname}>
        <Suspense fallback={<Loading />}>
          <Outlet />
        </Suspense>
      </div>
    </div>
  );
}
