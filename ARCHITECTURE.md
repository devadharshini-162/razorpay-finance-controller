# Architecture — Razorpay AI Finance Controller

This document describes the system's data flow, service boundaries, and the deliberate design choices that keep LLM involvement bounded and auditable.

---

## High-Level Data Flow

```mermaid
flowchart TD
    A["📂 Raw CSV Files<br/>(Razorpay / Bank Statement /<br/>Merchant Ledger / 4th Source)"]

    subgraph MAP ["Schema Mapping & Normalisation"]
        B["LLM Schema Mapper<br/><code>schema_mapper.py</code><br/>Reads column headers → FieldMapping"]
        C["Normaliser<br/><code>normalizer.py</code><br/>Type coercion · date parsing · Decimal amounts"]
    end

    D["CanonicalTransaction[ ]<br/><em>Single shared data contract</em>"]

    subgraph DET ["Deterministic Match Engine  ·  matcher.py"]
        direction TB
        E1["① Batch Pre-pass<br/>batch_amount_reconciliation<br/>Sum of source group == single bank credit via shared UTR"]
        E2["② Exact Identifier<br/>exact_identifier<br/>UTR / settlement ref exact match after normalisation · conf 1.00"]
        E3["③ Exact Amount + Date<br/>exact_amount_date<br/>amount == bank.amount AND settlement_date == posted_date · conf 0.95"]
        E4["④ Financial Reconciliation<br/>financial_reconciliation<br/>gross − fee − tax = bank credit on same date · conf 0.92"]
        E5["⑤ Amount + Date Tolerance<br/>amount_date_tolerance<br/>amount matches AND |date diff| ≤ 3 days · conf 0.85"]
        E6["⑥ Refund Detection<br/>refund_identifier<br/>settlement_id starts with ref_ → bank debit match · conf 0.95"]
        E7["⑦ Ambiguous / Duplicate / Unmatched<br/>Multiple candidates → ambiguous · No match → unmatched"]
        E1 --> E2 --> E3 --> E4 --> E5 --> E6 --> E7
    end

    subgraph ARB ["LLM Arbitration (optional)  ·  arbitrator.py"]
        F1["Only ambiguous decisions enter"]
        F2["ArbitrationProvider.resolve_ambiguity()"]
        F3["LLMArbitrationDecision validated<br/>via Pydantic before acceptance"]
        F1 --> F2 --> F3
    end

    G["FinalReconciliationResult<br/>decisions · exceptions · audit_records"]

    subgraph REP ["Reporting  ·  report.py"]
        H["ReconciliationReport<br/>deterministic_matches · llm_resolved_matches<br/>ambiguous_records · unmatched_records<br/>overall_resolution_rate"]
    end

    subgraph QA ["Grounded Q&amp;A  ·  qa.py"]
        I1["QuestionInterpreter<br/>Deterministic intent parsing · no LLM"]
        I2["DeterministicRetriever<br/>Exact record lookup against FinalReconciliationResult"]
        I3["FactComputer<br/>Computes verified GroundedFactSet"]
        I4["AnswerGenerator<br/>Hallucination check on numbers + record IDs<br/>before answer is returned"]
        I1 --> I2 --> I3 --> I4
    end

    J["FastAPI Adapter<br/><code>api_app.py</code><br/>/api/reconcile · /api/qa/ask"]

    K["React Dashboard<br/>Vite · TypeScript · Tailwind CSS<br/>Overview · Decisions · Exceptions · Audit · Q&amp;A"]

    A --> MAP --> D --> DET --> G
    G --> ARB --> G
    G --> REP --> J
    G --> QA  --> J
    J --> K

    style MAP fill:#dbeafe,stroke:#3b82f6
    style DET fill:#dcfce7,stroke:#22c55e
    style ARB fill:#fef9c3,stroke:#eab308
    style REP fill:#dcfce7,stroke:#22c55e
    style QA  fill:#f3e8ff,stroke:#a855f7
    style K   fill:#f0fdf4,stroke:#16a34a
```

**Colour key:**
| Colour | Responsibility |
|---|---|
| 🔵 Blue | LLM-assisted (schema mapping only) |
| 🟢 Green | Fully deterministic |
| 🟡 Yellow | LLM-optional (arbitration, bounded by Pydantic contract) |
| 🟣 Purple | Grounded Q&A (deterministic retrieval; LLM optional for answer phrasing) |

---

## Service Responsibilities

### `schema_mapper.py` — Schema Mapping
The only stage where an LLM is **always** consulted. It receives a list of column headers from the uploaded CSV and returns a `FieldMapping` dictionary that maps columns to the canonical field names (`amount`, `reference`, `settlement_date`, etc.). The output is a pure data structure — the LLM makes no reconciliation decisions.

### `normalizer.py` — Normalisation
Converts raw row dictionaries into `CanonicalTransaction` Pydantic models. Handles type coercion (string → `Decimal`, string → `date`), UTR normalisation, and source tagging. **No LLM involvement.**

### `matcher.py` — Deterministic Match Engine
The heart of the system. Runs **6 matching methods** in strict priority order. Each method produces a `ReconciliationDecision` (matched / ambiguous / unmatched), an `AuditRecord`, and optionally an `ExceptionRecord`. Bank records consumed by a match are removed from the available pool, preventing double-matching.

| # | Method | When it fires | Confidence |
|---|---|---|---|
| Pre-pass | `batch_amount_reconciliation` | ≥2 source records share a UTR; their sum equals one bank credit | 0.90 |
| 1 | `exact_identifier` | UTR/reference string match after normalisation | 1.00 |
| 2 | `exact_amount_date` | amount equal AND `settlement_date == posted_date` | 0.95 |
| 3 | `financial_reconciliation` | `gross − fee − tax == bank_credit` on same date | 0.92 |
| 4 | `amount_date_tolerance` | amount equal AND \|date diff\| ≤ 3 days | 0.85 |
| 5 | `refund_identifier` | `settlement_id` starts with `ref_`; bank debit matches gross | 0.95 |
| Fallback | `ambiguous` / `duplicate` / `unmatched` | Multiple candidates / duplicate bank IDs / no match | 0.40 / 0.40 / 0.10 |

### `arbitrator.py` — LLM Arbitration Service
Receives only records that left the deterministic engine as `ambiguous`. The LLM provider's raw output is validated against a `LLMArbitrationDecision` Pydantic model before any field on the decision is updated. If validation fails, the original `ambiguous` decision is preserved. The candidate ID returned by the LLM is also checked against the original candidate pool — hallucinated IDs are rejected.

### `reconciliation.py` — Pipeline Orchestrator
The public API surface: `reconcile(source_records, target_records, arbitrator=None)`. Runs the matcher, optionally runs arbitration, and returns a `FinalReconciliationResult`.

### `report.py` — Metric Reporting
Read-only computation over a `FinalReconciliationResult`. Produces `ReconciliationReport` with exact counts and rates. Never mutates decisions or exceptions.

### `qa.py` — Grounded Finance Q&A
A four-stage pipeline:
1. **QuestionInterpreter** — deterministic intent parsing via keyword/regex
2. **DeterministicRetriever** — exact record lookup, no estimation
3. **FactComputer** — assembles `GroundedFactSet` (verified numbers, record IDs)
4. **AnswerGenerator** — if an LLM is wired, the answer is checked: every number > 100 or decimal must appear in `fact_set.numerical_values`; every record ID must be in `fact_set.record_ids`. Fails → fallback to deterministic formatted answer.

### `api_app.py` — FastAPI Adapter
Thin HTTP layer. Manages session state (session_id → reconciliation result). Exposes:
- `POST /api/reconcile` — accepts CSV uploads, runs pipeline, returns full result
- `GET /api/session/{session_id}` — re-fetches an existing session
- `POST /api/qa/ask` — grounded Q&A against a session's result
- `GET /api/health` — liveness probe

### React Dashboard
Vite + React 18 + TypeScript + Tailwind CSS v4. Five views:
- **Executive Overview** — health KPIs, method breakdown chart
- **Decisions Explorer** — filterable transaction table, evidence drawer
- **Exceptions Investigation** — severity grid, structured evidence
- **Audit Trail** — full deterministic audit log per record
- **Finance Q&A** — grounded chat interface with evidence panel

---

## Key Design Principles

**1. Deterministic first, LLM optional.**
The system produces a complete, auditable reconciliation without any LLM. Arbitration is a pluggable opt-in via the `arbitrator` parameter. The current deployment uses no arbitrator, producing fully deterministic results.

**2. Canonical data contract.**
All sources — Razorpay settlements, bank statements, merchant ledger, fourth-source payout export — are normalised into the same `CanonicalTransaction` Pydantic model before any matching logic runs. Adding a new source requires only a new schema mapping; the entire downstream pipeline requires no changes.

**3. Evidence-first decisions.**
Every `ReconciliationDecision` carries an `evidence` dict with the exact fields and values that triggered the match (or ambiguity). Every decision has a corresponding `AuditRecord`.

**4. Hallucination containment.**
The Q&A module's `AnswerGenerator` checks the LLM's answer against the verified `GroundedFactSet` before returning it. Numbers and record IDs that cannot be traced to the reconciliation result cause the system to return the deterministic fallback answer instead.
