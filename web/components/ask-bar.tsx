"use client";

import { useRouter } from "next/navigation";

/** The one floating control: a round "Ask me" button that opens the Surya chat. */
export function AskBar() {
  const router = useRouter();
  return (
    <button type="button" className="surya-orb" onClick={() => router.push("/surya")} aria-label="Ask Surya, your investment guide">
      <svg className="orb-ring" viewBox="0 0 66 66" aria-hidden>
        <defs><path id="orb-path" d="M33,33 m-27,0 a27,27 0 1,1 54,0 a27,27 0 1,1 -54,0" /></defs>
        <text><textPath href="#orb-path" textLength="168" lengthAdjust="spacing">ASK ME · ASK ME · ASK ME ·</textPath></text>
      </svg>
      <span className="orb-tip" role="tooltip">
        <b>Ask your most difficult investment question</b>
        <small>Answers grounded in verified company documents</small>
      </span>
      <span className="orb-core">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" />
        </svg>
      </span>
    </button>
  );
}
