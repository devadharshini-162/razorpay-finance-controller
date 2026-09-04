# Judge Demo — Razorpay AI Finance Controller

**Estimated time: 2–3 minutes**
Prerequisites: backend running on `localhost:8000`, React frontend running on `localhost:5173`.

---

## Quick Start (before the demo)

```bash
# Terminal 1 — FastAPI backend
cd razorpay-finance-controller
source fin_env/bin/activate
PYTHONPATH=. uvicorn app.api_app:app --reload --port 8000

# Terminal 2 — React frontend
cd frontend
npm run dev
```

Open **http://localhost:5173** in the browser.

---

## Demo Script

### 0:00 – 0:20 · The Problem

> *"Finance reconciliation at merchant scale is painful. Teams manually match Razorpay settlements against bank credits, merchant ledger entries, and payout exports — across different CSV schemas, different column names, different date formats. Errors get buried in spreadsheets. Nothing is auditable."*

**Show:** The upload screen — four source cards, Razorpay and Bank marked **MANDATORY**, the others **OPTIONAL**.

---

### 0:20 – 0:50 · Upload & Run

> *"Drop in two real CSVs — Razorpay settlements and the bank statement. The system handles schema differences automatically."*

**Action:**
1. Drag `data/raw/razorpay_settlements.csv` onto the **Razorpay Settlements** card.
2. Drag `data/raw/bank_statement.csv` onto the **Bank Statement** card.
3. Click **Run Reconciliation**. Watch the spinner.

> *"The pipeline runs: schema mapping, normalisation into a canonical model, then 6 deterministic matching rules in priority order. No LLM in the critical path."*

---

### 0:50 – 1:20 · Executive Overview

> *"81 Razorpay records. 65 matched deterministically — 80.2% resolution rate. 13 ambiguous, 3 unmatched. All in under a second."*

**Show:**
- The five KPI cards: **80.2%**, **65** deterministic, **0** LLM-resolved, **13** ambiguous, **3** unmatched.
- The **Matching Method Breakdown** bar chart — point out `exact_identifier` dominating (41 records).

> *"Notice LLM-resolved is zero. That's intentional — the mock provider is wired in but arbitration is disabled at the UI layer. The interface is ready for a real LLM provider; the contract is already defined."*

---

### 1:20 – 1:50 · Decisions Explorer

**Action:** Click **Decisions** tab → filter to **Ambiguous**.

> *"These 13 records couldn't be resolved deterministically — multiple bank candidates matched on amount or date. Let's inspect one."*

**Action:** Click any row → **Evidence** button. The Evidence Drawer opens.

> *"Every decision carries structured evidence: which fields matched, what the candidates were, confidence score. This is an audit trail, not a black box."*

---

### 1:50 – 2:10 · Exceptions Investigation

**Action:** Click **Exceptions** tab.

> *"16 exceptions total. 6 are high severity:"*
- **3 duplicate** — multiple bank records share the same identifier
- **3 missing_record** — unmatched Razorpay settlements with no bank counterpart

> *"10 are ambiguous_match — medium severity, escalation candidates."*

**Action:** Click any high-severity exception → Evidence Drawer. Show the candidate IDs.

---

### 2:10 – 2:30 · Audit Trail

**Action:** Click **Audit** tab.

> *"Every record has a deterministic audit entry. Stage, method, decision, evidence. This is what an auditor needs — not aggregates, actual per-record traceability."*

---

### 2:30 – 2:55 · Grounded Finance Q&A

**Action:** Click **Q&A** tab. Type and send:

```
How many transactions were matched?
```

> *"The Q&A module doesn't call an LLM to answer that. It deterministically retrieves the ReconciliationReport facts, verifies the numbers, and returns a grounded answer."*

**Show:** The answer + the **Evidence** section showing the exact fact set (total_source_records, deterministic_matches, etc.).

Type a follow-up:

```
Which records are still ambiguous?
```

> *"It returns the exact record IDs from the reconciliation result. No hallucination possible — the answer is checked against the verified fact set before it's returned."*

---

### 2:55 – 3:00 · Close

> *"Same pipeline works with Merchant Ledger or a completely different fourth-source payout export — different column names, different schema, same canonical model underneath. No pipeline changes."*

---

## Key Talking Points

| Point | One sentence |
|---|---|
| **Deterministic first** | 80.2% of records resolved with zero LLM cost, with full audit evidence |
| **LLM is bounded** | Only genuinely ambiguous records escalate; provider output is Pydantic-validated before acceptance |
| **Hallucination containment** | Q&A answers are checked against the verified fact set before being shown |
| **Canonical model** | One `CanonicalTransaction` model; any CSV schema plugs in through schema mapping |
| **Auditability** | Every decision has a corresponding `AuditRecord`; nothing is implicit |
| **160 tests, 0 failures** | Full deterministic test coverage from M0 through M9 |
