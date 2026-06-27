import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { api, getAuthToken, setAuthToken, type AuthUser } from '../lib/api';

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  register: (email: string, password: string) => Promise<AuthUser>;
  logout: () => void;
}

const USER_KEY = 'medarchive_user';
const AuthContext = createContext<AuthState | null>(null);

function loadStoredUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    const u = JSON.parse(raw) as Partial<AuthUser>;
    if (u && typeof u.id === 'string' && typeof u.email === 'string' && (u.role === 'user' || u.role === 'admin')) {
      return u as AuthUser;
    }
    return null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => (getAuthToken() ? loadStoredUser() : null));
  const [loading, setLoading] = useState<boolean>(!!getAuthToken());

  function persist(u: AuthUser | null) {
    setUser(u);
    if (u) localStorage.setItem(USER_KEY, JSON.stringify(u));
    else localStorage.removeItem(USER_KEY);
  }

  useEffect(() => {
    const onUnauth = () => {
      setAuthToken(null);
      setUser(null);
      localStorage.removeItem(USER_KEY);
    };
    window.addEventListener('medarchive:unauthorized', onUnauth);
    if (getAuthToken()) {
      api
        .me()
        .then(persist)
        .catch(() => {
          setAuthToken(null);
          persist(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
    return () => window.removeEventListener('medarchive:unauthorized', onUnauth);
  }, []);

  async function login(email: string, password: string) {
    const { token, user: u } = await api.login(email, password);
    setAuthToken(token);
    persist(u);
    return u;
  }

  async function register(email: string, password: string) {
    const { token, user: u } = await api.register(email, password);
    setAuthToken(token);
    persist(u);
    return u;
  }

  function logout() {
    setAuthToken(null);
    persist(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
