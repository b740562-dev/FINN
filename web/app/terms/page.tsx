import type { Metadata } from "next";
import Link from "next/link";
import { LogoMark } from "@/components/logo";

export const metadata: Metadata = { title: "Terms of use · FINN" };

const CONTACT = "noreply.finnofficial@gmail.com";

export default function Terms() {
  return (
    <main className="legal">
      <Link href="/" className="legal-brand"><LogoMark size={30} /><span className="logo">FINN</span></Link>
      <h1>Terms of use</h1>
      <p className="legal-date">Last updated 14 November 2026</p>

      <p>By using FINN you agree to these terms. If you don&apos;t agree, please don&apos;t use the app.</p>

      <h2>1. Information only, not advice</h2>
      <p>FINN summarises publicly available information: stock exchange filings, company reports and disclosures, and end-of-day market data. Nothing in FINN, including Surya&apos;s answers, is investment advice, research or a recommendation to buy, sell or hold any security. FINN is not a SEBI-registered investment adviser or research analyst. Investment decisions are yours; consider consulting a SEBI-registered adviser.</p>

      <h2>2. Accuracy</h2>
      <p>We check numbers against their sources and link every claim to the original, but data can be delayed, incomplete or wrong, and AI-generated summaries can contain errors. Always confirm important facts in the original filing before acting on them. FINN is provided &quot;as is&quot;, without warranties of any kind.</p>

      <h2>3. Your account</h2>
      <ul>
        <li>Guest accounts are for trying FINN. Signing out of a guest account can lose its portfolio; log in with Google or email to keep it.</li>
        <li>You&apos;re responsible for activity on your account and for keeping your sign-in secure.</li>
      </ul>

      <h2>4. Documents you upload</h2>
      <p>Only upload public company documents (annual reports, concall transcripts, investor presentations) that you&apos;re allowed to share. Documents you add on the You page are used only for your own account. Reports added from Research for a listed company report join FINN&apos;s shared library and are used to build research for everyone. We may remove any upload that is inaccurate, private or inappropriate.</p>

      <h2>5. Fair use</h2>
      <p>Don&apos;t misuse FINN: no automated scraping, overloading the service, attempting to access other users&apos; data, or using it for anything unlawful. We may suspend accounts that do.</p>

      <h2>6. Liability</h2>
      <p>To the extent the law allows, FINN and its makers aren&apos;t liable for any loss arising from use of the app or reliance on its information, including investment losses.</p>

      <h2>7. Changes</h2>
      <p>We may update FINN and these terms. Continued use after a change means you accept the updated terms. These terms are governed by the laws of India.</p>

      <p className="legal-foot">Questions: <a href={`mailto:${CONTACT}`}>{CONTACT}</a> · <Link href="/privacy">Privacy policy</Link> · <Link href="/login">Back to FINN</Link></p>
    </main>
  );
}
