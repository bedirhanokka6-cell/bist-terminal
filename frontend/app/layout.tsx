import type { Metadata } from "next";
import "./globals.css";

export const metadata = {
  title: "BIST Katılım Terminal",
  description: "BIST Katılım 50 analiz ve paper trading terminali",
  manifest: "/manifest.webmanifest",
  themeColor: "#061725",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "BIST Terminal",
  },
  icons: {
    icon: "/icon-192.png",
    apple: "/icon-192.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
