'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  createContext,
  PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from 'react';

import { clearAuthToken, getAuthToken } from '@/lib/auth';
import { getMe, login as apiLogin, logout as apiLogout, register as apiRegister } from '@/lib/api';
import { AuthUser } from '@/lib/types';

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';

type AuthContextValue = {
  status: AuthStatus;
  user: AuthUser | null;
  login: (input: { email: string; password: string }) => Promise<void>;
  register: (input: { email: string; password: string; display_name: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const PUBLIC_EXACT_PATHS = new Set(['/']);
const PUBLIC_PREFIX_PATHS = ['/login', '/signup', '/forgot-password', '/reset-password'];

export function AuthProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser] = useState<AuthUser | null>(null);

  const refreshUser = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setUser(null);
      setStatus('unauthenticated');
      return;
    }

    try {
      const me = await getMe();
      setUser(me);
      setStatus('authenticated');
    } catch {
      clearAuthToken();
      setUser(null);
      setStatus('unauthenticated');
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = useCallback(
    async (input: { email: string; password: string }) => {
      await apiLogin(input);
      await refreshUser();
    },
    [refreshUser]
  );

  const register = useCallback(
    async (input: { email: string; password: string; display_name: string }) => {
      await apiRegister(input);
      await refreshUser();
    },
    [refreshUser]
  );

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
    setStatus('unauthenticated');
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      login,
      register,
      logout,
      refreshUser
    }),
    [status, user, login, register, logout, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth must be used within AuthProvider.');
  }
  return value;
}

function AuthLoadingScreen() {
  return (
    <main className="mx-auto max-w-5xl p-6 md:p-10">
      <section className="panel space-y-3 p-5">
        <div className="skeleton h-4 w-40" />
        <div className="skeleton h-8 w-72" />
        <div className="skeleton h-28 w-full" />
      </section>
    </main>
  );
}

export function AuthGate({ children }: PropsWithChildren) {
  const pathname = usePathname();
  const router = useRouter();
  const { status, user, logout } = useAuth();

  const isPublicPath =
    PUBLIC_EXACT_PATHS.has(pathname) ||
    PUBLIC_PREFIX_PATHS.some((path) => pathname.startsWith(path));

  useEffect(() => {
    if (status === 'loading') return;

    if (status === 'unauthenticated' && !isPublicPath) {
      const next = encodeURIComponent(pathname || '/topics');
      router.replace(`/login?next=${next}`);
      return;
    }

    if (status === 'authenticated' && isPublicPath) {
      router.replace('/topics');
    }
  }, [isPublicPath, pathname, router, status]);

  if (status === 'loading') {
    return <AuthLoadingScreen />;
  }

  if (status === 'unauthenticated' && !isPublicPath) {
    return <AuthLoadingScreen />;
  }

  if (status === 'authenticated' && isPublicPath) {
    return <AuthLoadingScreen />;
  }

  if (isPublicPath) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-black/10 bg-white/85 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-3 px-6 py-3 md:px-10">
          <div className="flex items-center gap-4">
            <Link href="/topics" className="text-sm font-semibold tracking-[0.08em] text-black/80">
              KNOWLEDGE BASE
            </Link>
            <nav className="hidden items-center gap-3 text-sm md:flex">
              <Link href="/topics" className="text-black/70 hover:text-black">
                Topics
              </Link>
              <Link href="/garden" className="text-black/70 hover:text-black">
                Garden
              </Link>
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <div className="hidden rounded-md border border-black/10 bg-white px-3 py-1.5 text-xs md:block">
              <p className="font-semibold">{user?.display_name || user?.email}</p>
              <p className="text-black/60">Level {user?.level ?? 1} · XP {user?.xp ?? 0}</p>
            </div>
            <button
              type="button"
              className="rounded-md border border-black/20 bg-white px-3 py-2 text-xs"
              onClick={async () => {
                await logout();
                router.push('/login');
              }}
            >
              Logout
            </button>
          </div>
        </div>
      </header>
      {children}
    </div>
  );
}
