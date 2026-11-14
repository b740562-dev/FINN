import type { Metadata } from "next";
import Link from "next/link";
import { LogoMark } from "@/components/logo";

export const metadata: Metadata = { title: "Privacy policy · FINN" };

const CONTACT = "noreply.finnofficial@gmail.com";

export default function Privacy() {
  return (
    <main className="legal">
      <Link href="/" className="legal-brand"><LogoMark size={30} /><span className="logo">FINN</span></Link>
      <h1>Privacy policy</h1>
      <p className="legal-date">Last updated 14 November 2026</p>

      <p>FINN is an investment companion for people who hold Indian listed stocks. This page explains what we store, why, and how to remove it.</p>

      <h2>What we store</h2>
      <ul>
        <li><b>Your account:</b> your email address. If you sign in with Google, also your name and profile photo from Google. Guests get an anonymous account with no personal details.</li>
        <li><b>What you add:</b> your portfolio (companies and quantities), alert settings, profile details you choose to fill in, your chats with Surya, and any reports you upload.</li>
        <li><b>Basic logs:</b> sign-in events and errors, used to keep the service working.</li>
      </ul>

      <h2>How we use it</h2>
      <ul>
        <li>To show the news, alerts and research that matter to your holdings.</li>
        <li>To answer your questions in Surya. Questions, and the report passages needed to answer them, are processed by Google&apos;s Gemini AI service.</li>
        <li>We don&apos;t sell your data, show ads, or use it for anything other than running FINN.</li>
      </ul>

      <h2>Where it lives</h2>
      <p>Data is stored in a Supabase database (Mumbai region) protected by row-level security, so each account can only read its own data. The app is hosted on Vercel and Render. Reports you upload join FINN&apos;s shared library of public company documents.</p>

      <h2>Your choices</h2>
      <ul>
        <li>Edit or clear your profile at any time under <i>Edit profile</i>, and remove documents you uploaded under <i>Your documents</i>.</li>
        <li>To delete your account and everything linked to it, email <a href={`mailto:${CONTACT}`}>{CONTACT}</a> from the address you signed in with.</li>
      </ul>

      <h2>Not investment advice</h2>
      <p>FINN summarises public company information. It does not give buy or sell recommendations.</p>

      <p className="legal-foot">Questions: <a href={`mailto:${CONTACT}`}>{CONTACT}</a> · <Link href="/login">Back to FINN</Link></p>
    </main>
  );
}
