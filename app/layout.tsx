import type { Metadata, Viewport } from "next";
import { Cairo, Tajawal } from "next/font/google";
import { ConnectionStatus } from "@/components/ConnectionStatus";
import { ServiceWorkerRegistration } from "@/components/ServiceWorkerRegistration";
import { BottomNav, SiteHeader } from "@/components/SiteNav";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

const cairo = Cairo({
  subsets: ["arabic", "latin"],
  weight: "variable",
  variable: "--font-cairo",
  display: "swap",
});

const tajawal = Tajawal({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "700"],
  variable: "--font-tajawal",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Peche TN | قرار السيرفكاست في تونس",
    template: "%s | Peche TN",
  },
  description:
    "أداة مجانية وآمنة أولاً لتحليل الرياح والموج والمدّ واقتراح أفضل نافذة سيرفكاست على الساحل التونسي.",
  applicationName: "Peche TN",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon-192.png" },
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "Peche TN" },
  formatDetection: { telephone: false },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: "#071719",
  colorScheme: "dark",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ar-TN" dir="rtl" className={`${cairo.variable} ${tajawal.variable}`}>
      <body>
        <SiteHeader />
        {children}
        <BottomNav />
        <ConnectionStatus />
        <ServiceWorkerRegistration />
      </body>
    </html>
  );
}
