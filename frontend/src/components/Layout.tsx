import { NavLink, Link, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useScrollReveal } from '../lib/useScrollReveal';

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
        <Link to="/" className="brand">
          <span className="logo">M</span>
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
      <NavBar />
      <div className="route-view" key={pathname}>
        <Outlet />
      </div>
    </div>
  );
}
