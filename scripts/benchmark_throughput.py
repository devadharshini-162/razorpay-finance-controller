import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ui_app import run_pipeline
from app.services.schema_mapper import SchemaMapper, MockLLMProvider
from app.services.normalizer import Normalizer
from app.services.reconciliation import reconcile
import csv
import io

def parse_uploaded_csv(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    reader = csv.DictReader(io.StringIO(content))
    return list(reader), reader.fieldnames

def benchmark_throughput():
    print("==================================================")
    print("THROUGHPUT EVALUATION: Deterministic reconciliation-core throughput")
    print("==================================================")
    
    # Pre-load and normalize data to isolate the reconciliation core.
    mapper = SchemaMapper(MockLLMProvider())
    normalizer = Normalizer()
    
    rzp_rows, rzp_cols = parse_uploaded_csv('data/raw/razorpay_settlements.csv')
    bank_rows, bank_cols = parse_uploaded_csv('data/raw/bank_statement.csv')
    
    rzp_mapping = mapper.map_source("razorpay", rzp_cols, rzp_rows[:5])
    source_records = normalizer.normalize(rzp_rows, rzp_mapping)
    
    bank_mapping = mapper.map_source("bank", bank_cols, bank_rows[:5])
    target_records = normalizer.normalize(bank_rows, bank_mapping)
    
    iterations = 1000
    print("Boundary: reconcile(source_records, target_records)")
    print("Excluding: CSV I/O, data generation, application startup, UI rendering")
    print(f"Source records: {len(source_records)}")
    print(f"Target records: {len(target_records)}")
    print(f"Iterations: {iterations}")
    
    start_time = time.perf_counter()
    
    for _ in range(iterations):
        result = reconcile(source_records, target_records)
        
    end_time = time.perf_counter()
    
    total_time = end_time - start_time
    avg_reconciliation_time = total_time / iterations
    records_processed_per_run = len(source_records)
    total_records_processed = records_processed_per_run * iterations
    records_per_second = records_processed_per_run / avg_reconciliation_time
    
    print(f"Total benchmark time: {total_time:.4f} seconds")
    print(f"Average reconciliation time: {avg_reconciliation_time * 1000:.4f} ms")
    print(f"Total records processed (iterated): {total_records_processed}")
    print(f"Records/second: {records_per_second:.2f}")

if __name__ == "__main__":
    benchmark_throughput()
