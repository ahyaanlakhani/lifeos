import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Nav } from "../components/Nav";

export const metadata: Metadata = {
  title: "Glass Box — LifeOS",
  description:
    "The control plane for LifeOS: see what the agents are doing, and stop them.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Approvals get used on a phone in a hurry. Pinch-zoom stays available.
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0a0b0d" },
    { media: "(prefers-color-scheme: light)", color: "#fbfbfc" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <header className="topbar">
            <div className="brand">
              Glass&nbsp;Box <small>LifeOS</small>
            </div>
            <Nav />
          </header>
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
