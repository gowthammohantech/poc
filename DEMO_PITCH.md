# Invoice OCR Agent — Demo Notes & Client Q&A

---

## Demo Notes

**1. Open on the Agent Hub, not the invoice screen.**
Two live agents, two coming soon. Line to say: *"This is a chassis, not a point
tool — same pipeline, different document type."* Sets the platform frame before
anything runs.

**2. Walk the "How It Works" strip before uploading anything.**
Six steps, ten seconds. The audience then knows what to watch for, which makes
the complexity-routing moment land instead of passing unnoticed.

**3. Upload a clean invoice — low complexity score → Tesseract.**
*"It measured the page before it read it. This one was easy, so it cost us
nothing."* The scorer uses real CV signals (line density, blur, column
detection), not a guess.

**4. Then upload a deliberately awful scan — high score → Vision LLM.**
*"Same pipeline, different engine, automatically. Nobody configured this."*
This is the architectural point: one product, per-page cost/accuracy decision.

**5. Spend real time on the review screen.**
Confidence is scored **per field**, not per document. *"Humans review 3 fields,
not 30 — that's the number you actually pay for."* Reframe the whole conversation
from accuracy to review workload.

**6. Show line items with GST detail.**
HSN/SAC, per-line CGST/SGST/IGST rate and amount, taxable value. *"This isn't a
generic invoice model with GST bolted on — it's GST-native."* Strongest
differentiator for an Indian client.

**7. Your best moment: the invoice with a deliberate arithmetic error.**
Validation fires and shows the actual arithmetic. Say plainly: *"No number on
this screen was validated by a language model. The LLM reads; it never decides."*

**8. Demo the mailbox connector sync.**
Invoices arrive from email, dedupe and skip rules fire. *"Nobody uploads anything
in production — this is how it really runs."* Point at the source column:
MANUAL / API / CONNECTOR provenance on every document.

**9. Close on export.**
JSON / CSV / Excel. *"Structured output — integration is field mapping, not
parsing."*

**10. Mention Bank Reconciliation, do not open it.**
Two sentences as proof of depth, then offer a follow-up session. A second product
in a first demo dilutes the story and doubles the objections.

**Have ready before the meeting:** one clean printed invoice, one genuinely bad
scan, one invoice with a planted arithmetic error, and one unseen vendor layout —
ideally supplied by the client.

---

## Client Q&A

Answers written to be said out loud. Where the honest answer is a limitation,
it's marked **[Concede]** — say it straight; it buys credibility for the rest.

**1. "What's your accuracy rate?"**
"I could give you a number, but neither of us could verify it on your documents.
Better offer: send us 100 real invoices. We'll show field-level confidence and
exactly which ones needed a human. That's the number you actually pay for —
review workload, not accuracy."

**2. "Does it hallucinate numbers?"**
"Output is schema-constrained, so it can't invent fields — and it can't quietly
invent a total either. The total is re-computed from the line items and compared
within tolerance. A hallucinated number fails that check and gets flagged. That's
exactly why validation lives in code rather than asking the model to check itself."

**3. "What happens when it gets something wrong?"**
"Two independent safety nets. Confidence is scored per field, so anything
uncertain is flagged and routed to review rather than passed through. And the
arithmetic and GST rules are deterministic code — so even when the model is
confident and wrong, a total that doesn't add up gets caught."

**4. "How long does a new vendor layout take to onboard?"**
"Zero. There are no templates and no per-vendor training set — an unseen layout
works on first sight. Give me one you've never processed and I'll run it right
now." *(Then actually do it.)*

**5. "What does it cost per invoice?"**
"That depends on your document mix — and that's the whole point of the routing.
Clean printed invoices, usually the large majority, run on local engines at
effectively zero marginal cost. Only the hard tail reaches a paid model. Send a
representative sample and we'll compute the real number for your mix."

**6. "Where does our data go? Can it run air-gapped?"**
"It runs in your environment — documents on your filesystem, data in your
database, OAuth tokens encrypted at rest. The only thing that leaves is the
escalated page image going to the vision model, and routing is designed so most
documents never take that path. For fully air-gapped: disable escalation and
route hard documents to a human, or swap the vision leg for a local model. The
pipeline is model-agnostic, so neither is a rewrite."

**7. "Do you train on our data?"**
"No. There's no fine-tuning step anywhere in the system — the model is used
read-only against a fixed schema and prompt."

**8. "How does this get into SAP / Tally / our ERP?"**
"Structured JSON, plus CSV and Excel export, plus a REST API on every endpoint.
Because output is schema-constrained, integration is field mapping, not parsing —
usually days, not months. **[Concede]** We don't have a certified SAP connector;
OpenText does. If SAP certification is a hard requirement, that's a real point in
their favour."

**9. "How many invoices a day can it handle?"**
"**[Concede]** Today's build is a single-node sandbox — SQLite, local storage.
Sized for a pilot, not your full volume. The pipeline is stateless per document,
so scaling is the well-trodden path: Postgres, object storage, a job queue,
horizontal workers. I'd rather show you a working pilot in three weeks than a
scale claim I can't back."

**10. "How do you handle users and access control?"**
"**[Concede]** No per-user model yet — a connected mailbox is shared by everyone
who can sign in. Authentication and role-based access is standard work and belongs
in production hardening, alongside the database and storage changes. I'd rather
tell you now than have you find it in a security review."

**11. "Does it handle handwritten or regional-language invoices?"**
"The complexity scorer detects handwriting and low contrast and routes those pages
to the vision model, which handles both far better than classic OCR. **[Concede]**
Handwriting is still the hardest case in document AI. What we guarantee is that
it's never silently accepted — it comes back low-confidence and lands in review."

**12. "Why you and not OpenText?"**
"If you need enterprise records management, retention policy and certified SAP
capture at millions of documents a day — buy OpenText, genuinely. If what you need
is Indian AP invoices read accurately, GST-validated, and turned into clean data in
weeks rather than quarters, that's the specific thing we're better at. And we're not
asking you to rip anything out — we sit in front as the fast lane for finance
documents. Start with one AP inbox and measure it."
