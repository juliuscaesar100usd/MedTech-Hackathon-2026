import { NavLink, Outlet } from 'react-router-dom';

const subnav = [
  { to: 'dashboard', label: 'Дашборд' },
  { to: 'upload', label: 'Загрузка' },
  { to: 'documents', label: 'Документы' },
  { to: 'verification', label: 'Очередь верификации' },
  { to: 'unmatched', label: 'Несопоставленные' },
];

export function AdminLayout() {
  return (
    <main className="page">
      <header className="page-header">
        <div className="eyebrow">Операции</div>
        <h1>Консоль администратора</h1>
        <p className="subtitle">
          Загружайте архивы, отслеживайте разбор файлов и управляйте очередями нормализации.
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
