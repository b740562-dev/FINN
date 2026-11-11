import type { NextConfig } from "next";

// Some Indian ISPs block *.supabase.co at the network level. The browser
// therefore never talks to Supabase directly: /sb/* on our own domain is
// rewritten (server-side, by Vercel/Next) to the Supabase project. See
// lib/supabase.ts, which points supabase-js at `${origin}/sb`.
const SUPABASE = (process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/+$/, "").replace(/\/rest\/v1$/, "");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  async rewrites() {
    return SUPABASE ? [{ source: "/sb/:path*", destination: `${SUPABASE}/:path*` }] : [];
  },
};

export default nextConfig;
