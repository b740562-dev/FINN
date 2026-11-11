import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "FINN: Financial Investment Agent",
    short_name: "FINN",
    description: "What changed in your portfolio, why it matters, and research grounded in primary sources.",
    start_url: "/",
    display: "standalone",
    background_color: "#0a0c0f",
    theme_color: "#0a0c0f",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
    ],
  };
}
