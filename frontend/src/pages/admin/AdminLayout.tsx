import { NavLink, Outlet } from 'react-router-dom';

const subnav = [
  { to: 'dashboard', label: 'Dashboard' },
  { to: 'upload', label: 'Upload' },
  { to: 'documents', label: 'Documents' },
  { to: 'verification', label: 'Verification' },
  { to: 'unmatched', label: 'Unmatched' },
];

export function AdminLayout() {
  return (
    <main className="page">
      <header className="page-header">
        <div className="eyebrow">Operations</div>
        <h1>Admin console</h1>
        <p className="subtitle">
          Ingest archives, monitor parsing, and curate the normalization queues.
        </p>
      </header>

      <nav className="admin-subnav">
        {subnav.map((s) => (
          <NavLink
            key={s.to}
            to={s.to}
            className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          >
            {s.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </main>
  );
}
