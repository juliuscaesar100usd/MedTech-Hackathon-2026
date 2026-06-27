import { NavLink, Link, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const baseNav = [
  { to: '/', label: 'Home', end: true },
  { to: '/search', label: 'Search' },
  { to: '/assistant', label: 'Assistant' },
  { to: '/services', label: 'Services' },
  { to: '/partners', label: 'Partners' },
];

export function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const items = user?.role === 'admin' ? [...baseNav, { to: '/admin', label: 'Admin' }] : baseNav;

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
              <button type="button" className="nav-logout" onClick={onLogout}>Logout</button>
            </>
          ) : (
            <NavLink to="/login" className="nav-link">Login</NavLink>
          )}
        </div>
      </div>
    </nav>
  );
}

export function Layout() {
  return (
    <div className="app-shell">
      <NavBar />
      <Outlet />
    </div>
  );
}
