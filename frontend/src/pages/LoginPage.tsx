import { useState, type FormEvent } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../lib/api';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const dest = (location.state as { from?: string } | null)?.from ?? '/search';

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const user = await login(email, password);
      navigate(user.role === 'admin' ? '/admin' : dest, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка входа.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-wrap">
      <form className="auth-card" onSubmit={onSubmit}>
        <h1 className="auth-title">Войти</h1>
        <label className="auth-label">
          Эл. почта
          <input className="auth-input" type="email" value={email} autoComplete="email"
                 onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label className="auth-label">
          Пароль
          <input className="auth-input" type="password" value={password} autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button className="auth-btn" type="submit" disabled={busy}>
          {busy ? 'Вход…' : 'Войти'}
        </button>
        <p className="auth-alt">
          Нет аккаунта? <Link to="/register">Регистрация</Link>
        </p>
      </form>
    </main>
  );
}
