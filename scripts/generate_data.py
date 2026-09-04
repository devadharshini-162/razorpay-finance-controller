import csv
import random
from datetime import datetime, timedelta
from decimal import Decimal
import os

SEED = 42
random.seed(SEED)

def rand_decimal(min_val, max_val):
    return Decimal(str(round(random.uniform(min_val, max_val), 2)))

def format_date_messy(dt):
    choice = random.choice([1, 2, 3, 4])
    if choice == 1:
        return dt.strftime("%Y-%m-%d")
    elif choice == 2:
        return dt.strftime("%d/%m/%Y")
    elif choice == 3:
        return dt.strftime("%d-%m-%Y")
    else:
        return dt.strftime("%b %d %Y")

def get_messy_ref(ref):
    choice = random.choice([1, 2, 3, 4])
    if choice == 1:
        return ref
    elif choice == 2:
        return f"UTR-{ref[3:]}"
    elif choice == 3:
        return ref.lower()
    else:
        return f"UTR {ref[3:]}"

def get_messy_narration(ref):
    choice = random.choice([1, 2, 3, 4])
    if choice == 1:
        return f"RAZORPAY SETTLEMENT {ref}"
    elif choice == 2:
        return f"Razorpay Settlement {ref}"
    elif choice == 3:
        return f"RZP SETTLEMENT {ref}"
    else:
        return f"RAZORPAY PAYOUT REF{ref[3:]}"

razorpay_records = []
bank_records = []
ledger_records = []
ground_truth = []
balance = Decimal("100000.00")

def add_ground_truth(logical_id, rzp_id, bank_id, ledg_id, rel):
    ground_truth.append({
        "logical_transaction_id": logical_id,
        "razorpay_record_id": rzp_id or "",
        "bank_record_id": bank_id or "",
        "ledger_record_id": ledg_id or "",
        "expected_relationship": rel
    })

def generate_base_transaction(logical_id, amount_base, date_base, type_name):
    gross = amount_base
    fee = rand_decimal(1, float(gross) * 0.05) if type_name != "refund" else Decimal("0.00")
    tax = round(fee * Decimal("0.18"), 2) if type_name != "refund" else Decimal("0.00")
    settlement = gross - fee - tax if type_name != "refund" else gross
    
    ref_num = f"{random.randint(100000, 999999)}"
    utr = f"UTR{ref_num}"
    
    return {
        "logical_id": logical_id,
        "gross": gross,
        "fee": fee,
        "tax": tax,
        "settlement": settlement,
        "date": date_base,
        "utr": utr,
        "ref_num": ref_num,
        "type": type_name
    }

def add_razorpay(data, is_refund=False):
    rzp_id = f"set_{data['ref_num']}"
    if is_refund:
        rzp_id = f"ref_{data['ref_num']}"
    
    record = {
        "Settlement Ref": rzp_id,
        "Order Reference": f"order_{data['ref_num']}",
        "Gross": str(data['gross']),
        "Processing Fee": str(data['fee']),
        "GST": str(data['tax']),
        "Settled Amount": str(data['settlement']),
        "Settlement Date": format_date_messy(data['date']) if random.random() < 0.3 else data['date'].strftime("%Y-%m-%d"),
        "UTR": get_messy_ref(data['utr']) if random.random() < 0.3 else data['utr']
    }
    razorpay_records.append(record)
    return rzp_id

def add_bank(data, credit_amount, desc=None, is_debit=False, out_of_order_date=None, utr=None):
    global balance
    bank_id = f"txn_{random.randint(10000,99999)}"
    if is_debit:
        balance -= credit_amount
        credit_val = ""
        debit_val = str(credit_amount)
    else:
        balance += credit_amount
        credit_val = str(credit_amount)
        debit_val = ""
        
    date_to_use = out_of_order_date or data['date']
    narration_utr = utr if utr is not None else data['utr']
    
    if desc is not None:
        narration = desc
    else:
        narration = get_messy_narration(narration_utr) if random.random() < 0.3 else f"RAZORPAY SETTLEMENT {narration_utr}"
        if is_debit:
            narration = f"RAZORPAY REFUND {narration_utr}"
        
    record = {
        "Txn ID": bank_id,
        "Txn Date": format_date_messy(date_to_use) if random.random() < 0.3 else date_to_use.strftime("%Y-%m-%d"),
        "Narration": narration,
        "Credit": credit_val,
        "Debit": debit_val,
        "Bank Ref": narration_utr if narration_utr and random.random() < 0.8 else "",
        "Running Balance": str(balance)
    }
    bank_records.append(record)
    return bank_id

def add_ledger(data, amount, desc=None, missing_id=False, messy_desc=False):
    ledg_id = f"inv_{data['ref_num']}"
    
    customer = f"Customer {data['ref_num']}"
    if messy_desc:
        desc_val = desc or f"Payment for {ledg_id} - some notes"
    else:
        desc_val = desc or f"Payment for {ledg_id}"
        
    record = {
        "Invoice No": "" if missing_id else ledg_id,
        "Paid On": format_date_messy(data['date']) if random.random() < 0.3 else data['date'].strftime("%Y-%m-%d"),
        "Customer": customer,
        "Amount Received": str(amount),
        "Remarks": desc_val
    }
    ledger_records.append(record)
    return ledg_id if not missing_id else ""

def generate_data():
    global razorpay_records, bank_records, ledger_records, ground_truth, balance
    razorpay_records = []
    bank_records = []
    ledger_records = []
    ground_truth = []
    balance = Decimal("100000.00")
    random.seed(SEED)
    
    start_date = datetime(2026, 9, 1)

    # Case A: Exact Match (~20)
    for i in range(20):
        l_id = f"L_A_{i}"
        dt = start_date + timedelta(days=random.randint(0, 10))
        d = generate_base_transaction(l_id, rand_decimal(100, 5000), dt, "payment")
        r_id = add_razorpay(d)
        b_id = add_bank(d, d['settlement'])
        bank_records[-1]['Bank Ref'] = d['utr']  # Force intended identifier
        l_id_rec = add_ledger(d, d['gross']) if random.random() > 0.2 else None
        add_ground_truth(l_id, r_id, b_id, l_id_rec, "exact_match")

    # Case B: Amount + date match (~10)
    for i in range(10):
        l_id = f"L_B_{i}"
        dt = start_date + timedelta(days=random.randint(0, 10))
        d = generate_base_transaction(l_id, rand_decimal(100, 5000), dt, "payment")
        r_id = add_razorpay(d)
        b_id = add_bank(d, d['settlement'], desc=f"NEFT TRANSFER {random.randint(100,999)}", utr="")
        l_id_rec = add_ledger(d, d['gross'], missing_id=True, messy_desc=True)
        add_ground_truth(l_id, r_id, b_id, l_id_rec, "amount_date_match")

    # Case C: Fee/tax deduction (~10)
    for i in range(10):
        l_id = f"L_C_{i}"
        dt = start_date + timedelta(days=random.randint(0, 10))
        d = generate_base_transaction(l_id, rand_decimal(100, 5000), dt, "payment")
        d['settlement'] = d['gross']
        r_id = add_razorpay(d)
        b_id1 = add_bank(d, d['gross'], desc=f"RAZORPAY SETTLEMENT {d['utr']}")
        b_id2 = add_bank(d, d['fee'] + d['tax'], desc=f"RAZORPAY FEE {d['utr']}", is_debit=True)
        l_id_rec = add_ledger(d, d['gross'])
        # The bank represents the gross settlement as a credit and fee+tax as a separate debit, so reconciliation must combine related bank entries.
        add_ground_truth(l_id, r_id, f"{b_id1}|{b_id2}", l_id_rec, "fee_tax_split")

    # Case D: Date mismatch (~10)
    for i in range(10):
        l_id = f"L_D_{i}"
        dt = start_date + timedelta(days=random.randint(0, 10))
        dt_bank = dt + timedelta(days=random.randint(1, 3))
        d = generate_base_transaction(l_id, rand_decimal(100, 5000), dt, "payment")
        r_id = add_razorpay(d)
        b_id = add_bank(d, d['settlement'], out_of_order_date=dt_bank)
        l_id_rec = add_ledger(d, d['gross'])
        add_ground_truth(l_id, r_id, b_id, l_id_rec, "date_mismatch")

    # Case E: Missing bank record (~3)
    for i in range(3):
        l_id = f"L_E_{i}"
        dt = start_date + timedelta(days=random.randint(0, 10))
        d = generate_base_transaction(l_id, rand_decimal(100, 5000), dt, "payment")
        r_id = add_razorpay(d)
        l_id_rec = add_ledger(d, d['gross'])
        add_ground_truth(l_id, r_id, None, l_id_rec, "missing_bank_record")

    # Case F: Missing Razorpay record (~3)
    for i in range(3):
        l_id = f"L_F_{i}"
        dt = start_date + timedelta(days=random.randint(0, 10))
        d = generate_base_transaction(l_id, rand_decimal(100, 5000), dt, "payment")
        b_id = add_bank(d, d['settlement'], desc=f"MISC TRANSFER {d['utr']}")
        l_id_rec = add_ledger(d, d['gross'])
        add_ground_truth(l_id, None, b_id, l_id_rec, "missing_razorpay_record")

    # Case G: Duplicate (~3)
    for i in range(3):
        l_id = f"L_G_{i}"
        dt = start_date + timedelta(days=random.randint(0, 10))
        d = generate_base_transaction(l_id, rand_decimal(100, 5000), dt, "payment")
        r_id = add_razorpay(d)
        b_id1 = add_bank(d, d['settlement'])
        b_id2 = add_bank(d, d['settlement'])
        l_id_rec = add_ledger(d, d['gross'])
        l_id_rec2 = add_ledger(d, d['gross'])
        add_ground_truth(l_id, r_id, f"{b_id1}|{b_id2}", f"{l_id_rec}|{l_id_rec2}", "duplicate")

    # Case H: Batched settlement (~3)
    for i in range(3):
        l_id = f"L_H_{i}"
        dt = start_date + timedelta(days=random.randint(0, 10))
        d1 = generate_base_transaction(f"{l_id}_1", rand_decimal(100, 2000), dt, "payment")
        d2 = generate_base_transaction(f"{l_id}_2", rand_decimal(100, 2000), dt, "payment")
        d3 = generate_base_transaction(f"{l_id}_3", rand_decimal(100, 2000), dt, "payment")
        
        batch_utr = f"UTR_BATCH_{i}"
        d1['utr'] = d2['utr'] = d3['utr'] = batch_utr
        r_id1 = add_razorpay(d1)
        r_id2 = add_razorpay(d2)
        r_id3 = add_razorpay(d3)
        batch_settlement = d1['settlement'] + d2['settlement'] + d3['settlement']
        b_id = add_bank(d1, batch_settlement, desc=f"RAZORPAY BATCH {batch_utr}", utr=batch_utr)
        bank_records[-1]['Bank Ref'] = batch_utr  # Force intended batch identifier
        add_ground_truth(l_id, f"{r_id1}|{r_id2}|{r_id3}", b_id, None, "batched_settlement")

    # Case I: Refund (~6)
    for i in range(6):
        l_id = f"L_I_{i}"
        dt = start_date + timedelta(days=random.randint(0, 10))
        d = generate_base_transaction(l_id, rand_decimal(50, 1000), dt, "refund")
        r_id = add_razorpay(d, is_refund=True)
        b_id = add_bank(d, d['gross'], is_debit=True)
        l_id_rec = add_ledger(d, d['gross'], desc=f"Refund for Customer {d['ref_num']}")
        add_ground_truth(l_id, r_id, b_id, l_id_rec, "refund")

    # Case J: Ambiguous records (~5)
    for i in range(5):
        l_id = f"L_J_{i}"
        dt = start_date + timedelta(days=random.randint(0, 10))
        d1 = generate_base_transaction(f"{l_id}_1", Decimal("1000.00"), dt, "payment")
        d2 = generate_base_transaction(f"{l_id}_2", Decimal("1000.00"), dt, "payment")
        
        for d in (d1, d2):
            d["fee"] = Decimal("0.00")
            d["tax"] = Decimal("0.00")
            d["settlement"] = d["gross"]

        r_id1 = add_razorpay(d1)
        r_id2 = add_razorpay(d2)
        b_id1 = add_bank(d1, d1['settlement'], desc="TRANSFER", utr="")
        b_id2 = add_bank(d2, d2['settlement'], desc="TRANSFER", utr="")
        add_ground_truth(f"{l_id}_1", r_id1, b_id1, None, "ambiguous_1")
        add_ground_truth(f"{l_id}_2", r_id2, b_id2, None, "ambiguous_2")


fourth_source_records = []

def generate_fourth_source_data():
    for i in range(1, 16):
        payout_id = f"PO-{800000 + i}"
        gross = Decimal(f"{1000 * i}.00")
        fee = Decimal(f"{18 * i}.00")
        tax = Decimal(f"{3.24 * i:.2f}")
        net = gross - fee - tax
        
        ext_ref = f"UTR{700000 + i}"
        if i <= len(razorpay_records) and razorpay_records[i-1].get("UTR"):
            ext_ref = razorpay_records[i-1]["UTR"]

        record = {
            "Payout No": payout_id,
            "Created At": f"2026-09-01 10:{i:02d}:00",
            "Effective Date": "2026-09-01",
            "Gross Sales": str(gross),
            "Processing Charges": str(fee),
            "GST": str(tax),
            "Net Payout": str(net),
            "External Ref": ext_ref,
            "Beneficiary": f"Merchant Store {i}",
            "Narrative": f"Merchant payout {payout_id}",
            "Payout Channel": "NEFT-FAST" if i % 2 == 0 else "IMPS"
        }
        fourth_source_records.append(record)

def save_csv(path, fieldnames, data):
    # Ensure dir exists
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)

if __name__ == "__main__":
    generate_data()
    generate_fourth_source_data()
    
    rzp_fields = ["Settlement Ref", "Order Reference", "Gross", "Processing Fee", "GST", "Settled Amount", "Settlement Date", "UTR"]
    bank_fields = ["Txn ID", "Txn Date", "Narration", "Credit", "Debit", "Bank Ref", "Running Balance"]
    ledg_fields = ["Invoice No", "Paid On", "Customer", "Amount Received", "Remarks"]
    gt_fields = ["logical_transaction_id", "razorpay_record_id", "bank_record_id", "ledger_record_id", "expected_relationship"]
    fourth_fields = ["Payout No", "Created At", "Effective Date", "Gross Sales", "Processing Charges", "GST", "Net Payout", "External Ref", "Beneficiary", "Narrative", "Payout Channel"]

    save_csv("data/raw/razorpay_settlements.csv", rzp_fields, razorpay_records)
    save_csv("data/raw/bank_statement.csv", bank_fields, bank_records)
    save_csv("data/raw/merchant_ledger.csv", ledg_fields, ledger_records)
    save_csv("data/raw/fourth_source.csv", fourth_fields, fourth_source_records)
    
    save_csv("data/raw/no_ledger/razorpay_settlements.csv", rzp_fields, razorpay_records)
    save_csv("data/raw/no_ledger/bank_statement.csv", bank_fields, bank_records)
    
    save_csv("data/processed/reconciliation_ground_truth.csv", gt_fields, ground_truth)
    
    print(f"Generated {len(ground_truth)} logical transactions and {len(fourth_source_records)} fourth-source records.")
