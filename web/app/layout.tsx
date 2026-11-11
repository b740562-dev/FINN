import type { Metadata, Viewport } from "next";
import { Inter, Manrope } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/auth";

const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
// Labels, numbers and the logo use Manrope (geometric sans) with tabular figures.
const mono = Manrope({ subsets: ["latin"], variable: "--font-mono", display: "swap", weight: ["500", "600", "700", "800"] });

export const metadata: Metadata = {
  title: "FINN",
  description: "Your portfolio's filter: what changed, why it matters, and research grounded in primary sources.",
  applicationName: "FINN",
  appleWebApp: { capable: true, title: "FINN", statusBarStyle: "black-translucent" },
  icons: { apple: "/apple-touch-icon.png" },
};

export const viewport: Viewport = {
  themeColor: "#06110c",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-IN" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
