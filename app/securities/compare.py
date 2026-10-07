"""Cross-check TreasuryDirect's auction records against Fiscal Data's (docs/phase-3.md, step 5).

TD-SECURITIES (TreasuryDirect's securities API) and FD-AUCTIONS (Fiscal
Data's Treasury Securities Auctions Data) publish the same auctions under the
same key (CUSIP/issue date), TreasuryDirect in camelCase and Fiscal Data in
snake_case with some names shortened. secmaster-svc builds the securities from
TreasuryDirect's; this says where the two disagree.

For every auction either source currently lists:

- **only in one source:** listed by one and not the other;
- for every field both publish, after normalizing what's only presentation (a
  date with or without "T00:00:00", "" and Fiscal Data's "null" both empty,
  numbers compared as decimals so "4.250000" equals "4.25", text without case):
  - **one side empty:** one has a value, the other none;
  - **different:** both have values, and they differ.

The result is kept (`record_comparison`, the latest per pair) for the metrics
and the job's answer: counts per field, and a few examples of each.

Month by month (both sources file an auction under the month of its auction
date), so only a month's records are in memory at once: all 22,000 at once
got mkt-data OOM-killed at its 256 MB limit (2026-10-07). A record one source
files under another month than the other is matched at the end.
"""

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Record, RecordComparison, Source

LEFT, RIGHT = "TD-SECURITIES", "FD-AUCTIONS"
RECORD_TYPE = "auction"
EXAMPLES_PER_FIELD = 5

# Fiscal Data's names where they aren't TreasuryDirect's in snake_case.
ALIASES = {
    "accrued_interest_per100": "accrued_int_per100",
    "accrued_interest_per1000": "accrued_int_per1000",
    "adjusted_accrued_interest_per1000": "adj_accrued_int_per1000",
    "adjusted_price": "adj_price",
    "allocation_percentage": "allocation_pctage",
    "allocation_percentage_decimals": "allocation_pctage_decimals",
    "announced_cusip": "announcemtd_cusip",
    "announcement_date": "announcemt_date",
    "average_median_discount_margin": "avg_med_discnt_margin",
    "average_median_discount_rate": "avg_med_discnt_rate",
    "average_median_investment_rate": "avg_med_investment_rate",
    "average_median_price": "avg_med_price",
    "average_median_yield": "avg_med_yield",
    "cash_management_bill_c_m_b": "cash_management_bill_cmb",
    "competitive_accepted": "comp_accepted",
    "competitive_bid_decimals": "comp_bid_decimals",
    "competitive_tendered": "comp_tendered",
    "competitive_tenders_accepted": "comp_tenders_accepted",
    "estimated_amount_of_publicly_held_maturing_securities_by_type": "est_pub_held_mat_by_type_amt",
    "fima_noncompetitive_accepted": "fima_noncomp_accepted",
    "fima_noncompetitive_tendered": "fima_noncomp_tendered",
    "first_interest_payment_date": "first_int_payment_date",
    "first_interest_period": "first_int_period",
    "high_discount_margin": "high_discnt_margin",
    "high_discount_rate": "high_discnt_rate",
    "interest_payment_frequency": "int_payment_frequency",
    "interest_rate": "int_rate",
    "low_discount_margin": "low_discnt_margin",
    "low_discount_rate": "low_discnt_rate",
    "maturing_date": "mat_date",
    "maximum_competitive_award": "max_comp_award",
    "maximum_noncompetitive_award": "max_noncomp_award",
    "maximum_single_bid": "max_single_bid",
    "minimum_bid_amount": "min_bid_amt",
    "minimum_strip_amount": "min_strip_amt",
    "minimum_to_issue": "min_to_issue",
    "nlp_exclusion_amount": "nlp_exclusion_amt",
    "noncompetitive_accepted": "noncomp_accepted",
    "noncompetitive_tenders_accepted": "noncomp_tenders_accepted",
    "offering_amount": "offering_amt",
    "standard_interest_payment_per1000": "std_int_payment_per1000",
    "tint_cusip1": "tint_cusip_1",
    "tint_cusip2": "tint_cusip_2",
    "treasury_retail_accepted": "treas_retail_accepted",
    "treasury_retail_tenders_accepted": "treas_retail_tenders_accepted",
    "unadjusted_accrued_interest_per1000": "unadj_accrued_int_per1000",
    "unadjusted_price": "unadj_price",
}
# Fields that are about the page, not the auction: not compared.
SKIP = re.compile(r"^(pdf_|xml_|closing_time|updated_timestamp$|record_date$)")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(T00:00:00(\.0+)?Z?)?$")
_EMPTY = {"", "null", "none"}
_TRUE, _FALSE = {"yes", "true", "y"}, {"no", "false", "n"}


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def norm(value) -> object:
    """A field's value without its presentation: None for empty, a date, a decimal, yes/no or case-folded text."""
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in _EMPTY:
        return None
    if _DATE.match(s):
        return s[:10]
    try:
        return Decimal(s.replace(",", "")).normalize()
    except InvalidOperation:
        pass
    low = s.casefold()
    if low in _TRUE:
        return "yes"
    if low in _FALSE:
        return "no"
    return " ".join(low.split())


def field_pairs(left_names, right_names) -> list[tuple[str, str]]:
    """(TreasuryDirect name, Fiscal Data name) for every field both publish, by snake_case or alias."""
    right = set(right_names)
    out = []
    for name in sorted(set(left_names)):
        sn = snake(name)
        other = ALIASES.get(sn, sn)
        if other in right and not SKIP.match(sn):
            out.append((name, other))
    return out


class Tally:
    """The comparison, built up a batch of records at a time."""

    def __init__(self):
        self.compared = 0
        self.records_differing = 0
        self.fields: dict[str, dict] = {}
        self.names: set[str] = set()
        self.pending_left: dict[str, dict] = {}  # keys not (yet) found in the other source
        self.pending_right: dict[str, dict] = {}

    def add(self, left: dict[str, dict], right: dict[str, dict]) -> None:
        """One batch (a month) of records by key on each side; a key on one side only waits for the other."""
        for key in sorted(set(left) & set(right)):
            self._pair(key, left[key], right[key])
        for key in set(left) - set(right):
            if key in self.pending_right:
                self._pair(key, left[key], self.pending_right.pop(key))
            else:
                self.pending_left[key] = left[key]
        for key in set(right) - set(left):
            if key in self.pending_left:
                self._pair(key, self.pending_left.pop(key), right[key])
            else:
                self.pending_right[key] = right[key]

    def _pair(self, key: str, a: dict, b: dict) -> None:
        self.compared += 1
        pairs = field_pairs(a, b)
        self.names.update(ln for ln, _ in pairs)
        any_diff = False
        for ln, rn in pairs:
            va, vb = norm(a.get(ln)), norm(b.get(rn))
            if va == vb:
                continue
            kind = "different" if va is not None and vb is not None else "one_side_empty"
            f = self.fields.setdefault(ln, {"field": ln, "other": rn, "different": 0, "one_side_empty": 0,
                                            "examples": []})
            f[kind] += 1
            if kind == "different":
                any_diff = True
                if len(f["examples"]) < EXAMPLES_PER_FIELD:
                    f["examples"].append({"key": key, LEFT: a.get(ln), RIGHT: b.get(rn)})
        self.records_differing += any_diff

    def result(self) -> dict:
        return {
            "compared": self.compared,
            "only_left": sorted(self.pending_left),
            "only_right": sorted(self.pending_right),
            "fields_compared": len(self.names),
            "records_differing": self.records_differing,
            "fields": sorted(self.fields.values(), key=lambda f: (-f["different"], -f["one_side_empty"], f["field"])),
        }


def compare(left: dict[str, dict], right: dict[str, dict]) -> dict:
    """Records by key on each side -> the comparison (pure: no database)."""
    tally = Tally()
    tally.add(left, right)
    return tally.result()


def _current(s: Session, sid: int | None, period: str) -> dict[str, dict]:
    if sid is None:
        return {}
    return {key: doc for key, doc in s.execute(
        select(Record.source_key, Record.fields).where(
            Record.source_id == sid, Record.period == period, Record.record_type == RECORD_TYPE,
            Record.valid_to.is_(None)))}


def run(s: Session, now: datetime | None = None) -> dict:
    """Compare the current records, a month at a time, and keep the result. Commits."""
    now = now or datetime.now(UTC)
    ids = {name: s.scalar(select(Source.id).where(Source.name == name)) for name in (LEFT, RIGHT)}
    periods = sorted(set(s.scalars(select(Record.period).where(
        Record.source_id.in_([i for i in ids.values() if i is not None]), Record.record_type == RECORD_TYPE,
        Record.valid_to.is_(None)).distinct())))
    tally = Tally()
    for period in periods:
        tally.add(_current(s, ids[LEFT], period), _current(s, ids[RIGHT], period))
        s.expunge_all()
    result = tally.result()
    row = s.scalar(select(RecordComparison).where(RecordComparison.left_source == LEFT,
                                                  RecordComparison.right_source == RIGHT))
    if row is None:
        row = RecordComparison(left_source=LEFT, right_source=RIGHT, record_type=RECORD_TYPE)
        s.add(row)
    row.ran_at = now
    row.compared = result["compared"]
    row.only_left = len(result["only_left"])
    row.only_right = len(result["only_right"])
    row.records_differing = result["records_differing"]
    row.detail = {"fields": result["fields"], "only_left": result["only_left"][:50],
                  "only_right": result["only_right"][:50], "fields_compared": result["fields_compared"]}
    s.commit()
    return {
        "pair": f"{LEFT} vs {RIGHT}", "compared": result["compared"], "fields_compared": result["fields_compared"],
        "only_in_" + LEFT: len(result["only_left"]), "only_in_" + RIGHT: len(result["only_right"]),
        "records_differing": result["records_differing"],
        "fields_differing": [{k: f[k] for k in ("field", "other", "different", "one_side_empty", "examples")}
                             for f in result["fields"] if f["different"]][:30],
        "fields_one_side_empty": {f["field"]: f["one_side_empty"] for f in result["fields"] if f["one_side_empty"]},
        "examples_only_in_" + LEFT: result["only_left"][:10], "examples_only_in_" + RIGHT: result["only_right"][:10],
    }
