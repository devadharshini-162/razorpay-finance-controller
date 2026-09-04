# Razorpay AI Finance Controller: Buildathon Evaluation

## 1. Frozen Baseline Verification

The M11 baseline rules remain completely untouched and verified by the pytest suite execution:

* **Total source records:** 81
* **Deterministic matches:** 65
* **LLM-resolved matches:** 0
* **Ambiguous records:** 13
* **Unmatched records:** 3
* **Resolution rate:** 80.25%
* **Total exceptions:** 16 (6 high severity, 10 `ambiguous_match`, 3 `duplicate`, 3 `missing_record`)
* **Audit records:** 81
* **Test Suite:** 160 tests passed (0 failures)

## 2. Accuracy Evaluation

The accuracy benchmark evaluates the actual deterministic reconciliation decisions against the `reconciliation_ground_truth.csv`.

**Methodology & Definitions:**
* **Precision:** True Positives (Correct Matches) / (True Positives + False Positives (Incorrect Matches))
* **Recall:** True Positives / (True Positives + False Negatives (Expected Matches Missed))
* **F1:** Harmonic mean of Precision and Recall
* A decision is a **Correct Match** if the `matched` system decision links the exact IDs matching the ground truth file expected relationship.
* A decision is **Correctly Unresolved** if the ground truth expects no deterministic solution (e.g. true duplicates, explicitly missing records) and the system appropriately returns `ambiguous` or `unmatched`.

**Actual Measured Accuracy Results:**
* Total evaluated source records: 81
* Correct matches: 65
* Incorrect matches: 0
* Expected matches missed: 0
* Correctly unresolved: 16
* Incorrectly unresolved: 0

* **Precision:** 1.0000 (100%)
* **Recall:** 1.0000 (100%)
* **F1 Score:**  1.0000 (100%)

> **Distinction Note:** *Resolution Rate* (80.25%) measures how many records the system felt confident matching automatically. *Accuracy* (100%) measures whether the decisions it *did* make (both to match and to abstain/mark ambiguous) were correct.

## 3. Throughput Evaluation

This metric isolates the core algorithmic matching engine (`app.services.reconciliation.reconcile`) from UI rendering, networking, parsing, and data generation overhead.

**Methodology:**
* Target boundary: `reconcile(source_records, target_records)` executed in memory natively via Python.
* Uses the exact 81 Razorpay records and 88 Bank records.
* Uses `time.perf_counter` averaged across exactly 1,000 iterations to measure raw throughput limits of the core logic processing rules.

**Actual Measured Throughput Result:**
* **Total iterations:** 1,000
* **Avg reconciliation time:** ~1.2945 ms (for the full dataset)
* **Algorithmic Throughput (Records/Second):** **~62,571 records per second**

> **Distinction Note:** This is algorithmic *Reconciliation-Core Throughput*. It proves the extreme speed of a deterministic-first engine. It is NOT end-to-end application throughput (which involves network calls to Vite/FastAPI).

## 4. Limitations of Synthetic-Data Evaluation

While the system achieves perfect P/R on the synthetic dataset (by design of the deterministic rules exactly covering the generated scenarios), real-world Razorpay and bank dumps may introduce edge cases (like trailing whitespace, Unicode discrepancies, mismatched timezone timestamps, undocumented row formats) not perfectly represented in the synthetic data generator. The schema mapping (and optional LLM arbitration) is built exactly to handle these future edge cases.
