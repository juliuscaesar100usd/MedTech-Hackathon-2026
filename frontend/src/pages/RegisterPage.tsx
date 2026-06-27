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
      setError('Password must be at least 8 characters.');
      return;
    }
    setBusy(true);
    try {
      await register(email, password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Registration failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={onSubmit}>
        <h1 className="auth-title">Create account</h1>
        <label className="auth-label">
          Email
          <input className="auth-input" type="email" value={email}
                 onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label className="auth-label">
          Password
          <input className="auth-input" type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)} required minLength={8} />
        </label>
        {error && <p className="auth-error">{error}</p>}
        <button className="auth-btn" type="submit" disabled={busy}>
          {busy ? 'Creating…' : 'Create account'}
        </button>
        <p className="auth-alt">
          Have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
