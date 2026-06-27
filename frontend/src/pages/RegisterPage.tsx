import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../lib/api';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError('Пароль должен содержать не менее 8 символов.');
      return;
    }
    setBusy(true);
    try {
      await register(email, password);
      navigate('/search', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка регистрации.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-wrap">
      <form className="auth-card" onSubmit={onSubmit}>
        <h1 className="auth-title">Создать аккаунт</h1>
        <label className="auth-label">
          Эл. почта
          <input className="auth-input" type="email" value={email} autoComplete="email"
                 onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label className="auth-label">
          Пароль
          <input className="auth-input" type="password" value={password} autoComplete="new-password"
                 onChange={(e) => setPassword(e.target.value)} required minLength={8} />
        </label>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button className="auth-btn" type="submit" disabled={busy}>
          {busy ? 'Создание…' : 'Создать аккаунт'}
        </button>
        <p className="auth-alt">
          Уже есть аккаунт? <Link to="/login">Войти</Link>
        </p>
      </form>
    </main>
  );
}
