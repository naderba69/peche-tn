import type { MetadataRoute } from "next";

export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Peche TN — قرار السيرفكاست",
    short_name: "Peche TN",
    description: "قرار سيرفكاست مجاني وآمن أولاً للساحل التونسي",
    id: "/",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "any",
    categories: ["sports", "utilities"],
    background_color: "#071719",
    theme_color: "#071719",
    lang: "ar-TN",
    dir: "rtl",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
    ],
    shortcuts: [
      {
        name: "خطّط حصتك",
        short_name: "خطّط",
        description: "افتح مخطط قرار السيرفكاست مباشرة",
        url: "/#planner",
        icons: [{ src: "/icon-192.png", sizes: "192x192", type: "image/png" }],
      },
      {
        name: "قائمة السلامة",
        short_name: "السلامة",
        description: "افتح قائمة التحقق الميدانية",
        url: "/#field-checklist",
        icons: [{ src: "/icon-192.png", sizes: "192x192", type: "image/png" }],
      },
    ],
  };
}
