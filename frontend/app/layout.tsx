import type { ReactNode } from "react";

export const metadata = {
  title: "Paladins .ini Config Analyzer",
  description: "Deterministic analysis for Paladins (Hi-Rez UE3 fork) config files.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body
        style={{
          fontFamily: "system-ui, -apple-system, sans-serif",
          margin: 0,
          background: "#0b0d12",
          color: "#e4e7ee",
          minHeight: "100vh",
        }}
      >
        <main style={{ maxWidth: 960, margin: "0 auto", padding: "2rem 1.25rem" }}>
          {children}
        </main>
      </body>
    </html>
  );
}
