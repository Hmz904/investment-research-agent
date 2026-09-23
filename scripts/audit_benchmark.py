import ast
import csv
import re
from collections import Counter, defaultdict
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 40

ROOT = Path("benchmark/frozen")


def read_csv(name):
    path = ROOT / name
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows, f"{name}: empty"

    for i, row in enumerate(rows, start=2):
        assert None not in row, f"{name}:{i}: malformed CSV row"

    return rows


sources = read_csv("source_manifest.csv")
questions = read_csv("questions.csv")
facts = read_csv("numeric_answers.csv")
evidence = read_csv("evidence_checklist.csv")

errors = []
warnings = []

# ============================================================
# 1. Source manifest
# ============================================================

source_ids = [r["doc_id"] for r in sources]
source_accessions = [r["accession"] for r in sources]
allowed_accessions = set(source_accessions)

if len(sources) != 14:
    errors.append(f"expected 14 source docs, got {len(sources)}")

if len(source_ids) != len(set(source_ids)):
    errors.append("duplicate doc_id in source_manifest")

if len(source_accessions) != len(set(source_accessions)):
    errors.append("duplicate accession in source_manifest")

historical_refs = {
    "0001045810-25-000209",
    "0001045810-26-000019",
}

if not historical_refs.issubset(allowed_accessions):
    errors.append(
        "missing NVIDIA historical reference filings: "
        f"{sorted(historical_refs - allowed_accessions)}"
    )

# ============================================================
# 2. Questions
# ============================================================

qkeys = [(r["q_id"], r["version"]) for r in questions]
qmap = {(r["q_id"], r["version"]): r for r in questions}

if len(qkeys) != len(set(qkeys)):
    errors.append("duplicate (q_id, version) in questions")

frozen = {
    key: row
    for key, row in qmap.items()
    if row["status"] == "frozen"
}

if len(frozen) != 16:
    errors.append(f"expected 16 frozen questions, got {len(frozen)}")

expected_numeric = {
    ("Q01", "1"),
    ("Q03", "1"),
    ("Q06", "2"),
    ("Q08", "2"),
    ("Q11", "1"),
    ("Q13", "2"),
}

expected_checklist = {
    ("Q02", "2"),
    ("Q04", "2"),
    ("Q05", "2"),
    ("Q07", "2"),
    ("Q09", "2"),
    ("Q10", "2"),
    ("Q12", "2"),
    ("Q14", "2"),
    ("Q15", "2"),
    ("Q16", "2"),
}

actual_numeric = {
    key for key, row in frozen.items()
    if row["q_type"] == "numeric"
}

actual_checklist = set(frozen) - actual_numeric

if actual_numeric != expected_numeric:
    errors.append(
        "numeric manifest mismatch: "
        f"missing={sorted(expected_numeric - actual_numeric)}, "
        f"extra={sorted(actual_numeric - expected_numeric)}"
    )

if actual_checklist != expected_checklist:
    errors.append(
        "checklist manifest mismatch: "
        f"missing={sorted(expected_checklist - actual_checklist)}, "
        f"extra={sorted(actual_checklist - expected_checklist)}"
    )

for key, row in qmap.items():
    expected_label = (
        "numeric" if row["q_type"] == "numeric"
        else "checklist"
    )

    if row["label_type"] != expected_label:
        errors.append(
            f"{key}: q_type={row['q_type']} "
            f"but label_type={row['label_type']}"
        )

    deps = [x for x in row["depends_on"].split(";") if x]

    for dep in deps:
        if "@" not in dep:
            errors.append(f"{key}: bad dependency syntax {dep}")
            continue

        q, v = dep.split("@", 1)
        target = qmap.get((q, v))

        if target is None:
            errors.append(f"{key}: missing dependency target {dep}")
        elif row["status"] == "frozen" and target["status"] != "frozen":
            errors.append(
                f"{key}: frozen question depends on non-frozen {dep}"
            )

# Frozen update dependency invariant
if qmap[("Q05", "2")]["depends_on"] != "Q02@2":
    errors.append(
        "Q05@2 must depend only on Q02@2"
    )

# ============================================================
# 3. Numeric facts
# ============================================================

fact_ids = [r["fact_id"] for r in facts]
factmap = {r["fact_id"]: r for r in facts}

if len(fact_ids) != len(set(fact_ids)):
    errors.append("duplicate fact_id")

expected_fact_ids = {
    f"F{i:03d}" for i in range(1, 73)
} - {"F026"}

if set(fact_ids) != expected_fact_ids:
    errors.append(
        "fact-id set mismatch: "
        f"missing={sorted(expected_fact_ids - set(fact_ids))}, "
        f"extra={sorted(set(fact_ids) - expected_fact_ids)}"
    )

answer_questions = set()
graph = defaultdict(list)

for row in facts:
    fid = row["fact_id"]

    if row["role"] not in {"answer", "input"}:
        errors.append(f"{fid}: invalid role {row['role']}")

    if row["role"] == "answer":
        key = (row["q_id"], row["q_version"])
        answer_questions.add(key)

        if key not in expected_numeric:
            errors.append(
                f"{fid}: answer linked to non-numeric benchmark {key}"
            )

        if not row["answer_group"]:
            errors.append(f"{fid}: answer missing answer_group")

        if not row["answer_method"]:
            errors.append(f"{fid}: answer missing answer_method")

    else:
        if row["q_id"] or row["q_version"]:
            warnings.append(
                f"{fid}: input unexpectedly linked to question"
            )

        if row["answer_group"] or row["answer_method"]:
            errors.append(
                f"{fid}: input has answer_group/answer_method"
            )

    formula_refs = re.findall(
        r"\bF\d{3}\b",
        row["formula"] or ""
    )

    listed_refs = [
        x for x in (row["input_items"] or "").split(";")
        if x
    ]

    for ref in set(formula_refs + listed_refs):
        if ref not in factmap:
            errors.append(
                f"{fid}: missing fact reference {ref}"
            )
        else:
            graph[fid].append(ref)

    if row["is_derived"].lower() == "true":
        if not row["formula"]:
            errors.append(
                f"{fid}: derived fact missing formula"
            )

        if not listed_refs:
            errors.append(
                f"{fid}: derived fact missing input_items"
            )

    for acc in [
        x for x in row["accession"].split(";") if x
    ]:
        if acc not in allowed_accessions:
            errors.append(
                f"{fid}: accession not in source_manifest: {acc}"
            )

if answer_questions != expected_numeric:
    errors.append(
        "numeric answer-question mismatch: "
        f"missing={sorted(expected_numeric - answer_questions)}, "
        f"extra={sorted(answer_questions - expected_numeric)}"
    )

# ------------------------------------------------------------
# DAG cycle detection
# ------------------------------------------------------------

state = {}
cycle = []


def dfs(node, stack):
    state[node] = 1
    stack.append(node)

    for nxt in graph[node]:
        if state.get(nxt, 0) == 0:
            if dfs(nxt, stack):
                return True

        elif state.get(nxt) == 1:
            i = stack.index(nxt)
            cycle.extend(stack[i:] + [nxt])
            return True

    stack.pop()
    state[node] = 2
    return False


for fid in fact_ids:
    if state.get(fid, 0) == 0:
        if dfs(fid, []):
            break

if cycle:
    errors.append(
        f"fact dependency cycle: {cycle}"
    )

# ------------------------------------------------------------
# Safe Decimal formula evaluator
# ------------------------------------------------------------


def eval_formula(expr, env):
    tree = ast.parse(expr, mode="eval")

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)

        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ValueError(
                    f"unknown fact {node.id}"
                )
            return env[node.id]

        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))

        if isinstance(node, ast.BinOp):
            left = walk(node.left)
            right = walk(node.right)

            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right

            raise ValueError("invalid binary operator")

        if isinstance(node, ast.UnaryOp):
            value = walk(node.operand)

            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return value

            raise ValueError("invalid unary operator")

        raise ValueError(
            f"invalid AST node {type(node).__name__}"
        )

    return walk(tree)


env = {
    r["fact_id"]: Decimal(r["value"])
    for r in facts
}

formula_failures = []

for row in facts:
    if row["is_derived"].lower() != "true":
        continue

    exact = eval_formula(
        row["formula"],
        env
    )

    stored_raw = row["value"]
    stored = Decimal(stored_raw)

    decimals = (
        len(stored_raw.split(".", 1)[1])
        if "." in stored_raw
        else 0
    )

    quantum = Decimal("1").scaleb(-decimals)
    rounded = exact.quantize(quantum)

    if rounded != stored:
        formula_failures.append(
            (
                row["fact_id"],
                str(exact),
                stored_raw,
                str(rounded),
            )
        )

if formula_failures:
    errors.append(
        f"derived formula mismatches: {formula_failures}"
    )

# ============================================================
# 4. Evidence checklist
# ============================================================

ekeys = [
    (r["q_id"], r["q_version"], r["item_id"])
    for r in evidence
]

if len(ekeys) != len(set(ekeys)):
    errors.append(
        "duplicate evidence primary key"
    )

verified_evidence = [
    r for r in evidence
    if r["verification_status"] == "verified"
]

retired_evidence = [
    r for r in evidence
    if r["verification_status"] == "retired"
]

if len(evidence) != 114:
    errors.append(
        f"expected 114 retained evidence rows, got {len(evidence)}"
    )

if len(verified_evidence) != 113:
    errors.append(
        "expected 113 verified/scorable evidence rows, "
        f"got {len(verified_evidence)}"
    )

if len(retired_evidence) != 1:
    errors.append(
        f"expected 1 retired control row, got {len(retired_evidence)}"
    )

if not (
    len(retired_evidence) == 1
    and retired_evidence[0]["q_id"] == "Q15"
    and retired_evidence[0]["q_version"] == "2"
    and retired_evidence[0]["item_id"] == "E07"
):
    errors.append(
        "retired evidence is not exactly Q15@2 E07"
    )

verified_checklist_questions = {
    (r["q_id"], r["q_version"])
    for r in verified_evidence
}

if verified_checklist_questions != expected_checklist:
    errors.append(
        "verified checklist-question mismatch: "
        f"missing={sorted(expected_checklist - verified_checklist_questions)}, "
        f"extra={sorted(verified_checklist_questions - expected_checklist)}"
    )

allowed_stance = {
    "support",
    "contradict",
    "context",
}

allowed_importance = {
    "core",
    "supporting",
    "optional",
}

allowed_temporal = {
    "current",
    "prior_period",
    "change",
    "cross_company",
}

allowed_types = {
    "financial_metric",
    "management_guidance",
    "risk_factor",
    "customer_demand",
    "capacity_supply",
    "competitive",
    "regulatory",
    "accounting_policy",
    "other",
}

for row in evidence:
    eid = (
        f"{row['q_id']}@{row['q_version']}:"
        f"{row['item_id']}"
    )

    key = (
        row["q_id"],
        row["q_version"],
    )

    if key not in expected_checklist:
        errors.append(
            f"{eid}: linked to wrong benchmark question"
        )

    if row["stance"] not in allowed_stance:
        errors.append(
            f"{eid}: invalid stance {row['stance']}"
        )

    if row["importance"] not in allowed_importance:
        errors.append(
            f"{eid}: invalid importance {row['importance']}"
        )

    if row["temporal_role"] not in allowed_temporal:
        errors.append(
            f"{eid}: invalid temporal_role "
            f"{row['temporal_role']}"
        )

    if row["evidence_type"] not in allowed_types:
        errors.append(
            f"{eid}: invalid evidence_type "
            f"{row['evidence_type']}"
        )

    for acc in [
        x for x in row["accession"].split(";")
        if x
    ]:
        if acc not in allowed_accessions:
            errors.append(
                f"{eid}: accession not in source_manifest: {acc}"
            )

# Update-question coverage
for q in ["Q05", "Q10", "Q14"]:
    core_roles = {
        r["temporal_role"]
        for r in verified_evidence
        if (
            r["q_id"] == q
            and r["importance"] == "core"
        )
    }

    required = {
        "prior_period",
        "current",
        "change",
    }

    missing = required - core_roles

    if missing:
        errors.append(
            f"{q}: missing core update roles "
            f"{sorted(missing)}"
        )

# Q09 invariants
q09 = [
    r for r in verified_evidence
    if r["q_id"] == "Q09"
]

if not all(
    r["evidence_type"] == "risk_factor"
    for r in q09
):
    errors.append(
        "Q09 has non-risk_factor evidence"
    )

if not all(
    r["temporal_role"] == "change"
    for r in q09
):
    errors.append(
        "Q09 has non-change temporal role"
    )

# Cross-company invariants
for q in ["Q15", "Q16"]:
    if not all(
        r["temporal_role"] == "cross_company"
        for r in verified_evidence
        if r["q_id"] == q
    ):
        errors.append(
            f"{q}: verified evidence not all cross_company"
        )

# Specific benchmark invariants
q02e07 = next(
    r for r in evidence
    if r["q_id"] == "Q02"
    and r["q_version"] == "2"
    and r["item_id"] == "E07"
)

if q02e07["stance"] != "contradict":
    errors.append(
        "Q02@2 E07 must have stance=contradict"
    )

# ============================================================
# 5. Report
# ============================================================

print("=== BENCHMARK AUDIT ===")
print("sources:", len(sources))
print("question-version rows:", len(questions))
print("frozen questions:", len(frozen))
print("facts:", len(facts))
print(
    "derived facts:",
    sum(
        r["is_derived"].lower() == "true"
        for r in facts
    ),
)
print("retained evidence:", len(evidence))
print(
    "verified/scorable evidence:",
    len(verified_evidence),
)
print(
    "retired controls:",
    len(retired_evidence),
)

print("\nverified evidence by question:")
for key, n in sorted(
    Counter(
        (r["q_id"], r["q_version"])
        for r in verified_evidence
    ).items()
):
    print(
        f"  {key[0]}@{key[1]}: {n}"
    )

print(
    "\nformula failures:",
    formula_failures,
)
print("warnings:", warnings)
print("errors:", errors)

if errors:
    raise SystemExit("\nAUDIT FAILED")

print("\nAUDIT PASSED")
