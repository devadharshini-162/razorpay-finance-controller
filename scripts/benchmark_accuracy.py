import sys
import os
import csv
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ui_app import run_pipeline

class MemFile:
    def __init__(self, path):
        with open(path, 'rb') as f:
            self._data = f.read()
    def read(self):
        return self._data

def load_ground_truth(path):
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

def evaluate_accuracy():
    print("==================================================")
    print("ACCURACY EVALUATION: Razorpay AI Finance Controller")
    print("==================================================")
    
    # 1. Run pipeline to get actual deterministic results
    razorpay_file = MemFile('data/raw/razorpay_settlements.csv')
    bank_file = MemFile('data/raw/bank_statement.csv')
    
    res = run_pipeline(razorpay_file=razorpay_file, bank_file=bank_file)
    decisions = res['result'].decisions
    
    # Map canonical record_id back to actual ground truth identifiers
    source_map = {r.record_id: r.settlement_id for r in res['source_records']}
    target_map = {r.record_id: r.transaction_id for r in res['target_records']}
    
    decision_map = {source_map.get(d.source_record_id, d.source_record_id): d for d in decisions}
    
    # 2. Load ground truth
    ground_truth = load_ground_truth('data/processed/reconciliation_ground_truth.csv')
    
    # We will expand ground truth so each razorpay_record_id has an entry
    gt_map = {}
    for row in ground_truth:
        rzp_ids = row['razorpay_record_id'].split('|') if row['razorpay_record_id'] else []
        for r_id in rzp_ids:
            if r_id:
                gt_map[r_id] = row
                
    # 3. Categorize
    correct_matches = 0
    incorrect_matches = 0
    expected_matches_missed = 0
    correctly_unresolved = 0
    incorrectly_unresolved = 0
    
    EXPECTED_MATCH_RELS = {
        "exact_match", "amount_date_match", "fee_tax_split", 
        "date_mismatch", "batched_settlement", "refund"
    }
    
    EXPECTED_UNRESOLVED_RELS = {
        "missing_bank_record", "ambiguous_1", "ambiguous_2", "duplicate"
    }
    
    evaluated_source_records = 0
    excluded_records = 0
    
    missing_razorpay_gt = [row for row in ground_truth if not row['razorpay_record_id']]
    # Ground truth without a Razorpay id is when a bank record exists but Razorpay doesn't (missing_razorpay_record).
    # Since we evaluate by iterating Razorpay source records, we ignore those implicitly unless we evaluate target coverage.
    
    for r_id, decision in decision_map.items():
        evaluated_source_records += 1
        gt_row = gt_map.get(r_id)
        
        if not gt_row:
            excluded_records += 1
            print(f"Warning: {r_id} not in ground truth.")
            continue
            
        rel = gt_row['expected_relationship']
        is_expected_match = rel in EXPECTED_MATCH_RELS
        is_expected_unresolved = rel in EXPECTED_UNRESOLVED_RELS
        
        valid_bank_ids = set(gt_row['bank_record_id'].split('|')) if gt_row['bank_record_id'] else set()
        
        system_matched = decision.decision == "matched"
        # map system matched target record IDs to actual bank IDs
        system_target_ids = {target_map.get(decision.candidate_record_id, decision.candidate_record_id)} if decision.candidate_record_id else set()
        
        if system_matched:
            # Did the system match correctly?
            # For our rules, as long as the system target is within the valid targets, it's correct.
            is_correct_target = system_target_ids.issubset(valid_bank_ids) and len(system_target_ids) > 0
            
            if is_expected_match and is_correct_target:
                correct_matches += 1
            elif not is_expected_match and is_correct_target:
                # Should not happen typically, but if it matched a valid bank id when it shouldn't 
                # (e.g. duplicate), it's still incorrect match
                incorrect_matches += 1
            else:
                incorrect_matches += 1
        else: # System unresolved (ambiguous, unmatched)
            if is_expected_match:
                expected_matches_missed += 1
            else:
                correctly_unresolved += 1
                
    total_evaluated = correct_matches + incorrect_matches + expected_matches_missed + correctly_unresolved + incorrectly_unresolved
    
    # Calculate Precision, Recall, F1 for "Match" classification
    # True Positive (TP) = correct_matches
    # False Positive (FP) = incorrect_matches
    # False Negative (FN) = expected_matches_missed
    # True Negative (TN) = correctly_unresolved
    
    tp = correct_matches
    fp = incorrect_matches
    fn = expected_matches_missed
    tn = correctly_unresolved
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    print(f"Total evaluated source records: {evaluated_source_records}")
    print(f"Correct matches: {correct_matches}")
    print(f"Incorrect matches: {incorrect_matches}")
    print(f"Expected matches missed: {expected_matches_missed}")
    print(f"Correctly unresolved: {correctly_unresolved}")
    print(f"Incorrectly unresolved: {incorrectly_unresolved}")
    print("")
    print("Exact Definitions Used:")
    print("Precision: True Positives (Correct Matches) / (True Positives + False Positives (Incorrect Matches))")
    print("Recall: True Positives / (True Positives + False Negatives (Expected Matches Missed))")
    print("F1: Harmonic mean of Precision and Recall")
    print("")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1 Score:  {f1:.4f}")

if __name__ == "__main__":
    evaluate_accuracy()
