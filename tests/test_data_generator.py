import os
import csv
import subprocess

def test_data_generation_execution():
    # Run the generator script
    subprocess.run(["python3", "scripts/generate_data.py"], check=True)
    
    # Verify files exist
    assert os.path.exists("data/raw/razorpay_settlements.csv")
    assert os.path.exists("data/raw/bank_statement.csv")
    assert os.path.exists("data/raw/merchant_ledger.csv")
    assert os.path.exists("data/raw/no_ledger/razorpay_settlements.csv")
    assert os.path.exists("data/raw/no_ledger/bank_statement.csv")
    assert os.path.exists("data/processed/reconciliation_ground_truth.csv")
    
    # Verify counts
    with open("data/processed/reconciliation_ground_truth.csv", "r") as f:
        reader = csv.DictReader(f)
        gt = list(reader)
        
    assert len(gt) >= 60
    
    # Collect relationship metrics to verify cases
    rels = [row["expected_relationship"] for row in gt]
    
    assert "exact_match" in rels
    assert "amount_date_match" in rels
    assert "fee_tax_split" in rels
    assert "date_mismatch" in rels
    assert "missing_bank_record" in rels
    assert "missing_razorpay_record" in rels
    assert "duplicate" in rels
    assert "batched_settlement" in rels
    assert "refund" in rels
    assert "ambiguous_1" in rels
    
    # Verify no deterministic bleed (ground truth ID in banks)
    # The GT file shouldn't be exposed
    with open("data/raw/bank_statement.csv", "r") as f:
        content = f.read()
        assert "expected_relationship" not in content
        assert "logical_transaction_id" not in content

def test_deterministic_output():
    # Calling it twice should not change the outputs if we read them
    subprocess.run(["python3", "scripts/generate_data.py"], check=True)
    with open("data/processed/reconciliation_ground_truth.csv", "r") as f:
        run1 = f.read()
        
    subprocess.run(["python3", "scripts/generate_data.py"], check=True)
    with open("data/processed/reconciliation_ground_truth.csv", "r") as f:
        run2 = f.read()
        
    assert run1 == run2

def test_data_fields_exist():
    # Verify fieldnames exist conceptually
    
    with open("data/raw/razorpay_settlements.csv", "r") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        assert "Settlement Ref" in fields
        assert "Settled Amount" in fields
        
    with open("data/raw/bank_statement.csv", "r") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        assert "Txn Date" in fields
        assert "Narration" in fields
        assert "Credit" in fields
        
    with open("data/raw/merchant_ledger.csv", "r") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        assert "Invoice No" in fields
        assert "Amount Received" in fields
from datetime import datetime
from decimal import Decimal

def parse_date(date_str):
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%b %d %Y"]:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass
    return None

def test_data_properties():
    # Make sure we have the latest run
    subprocess.run(["python3", "scripts/generate_data.py"], check=True)
    
    with open("data/raw/razorpay_settlements.csv", "r") as f:
        rzp = list(csv.DictReader(f))
    with open("data/raw/bank_statement.csv", "r") as f:
        bank = list(csv.DictReader(f))
    with open("data/processed/reconciliation_ground_truth.csv", "r") as f:
        gt = list(csv.DictReader(f))
        
    rzp_map = {r['Settlement Ref']: r for r in rzp}
    bank_map = {r['Txn ID']: r for r in bank}
    
    tested_case_b = False
    tested_case_d = False
    tested_case_c = False
    tested_case_h = False
    tested_case_j = False
    tested_case_g = False
    
    for row in gt:
        rel = row['expected_relationship']
        r_ids = row['razorpay_record_id'].split('|') if row['razorpay_record_id'] else []
        b_ids = row['bank_record_id'].split('|') if row['bank_record_id'] else []
        
        rzp_recs = [rzp_map[rid] for rid in r_ids if rid in rzp_map]
        bank_recs = [bank_map[bid] for bid in b_ids if bid in bank_map]
        
        if rel == 'amount_date_match' and rzp_recs and bank_recs:
            r = rzp_recs[0]
            b = bank_recs[0]
            assert Decimal(r['Settled Amount']) == Decimal(b['Credit'])
            assert parse_date(r['Settlement Date']) == parse_date(b['Txn Date'])
            utr = r['UTR'].strip().lower()
            utr_clean = utr.replace("utr-", "").replace("utr ", "").replace("utr", "")
            narr = b['Narration'].lower()
            ref = b['Bank Ref'].lower()
            assert utr_clean not in narr, f"Found {utr_clean} in {narr}"
            assert utr_clean not in ref
            tested_case_b = True
            
        elif rel == 'date_mismatch' and rzp_recs and bank_recs:
            r = rzp_recs[0]
            b = bank_recs[0]
            r_date = parse_date(r['Settlement Date'])
            b_date = parse_date(b['Txn Date'])
            assert r_date != b_date
            diff = abs((b_date - r_date).days)
            assert 1 <= diff <= 3
            tested_case_d = True
            
        elif rel == 'fee_tax_split' and rzp_recs and len(bank_recs) == 2:
            r = rzp_recs[0]
            gross = Decimal(r['Gross'])
            fee = Decimal(r['Processing Fee'])
            tax = Decimal(r['GST'])
            
            b1, b2 = bank_recs
            b_credit = b1 if b1['Credit'] else b2
            b_debit = b2 if b2['Debit'] else b1
            
            assert Decimal(b_credit['Credit']) == gross
            assert Decimal(b_debit['Debit']) == (fee + tax)
            tested_case_c = True
            
        elif rel == 'batched_settlement' and len(rzp_recs) == 3 and bank_recs:
            b = bank_recs[0]
            sum_settled = sum(Decimal(r['Settled Amount']) for r in rzp_recs)
            assert sum_settled == Decimal(b['Credit'])
            tested_case_h = True
            
        elif 'ambiguous' in rel and rzp_recs and bank_recs:
            r = rzp_recs[0]
            b = bank_recs[0]
            utr = r['UTR'].strip().lower()
            utr_clean = utr.replace("utr-", "").replace("utr ", "").replace("utr", "")
            narr = b['Narration'].lower()
            ref = b['Bank Ref'].lower()
            
            assert utr_clean not in narr, f"Found {utr_clean} in {narr}"
            assert utr_clean not in ref
            assert Decimal(r['Settled Amount']) == Decimal(b['Credit'])
            assert parse_date(r['Settlement Date']) == parse_date(b['Txn Date'])
            tested_case_j = True
            
        elif rel == 'duplicate' and rzp_recs and len(bank_recs) == 2:
            b1, b2 = bank_recs
            assert parse_date(b1['Txn Date']) == parse_date(b2['Txn Date'])
            assert b1['Credit'] == b2['Credit']
            assert b1['Txn ID'] != b2['Txn ID']
            tested_case_g = True
            
    assert tested_case_b
    assert tested_case_d
    assert tested_case_c
    assert tested_case_h
    assert tested_case_j
    assert tested_case_g
