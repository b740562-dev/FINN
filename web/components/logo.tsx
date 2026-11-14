import { useId } from "react";

/** FINN's mark: three rising bars with a trend line, in the app's palette.
 *  Same geometry as public/logo.svg (favicon, app icons, PWA, share preview). */
export function LogoMark({ size = 32, className = "" }: { size?: number; className?: string }) {
  const uid = useId().replace(/:/g, "");
  const bg = `lmBg${uid}`, bar = `lmBar${uid}`;
  return (
    <svg className={`logo-mark ${className}`} width={size} height={size} viewBox="0 0 512 512" aria-hidden>
      <defs>
        <radialGradient id={bg} cx="0.3" cy="0.22" r="0.95">
          <stop offset="0" stopColor="#17502f" />
          <stop offset="0.65" stopColor="#0a2016" />
          <stop offset="1" stopColor="#06110c" />
        </radialGradient>
        <linearGradient id={bar} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#d4f77a" />
          <stop offset="1" stopColor="#5be38f" />
        </linearGradient>
      </defs>
      <circle cx="256" cy="256" r="256" fill={`url(#${bg})`} />
      <circle cx="256" cy="256" r="248" fill="none" stroke="#c6f45e" strokeOpacity="0.35" strokeWidth="10" />
      <rect x="124" y="294" width="72" height="96" rx="11" fill={`url(#${bar})`} />
      <rect x="220" y="220" width="72" height="170" rx="11" fill={`url(#${bar})`} />
      <rect x="316" y="146" width="72" height="244" rx="11" fill={`url(#${bar})`} />
      <path d="M160 294 L352 146" stroke="#fff" strokeWidth="9" strokeLinecap="round" />
      <circle cx="352" cy="146" r="20" fill="#fff" />
      <circle cx="352" cy="146" r="10" fill="#7fe89a" />
    </svg>
  );
}

/** Mark + wordmark, for headers. */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span className="logo-lockup">
      <LogoMark size={size} />
      <span className="logo">FINN</span>
    </span>
  );
}
