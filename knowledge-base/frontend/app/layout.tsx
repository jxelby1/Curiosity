import type { Metadata } from 'next';

import { AuthGate, AuthProvider } from '@/components/auth-provider';
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '@/lib/brand';

import './globals.css';

export const metadata: Metadata = {
  title: PRODUCT_NAME,
  description: PRODUCT_TAGLINE
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans studio-shell">
        <AuthProvider>
          <AuthGate>{children}</AuthGate>
        </AuthProvider>
      </body>
    </html>
  );
}
