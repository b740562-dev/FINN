"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { put } from "@/lib/api";
import type { Profile } from "@/lib/types";
import { useAuth } from "@/components/auth";
import { DEFAULT_NAME, Face, isVerified, profileCompleteness, useData, VerifiedTick } from "@/components/data";
import { Ring } from "@/components/ring";
import { ProfileButton } from "@/components/profile-menu";

const GENDERS: [Profile["gender"], string][] = [["female", "Female"], ["male", "Male"], ["non_binary", "Non-binary"], ["prefer_not_to_say", "Prefer not to say"]];
const EXPERIENCE: [Profile["experience"], string][] = [["new", "New"], ["intermediate", "1–3 yrs"], ["experienced", "3–10 yrs"], ["professional", "Professional"]];

type Form = Omit<Profile, "email" | "is_anonymous" | "created_at" | "updated_at">;
const EMPTY: Form = { full_name: "", gender: null, work_company: "", work_role: "", education: "", city: "", experience: null, bio: "" };

export default function EditProfile() {
  const { session } = useAuth();
  const { profile, setProfile } = useData();
  const router = useRouter();
  const user = session?.user as { email?: string | null; is_anonymous?: boolean } | undefined;
  const guest = Boolean(user?.is_anonymous);
  const [f, setF] = useState<Form>(EMPTY);
  const email = user?.email ?? "";
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (profile) {
      const { email: _e, is_anonymous: _a, created_at: _c, updated_at: _u, ...rest } = profile;
      void _e; void _a; void _c; void _u;
      setF({ ...EMPTY, ...Object.fromEntries(Object.entries(rest).map(([k, v]) => [k, v ?? (k === "gender" || k === "experience" ? null : "")])) } as Form);
    }
  }, [profile]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    try {
      const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : v]));
      const p = await put<Profile>("/profile", body);
      setProfile(p);
      const text = "Profile saved.";
      setMsg({ ok: true, text });
    } catch (er) {
      setMsg({ ok: false, text: (er as Error).message });
    } finally {
      setSaving(false);
    }
  }

  const verified = isVerified(session?.user as Parameters<typeof isVerified>[0]);

  return (
    <>
      <header className="topbar">
        <ProfileButton />
        <div className="brand">
          <button className="logo" style={{ fontSize: 17 }} onClick={() => router.back()}>‹ Edit profile</button>
        </div>
      </header>

      <form onSubmit={save} className="pf">
        <div className="pf-hero">
          <div className={`pf-av ${guest ? "guest" : ""}`}><Face profile={{ ...(profile as Profile), full_name: f.full_name } as Profile} email={email} guest={guest} /></div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="pf-name">{f.full_name || (guest ? DEFAULT_NAME : email || "Your name")}{verified && <VerifiedTick size={16} />}</div>
            <div className="pf-sub">{[f.work_role, f.work_company].filter(Boolean).join(" · ") || "Add your work below"}</div>
          </div>
          <Ring pct={profileCompleteness(f, email)} size={50} stroke={4.5} />
        </div>

        <section className="panel">
          <h3>Basics</h3>
          <label className="pf-f"><span>Full name</span>
            <input className="txt" value={f.full_name ?? ""} onChange={(e) => set("full_name", e.target.value)} placeholder="Your name" maxLength={80} autoComplete="name" /></label>
          <div className="pf-f"><span>Gender</span>
            <div className="chips">{GENDERS.map(([v, l]) => (
              <button type="button" key={v} className={`chip ${f.gender === v ? "on" : ""}`} onClick={() => set("gender", f.gender === v ? null : v)}>{l}</button>
            ))}</div></div>
          <div className="pf-f"><span>Email</span>
            {guest || !email ? (
              <Link href="/login" className="pf-email login">Log in with email <em>· one-time code, keeps this portfolio</em></Link>
            ) : (
              <div className="pf-email">{email}{verified ? <VerifiedTick size={16} /> : <em>· not verified</em>}</div>
            )}</div>
          <label className="pf-f"><span>City</span>
            <input className="txt" value={f.city ?? ""} onChange={(e) => set("city", e.target.value)} placeholder="Mumbai" maxLength={60} autoComplete="address-level2" /></label>
        </section>

        <section className="panel">
          <h3>Work &amp; education</h3>
          <div className="pf-row">
            <label className="pf-f"><span>Works at</span>
              <input className="txt" value={f.work_company ?? ""} onChange={(e) => set("work_company", e.target.value)} placeholder="Company" maxLength={80} autoComplete="organization" /></label>
            <label className="pf-f"><span>Role</span>
              <input className="txt" value={f.work_role ?? ""} onChange={(e) => set("work_role", e.target.value)} placeholder="Analyst" maxLength={80} autoComplete="organization-title" /></label>
          </div>
          <label className="pf-f"><span>Education</span>
            <input className="txt" value={f.education ?? ""} onChange={(e) => set("education", e.target.value)} placeholder="e.g. B.Tech, IIT Delhi" maxLength={120} /></label>
        </section>

        <section className="panel">
          <h3>Investing</h3>
          <div className="pf-f"><span>Experience</span>
            <div className="chips">{EXPERIENCE.map(([v, l]) => (
              <button type="button" key={v} className={`chip ${f.experience === v ? "on" : ""}`} onClick={() => set("experience", f.experience === v ? null : v)}>{l}</button>
            ))}</div></div>
          <label className="pf-f"><span>About <em className="pf-hint">{(f.bio ?? "").length}/280</em></span>
            <textarea className="txt" rows={3} value={f.bio ?? ""} onChange={(e) => set("bio", e.target.value)} placeholder="Your investing style in a line" maxLength={280} /></label>
        </section>

        <div className="pf-actions">
          <button className="btn primary block" disabled={saving}>{saving ? "Saving…" : "Save profile"}</button>
          {msg && <div className={msg.ok ? "ok" : "err"} style={{ margin: 0 }}>{msg.text}</div>}
          <Link className="link" href="/you" style={{ textAlign: "center", display: "block", marginTop: 6 }}>Portfolio, alert rules &amp; settings →</Link>
        </div>
      </form>
    </>
  );
}
