"""Upload-path check, in-process (FastAPI TestClient), so it runs even on a
network that blocks *.supabase.co: the Supabase token check is swapped for a
fixed test user; everything else (DB, Gemini, background job) is real.

 - guest upload -> 403
 - signed-in upload -> 202 job -> done; promise vs delivered rebuilt
 - same file again -> instant duplicate
 - source is recorded; "your documents" lists it; another user can't remove it;
   the uploader can (chunks go with it)
Leaves the shared library exactly as it was (test document + jobs deleted)."""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from finn.api.auth import User, current_user  # noqa: E402
from finn.api.main import app  # noqa: E402
from finn.db import cursor  # noqa: E402
from finn.pull import sections as S  # noqa: E402
from scripts.check_research import make_pdf  # noqa: E402

SYM = "INFY"
GUEST = User(id=str(uuid.uuid4()), is_anonymous=True, email=None)
MEMBER = User(id=str(uuid.uuid4()), is_anonymous=False, email="tester@example.com")
OTHER = User(id=str(uuid.uuid4()), is_anonymous=False, email="other@example.com")


def as_user(u: User) -> None:
    app.dependency_overrides[current_user] = lambda: u


def main() -> None:
    client = TestClient(app)
    pdf = make_pdf([[
        f"Infosys earnings call test transcript {uuid.uuid4().hex[:8]}.",
        "Management: we expect revenue growth of 12 to 14 percent in constant currency for FY27.",
        "We are guiding operating margins in the band of 20 to 22 percent for the year.",
    ]])
    files = {"file": ("CC-test.pdf", pdf, "application/pdf")}
    form = {"kind": "transcript", "period": "2026-10-16", "source": "company_website",
            "source_url": "https://www.infosys.com/investors.html"}
    doc_id = None
    try:
        as_user(GUEST)
        r = client.post(f"/research/{SYM}/documents", files=files, data=form)
        print("guest upload ->", r.status_code, r.json()["detail"][:70])

        as_user(MEMBER)
        r = client.post(f"/research/{SYM}/documents", files=files, data=form)  # TestClient runs the background task
        print("member upload ->", r.status_code, r.json())
        j = client.get(f"/research/{SYM}/jobs/{r.json()['job_id']}").json()
        print(f"job -> {j['status']} in {j['seconds']}s, result={j['result']}, error={j['error']}")
        doc_id = (j.get("result") or {}).get("document_id")

        ov = client.get(f"/research/{SYM}").json()
        print("overview ->", ov["docs"]["transcripts"], "transcript(s) on file")
        pd = client.get(f"/research/{SYM}/sections/promise_delivered").json()
        print("promise_delivered ->", pd["status"], "(cached: rebuilt by the job)" if pd.get("cached") else "(fresh)",
              pd["content"].get("score"))
        for it in pd["content"].get("items", [])[:3]:
            print(f"   [{it['verdict']}] {it['promise'][:70]} | actual: {it.get('actual')}")

        r = client.post(f"/research/{SYM}/documents", files=files, data=form)
        print("same file again ->", r.status_code, r.json())

        r = client.get(f"/research/{SYM}/jobs/999999999")
        print("unknown job ->", r.status_code)

        r = client.post(f"/research/{SYM}/documents", files=files, data={**form, "source": "rumour"})
        print("bad source ->", r.status_code)

        mine = client.get("/documents/mine").json()
        d = next((x for x in mine["documents"] if x["id"] == doc_id), None)
        print("your documents ->", len(mine["documents"]), "doc(s);",
              d and f"{d['symbol']} {d['label']} · {d['source_label']} · {d['source_url']}")

        as_user(OTHER)
        r = client.delete(f"/documents/{doc_id}")
        print("other user removes it ->", r.status_code)
        print("other user's list ->", len(client.get("/documents/mine").json()["documents"]), "doc(s)")

        as_user(MEMBER)
        r = client.delete(f"/documents/{doc_id}")
        print("uploader removes it ->", r.status_code, r.json())
        with cursor(commit=False) as c:
            c.execute("select count(*) from public.doc_chunks where document_id = %s", (doc_id,))
            print("chunks left ->", c.fetchone()[0])
        print("list after ->", len(client.get("/documents/mine").json()["documents"]), "doc(s)")
        print("remove again ->", client.delete(f"/documents/{doc_id}").status_code)
    finally:
        app.dependency_overrides.clear()
        with cursor() as c:
            if doc_id:
                c.execute("delete from public.documents where id = %s", (doc_id,))
            c.execute("delete from public.ingest_jobs where symbol = %s and filename = 'CC-test.pdf'", (SYM,))
        S.invalidate(SYM)
        for sec in S.SECTIONS:                    # leave INFY's dossier warm, as before
            S.get_section(SYM, sec)
        print("cleaned up: test document + jobs removed; INFY dossier rebuilt without it")


if __name__ == "__main__":
    main()
