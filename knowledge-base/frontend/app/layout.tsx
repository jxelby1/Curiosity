import type { Metadata } from 'next';

import { AuthGate, AuthProvider } from '@/components/auth-provider';

import './globals.css';

export const metadata: Metadata = {
  title: 'Knowledge Base Learning System',
  description: 'PoC multi-agent learning companion'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        className="font-sans"
        style={{ fontFamily: '"Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif' }}
      >
        <AuthProvider>
          <AuthGate>{children}</AuthGate>
        </AuthProvider>
      </body>
    </html>
  );
}
