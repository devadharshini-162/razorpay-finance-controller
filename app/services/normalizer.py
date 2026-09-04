from typing import List, Dict, Any
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from app.models.canonical import CanonicalTransaction
from app.models.mapping import MappingResult


class Normalizer:
    def _parse_date(self, date_str: str) -> date | None:
        if not date_str or not str(date_str).strip():
            return None

        clean = str(date_str).strip()
        formats = [
            "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y",
            "%b %d %Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(clean, fmt).date()
            except ValueError:
                pass

        raise ValueError(f"Could not parse date: {date_str}")

    def _parse_decimal(self, amount_str: str) -> Decimal | None:
        if not amount_str or not str(amount_str).strip():
            return None

        clean = str(amount_str).strip().replace(',', '')
        clean = clean.replace('₹', '').replace('$', '').strip()

        try:
            return Decimal(clean)
        except InvalidOperation:
            raise ValueError(f"Could not parse monetary amount: {amount_str}")

    def _col_sign(self, col: str) -> int:
        """Return -1 for debit-style columns, +1 for credit-style, 0 for neutral."""
        cl = col.lower()
        if "debit" in cl or cl.endswith(" dr") or cl.startswith("dr "):
            return -1
        if "credit" in cl or cl.endswith(" cr") or cl.startswith("cr "):
            return 1
        return 0

    def normalize(
        self, raw_rows: List[Dict[str, Any]], mapping: MappingResult
    ) -> List[CanonicalTransaction]:
        transactions = []
        for index, row in enumerate(raw_rows):
            kwargs: Dict[str, Any] = {}
            metadata: Dict[str, Any] = {}
            # Accumulator for `amount` — handles the case where a source has
            # separate Credit and Debit columns both mapped to the same canonical
            # field. Credit values are positive, debit values are negative.
            amount_accumulator: Decimal | None = None

            for col, val in row.items():
                if not val:
                    val = None

                if col in mapping.column_mapping:
                    canonical_field = mapping.column_mapping[col]

                    if "amount" in canonical_field or canonical_field in ["fee", "tax", "adjustment"]:
                        parsed = self._parse_decimal(val) if val else None

                        if canonical_field == "amount" and parsed is not None:
                            sign = self._col_sign(col)
                            if sign == -1:
                                parsed = -abs(parsed)
                            elif sign == 1:
                                parsed = abs(parsed)
                            # Sum so Credit and Debit columns don't overwrite each other.
                            amount_accumulator = (amount_accumulator or Decimal("0")) + parsed
                        elif parsed is not None:
                            kwargs[canonical_field] = parsed

                    elif "date" in canonical_field:
                        kwargs[canonical_field] = self._parse_date(val) if val else None
                    else:
                        parsed_str = str(val).strip() if val else None
                        kwargs[canonical_field] = parsed_str if parsed_str else None
                else:
                    metadata[col] = val

            # Commit accumulated amount (if any)
            if amount_accumulator is not None:
                kwargs["amount"] = amount_accumulator

            record_id = f"{mapping.source_name}_{index+1:04d}"

            # transaction_type comes ONLY from an explicitly mapped source column.
            # Never inferred from narration text or source name.
            tx_type = kwargs.pop("transaction_type", "unknown")
            if tx_type not in ["payment", "settlement", "refund", "adjustment", "transfer", "unknown"]:
                tx_type = "unknown"

            tx = CanonicalTransaction(
                record_id=record_id,
                source=mapping.source_name,
                transaction_type=tx_type,
                metadata=metadata,
                **kwargs
            )
            transactions.append(tx)

        return transactions
