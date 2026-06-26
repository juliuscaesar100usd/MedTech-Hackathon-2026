import { NavLink, Link, Outlet } from 'react-router-dom';

const navItems = [
  { to: '/', label: 'Search', end: true },
  { to: '/assistant', label: 'Assistant' },
  { to: '/services', label: 'Services' },
  { to: '/partners', label: 'Partners' },
  { to: '/admin', label: 'Admin' },
];

export function NavBar() {
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
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
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
