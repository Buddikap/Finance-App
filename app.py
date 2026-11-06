import io
import json
import zipfile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="FP&A Prompt & LLM Assistant",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

TASKS = {
    "Variance Commentary": {
        "blurb": "Draft board-ready commentary on a budget-to-actual gap.",
        "role": (
            "You are a senior FP&A business partner writing variance commentary "
            "for a CFO and department leader."
        ),
        "fields": [
            {"key": "period", "label": "Period", "type": "text", "placeholder": "Q3 2026"},
            {"key": "department", "label": "Department", "type": "text", "placeholder": "Marketing"},
            {"key": "line_item", "label": "Line item", "type": "text", "placeholder": "Paid media"},
            {
                "key": "line_type",
                "label": "Line type",
                "type": "select",
                "options": ["Expense", "Revenue"],
            },
            {"key": "budget", "label": "Budget", "type": "money", "placeholder": "500,000"},
            {"key": "actual", "label": "Actual", "type": "money", "placeholder": "575,000"},
            {
                "key": "drivers",
                "label": "Known drivers (optional)",
                "type": "area",
                "placeholder": "Campaign pulled forward from Q4. Rate card increased 8%.",
                "optional": True,
            },
        ],
        "constraints": [
            "Use only the facts provided. Do not invent causes, customers, or timing.",
            "State variance as Actual minus Budget. Call the result favorable or unfavorable based on line type: over-spend is unfavorable for an expense; over-performance is favorable for revenue.",
            "Separate what is known from what still needs an owner to confirm.",
            "Keep the tone concise and suitable for a monthly finance pack. No jargon without a plain-English explanation.",
            "Do not recommend journal entries or restate the general ledger.",
        ],
        "output_format": [
            "Headline: one sentence with the line item, dollar variance, percent variance, and favorable or unfavorable.",
            "Bridge: two to four bullets on the drivers, each with an estimated dollar impact when the facts support it.",
            "Open items: bullets for missing facts a reviewer should confirm.",
            "Suggested owner question: one question the FP&A partner can send back to the department.",
        ],
    },
    "Accruals Explanation": {
        "blurb": "Explain why an accrual was recorded and when it should reverse.",
        "role": (
            "You are a senior FP&A accountant explaining an accrual to a controller "
            "and the budget owner."
        ),
        "fields": [
            {"key": "period", "label": "Period", "type": "text", "placeholder": "October 2026"},
            {"key": "department", "label": "Department", "type": "text", "placeholder": "Operations"},
            {"key": "account", "label": "Account", "type": "text", "placeholder": "Professional services"},
            {"key": "vendor", "label": "Vendor or counterparty", "type": "text", "placeholder": "Northwind Advisory"},
            {"key": "amount", "label": "Accrual amount", "type": "money", "placeholder": "42,000"},
            {
                "key": "basis",
                "label": "Basis",
                "type": "select",
                "options": [
                    "Goods or services received, invoice not yet booked",
                    "Estimate based on contract or run-rate",
                    "Partial-period charge",
                    "Other — describe in the notes",
                ],
            },
            {
                "key": "support",
                "label": "What was received or incurred",
                "type": "area",
                "placeholder": "Advisory work delivered in October. Invoice expected mid-November.",
            },
            {
                "key": "reversal",
                "label": "Expected reversal",
                "type": "text",
                "placeholder": "Reverse when the November invoice is posted",
            },
        ],
        "constraints": [
            "Use only the facts provided. If support is thin, say so plainly.",
            "Do not conclude that the amount is audit-ready unless the notes already say that.",
            "Distinguish the accounting reason for the accrual from the business reason for the spend.",
            "State the reversal trigger in operational language a budget owner can act on.",
            "Do not propose a different accounting policy.",
        ],
        "output_format": [
            "Summary: period, account, counterparty, amount, and basis in one short paragraph.",
            "Support: bullets listing the evidence provided and any evidence still missing.",
            "Reversal: when it should come off the books and what document will clear it.",
            "Reviewer note: one sentence on residual risk (timing, estimate quality, or duplicate-invoice risk).",
        ],
    },
    "Cash Burn Summary": {
        "blurb": "Summarize cash movement, burn, and runway for leadership.",
        "role": (
            "You are a senior FP&A lead preparing a cash burn summary for the CEO and CFO."
        ),
        "fields": [
            {"key": "entity", "label": "Entity", "type": "text", "placeholder": "Contoso Holdings"},
            {"key": "period", "label": "Period", "type": "text", "placeholder": "Q3 2026"},
            {"key": "months", "label": "Months in period", "type": "number", "placeholder": "3"},
            {"key": "beginning_cash", "label": "Beginning cash", "type": "money", "placeholder": "12,000,000"},
            {"key": "ending_cash", "label": "Ending cash", "type": "money", "placeholder": "9,400,000"},
            {
                "key": "restricted",
                "label": "Restricted or trapped cash (optional)",
                "type": "money",
                "placeholder": "500,000",
                "optional": True,
            },
            {
                "key": "uses",
                "label": "Principal uses and sources of cash (optional)",
                "type": "area",
                "placeholder": "Payroll and vendors $2.1M. Equity raise $0. Collection delay on two enterprise invoices.",
                "optional": True,
            },
        ],
        "constraints": [
            "Use only the figures and notes provided. Do not assume debt capacity, covenants, or future raises.",
            "Define net burn as beginning cash minus ending cash. A cash increase is a surplus, not a burn.",
            "Monthly burn equals net burn divided by the number of months in the period.",
            "Runway equals unrestricted ending cash divided by monthly burn. If burn is zero or negative, say runway is not meaningful and state that cash increased.",
            "Unrestricted cash equals ending cash minus restricted cash. If restricted cash is blank, treat all ending cash as unrestricted and say that assumption.",
            "Separate operating narrative from financing events when the notes support that split. Otherwise do not invent the split.",
        ],
        "output_format": [
            "Snapshot: beginning cash, ending cash, net burn or surplus, monthly burn, unrestricted cash, and runway.",
            "What moved cash: three to five bullets grounded in the notes.",
            "Watch items: liquidity risks that follow from the figures, without speculative scenarios.",
            "Questions for treasury: up to three facts needed before the next forecast lock.",
        ],
    },
    "Working Capital Analysis": {
        "blurb": "Turn receivables, inventory, and payables into a working-capital readout.",
        "role": (
            "You are a senior FP&A analyst writing a working-capital commentary "
            "for the CFO and the order-to-cash and procure-to-pay owners."
        ),
        "fields": [
            {"key": "entity", "label": "Entity", "type": "text", "placeholder": "Contoso Holdings"},
            {"key": "period", "label": "Period", "type": "text", "placeholder": "September 2026"},
            {"key": "days", "label": "Days in period", "type": "number", "placeholder": "30"},
            {"key": "revenue", "label": "Revenue", "type": "money", "placeholder": "8,000,000"},
            {"key": "cogs", "label": "COGS (optional, for DIO)", "type": "money", "placeholder": "3,200,000", "optional": True},
            {"key": "receivables", "label": "Accounts receivable", "type": "money", "placeholder": "2,400,000"},
            {"key": "inventory", "label": "Inventory", "type": "money", "placeholder": "900,000"},
            {"key": "payables", "label": "Accounts payable", "type": "money", "placeholder": "700,000"},
            {
                "key": "notes",
                "label": "Context (optional)",
                "type": "area",
                "placeholder": "Two large invoices billed on the last day of the month. Inventory build ahead of a product launch.",
                "optional": True,
            },
        ],
        "constraints": [
            "Use only the balances and notes provided.",
            "Net working capital equals receivables plus inventory minus payables.",
            "DSO equals receivables divided by revenue, times days in the period. Skip DSO if revenue is zero.",
            "DIO equals inventory divided by COGS, times days in the period. Skip DIO if COGS is blank or zero.",
            "DPO equals payables divided by COGS, times days in the period. Skip DPO if COGS is blank or zero.",
            "Cash conversion cycle equals DSO plus DIO minus DPO, and only when all three components are available.",
            "Do not benchmark against an industry median unless one was provided.",
        ],
        "output_format": [
            "Position: net working capital and each balance, with the ratios that can be calculated.",
            "Read-through: what the ratios imply about collections, stock, and payment timing, tied to the notes.",
            "Cash impact: whether working capital is absorbing or releasing cash, stated qualitatively if a prior period was not provided.",
            "Follow-ups: specific questions for billing, supply chain, or accounts payable.",
        ],
    },
}


def parse_number(raw: str) -> float | None:
    cleaned = raw.strip().replace(",", "").replace("$", "").replace(" ", "")
    if cleaned in {"", "-", ".", "-."}:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if negative else value


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}" if float(value).is_integer() else f"{sign}${abs(value):,.2f}"


def pct(part: float, base: float) -> str:
    if base == 0:
        return "n/m (base is zero)"
    return f"{part / base * 100:,.1f}%"


def widget_key(task_name: str, field: dict) -> str:
    return f"{task_name}::{field['key']}"


def render_field(task_name: str, field: dict) -> None:
    key = widget_key(task_name, field)
    label = field["label"] if field.get("optional") else f"{field['label']} *"
    kind = field["type"]
    if kind == "area":
        st.text_area(label, placeholder=field.get("placeholder", ""), key=key, height=110)
    elif kind == "select":
        st.selectbox(label, field["options"], key=key)
    else:
        st.text_input(label, placeholder=field.get("placeholder", ""), key=key)


def collect(task_name: str, task: dict) -> tuple[dict, list[str]]:
    values: dict[str, str | float] = {}
    errors: list[str] = []
    for field in task["fields"]:
        raw = str(st.session_state.get(widget_key(task_name, field), "")).strip()
        optional = field.get("optional", False)
        if field["type"] in {"money", "number"}:
            if raw == "":
                if not optional:
                    errors.append(field["label"])
                continue
            parsed = parse_number(raw)
            if parsed is None:
                errors.append(f"{field['label']} (enter a number)")
                continue
            if field["type"] == "number" and parsed <= 0:
                errors.append(f"{field['label']} (enter a number greater than zero)")
                continue
            values[field["key"]] = parsed
        else:
            if raw == "" and not optional:
                errors.append(field["label"])
                continue
            if raw:
                values[field["key"]] = raw
    return values, errors


def bullet(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def variance_facts(values: dict) -> list[str]:
    budget = float(values["budget"])
    actual = float(values["actual"])
    gap = actual - budget
    line_type = str(values["line_type"])
    if line_type == "Expense":
        direction = "unfavorable" if gap > 0 else "favorable" if gap < 0 else "on budget"
    else:
        direction = "favorable" if gap > 0 else "unfavorable" if gap < 0 else "on budget"
    facts = [
        f"Period: {values['period']}",
        f"Department: {values['department']}",
    ]
    if values.get("category"):
        facts.append(f"Category: {values['category']}")
    facts.extend(
        [
            f"Line item: {values['line_item']} ({line_type})",
            f"Budget: {money(budget)}",
            f"Actual: {money(actual)}",
            f"Variance (Actual − Budget): {money(gap)} ({pct(gap, budget)}), {direction}",
        ]
    )
    if values.get("drivers"):
        facts.append(f"Known drivers supplied by the user: {values['drivers']}")
    return facts


def accrual_facts(values: dict) -> list[str]:
    facts = [
        f"Period: {values['period']}",
        f"Department: {values['department']}",
        f"Account: {values['account']}",
        f"Vendor or counterparty: {values['vendor']}",
        f"Accrual amount: {money(float(values['amount']))}",
        f"Basis: {values['basis']}",
        f"What was received or incurred: {values['support']}",
        f"Expected reversal: {values['reversal']}",
    ]
    return facts


def burn_facts(values: dict) -> list[str]:
    beginning = float(values["beginning_cash"])
    ending = float(values["ending_cash"])
    months = float(values["months"])
    net = beginning - ending
    monthly = net / months
    restricted = values.get("restricted")
    if restricted is None:
        unrestricted = ending
        restricted_line = "Restricted cash: not provided. Treat ending cash as unrestricted."
    else:
        unrestricted = ending - float(restricted)
        restricted_line = f"Restricted cash: {money(float(restricted))}"
    if monthly > 0:
        runway = f"{unrestricted / monthly:,.1f} months" if monthly else "n/m"
        movement = f"Net burn: {money(net)} ({money(monthly)} per month)"
    elif monthly < 0:
        runway = "Not meaningful — cash increased over the period"
        movement = f"Net surplus: {money(abs(net))} ({money(abs(monthly))} per month)"
    else:
        runway = "Not meaningful — cash was unchanged"
        movement = "Net burn: $0"
    facts = [
        f"Entity: {values['entity']}",
        f"Period: {values['period']} ({months:g} months)",
        f"Beginning cash: {money(beginning)}",
        f"Ending cash: {money(ending)}",
        restricted_line,
        f"Unrestricted ending cash: {money(unrestricted)}",
        movement,
        f"Runway on unrestricted cash: {runway}",
    ]
    if values.get("uses"):
        facts.append(f"Notes on sources and uses: {values['uses']}")
    return facts


def days_ratio(balance: float, flow: float | None, days: float, name: str) -> str | None:
    if flow is None or flow == 0:
        return None
    return f"{name}: {balance / flow * days:,.1f} days"


def working_capital_facts(values: dict) -> list[str]:
    revenue = float(values["revenue"])
    receivables = float(values["receivables"])
    inventory = float(values["inventory"])
    payables = float(values["payables"])
    days = float(values["days"])
    cogs = values.get("cogs")
    cogs_value = None if cogs is None else float(cogs)
    nwc = receivables + inventory - payables
    facts = [
        f"Entity: {values['entity']}",
        f"Period: {values['period']} ({days:g} days)",
        f"Revenue: {money(revenue)}",
        f"COGS: {money(cogs_value)}" if cogs_value is not None else "COGS: not provided",
        f"Accounts receivable: {money(receivables)}",
        f"Inventory: {money(inventory)}",
        f"Accounts payable: {money(payables)}",
        f"Net working capital (AR + Inventory − AP): {money(nwc)}",
    ]
    ratios = [
        days_ratio(receivables, revenue, days, "DSO"),
        days_ratio(inventory, cogs_value, days, "DIO"),
        days_ratio(payables, cogs_value, days, "DPO"),
    ]
    named = [ratio for ratio in ratios if ratio]
    if len(named) == 3:
        dso = receivables / revenue * days
        dio = inventory / cogs_value * days
        dpo = payables / cogs_value * days
        named.append(f"Cash conversion cycle (DSO + DIO − DPO): {dso + dio - dpo:,.1f} days")
    if named:
        facts.extend(named)
    else:
        facts.append("Activity ratios: not calculated because the required flow amounts are zero or missing.")
    if values.get("notes"):
        facts.append(f"Context supplied by the user: {values['notes']}")
    return facts


FACT_BUILDERS = {
    "Variance Commentary": variance_facts,
    "Accruals Explanation": accrual_facts,
    "Cash Burn Summary": burn_facts,
    "Working Capital Analysis": working_capital_facts,
}


def build_prompt(name: str, task: dict, values: dict) -> str:
    facts = FACT_BUILDERS[name](values)
    sections = [
        f"Role\n{task['role']}",
        f"Context\nPrepare the following {name.lower()} using only the facts below.\n\n{bullet(facts)}",
        (
            "Task\n"
            f"Write a {name.lower()} that a finance business partner can drop into a management pack "
            "or send to a stakeholder with light editing."
        ),
        f"Constraints\n{bullet(task['constraints'])}",
        f"Output format\n{bullet(task['output_format'])}",
    ]
    return "\n\n".join(sections)


BULK_COLUMNS = ["Line_Item", "Category", "Department", "Period", "Budget", "Actual"]


def cell_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def canonicalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    lookup = {str(column).strip().lower(): column for column in df.columns}
    rename = {}
    for name in BULK_COLUMNS + ["Drivers"]:
        source = lookup.get(name.lower())
        if source is not None:
            rename[source] = name
    return df.rename(columns=rename)


def line_type_from_category(category: str) -> str:
    text = category.lower()
    if any(hint in text for hint in ("expense", "cost of", "cogs", "overhead")):
        return "Expense"
    if any(hint in text for hint in ("revenue", "income", "sales", "turnover")):
        return "Revenue"
    return "Expense"


def variance_direction(line_type: str, gap: float) -> str:
    if gap == 0:
        return "on budget"
    if line_type == "Expense":
        return "unfavorable" if gap > 0 else "favorable"
    return "favorable" if gap > 0 else "unfavorable"


def load_variance_csv(uploaded) -> tuple[pd.DataFrame | None, str | None]:
    try:
        frame = pd.read_csv(uploaded)
    except Exception:
        return None, "This file could not be read as a CSV."
    frame = canonicalize_columns(frame)
    missing = [column for column in BULK_COLUMNS if column not in frame.columns]
    if missing:
        return None, "Missing required column(s): " + ", ".join(missing) + "."
    if frame.empty:
        return None, "The file has headers but no data rows."
    return frame, None


def build_bulk_prompts(frame: pd.DataFrame, unfavorable_only: bool, threshold: float) -> tuple[pd.DataFrame, str, list[str]]:
    task = TASKS["Variance Commentary"]
    records = []
    skipped: list[str] = []
    for index, row in frame.iterrows():
        row_number = int(index) + 2
        line_item = cell_text(row["Line_Item"])
        category = cell_text(row["Category"])
        department = cell_text(row["Department"])
        period = cell_text(row["Period"])
        budget = parse_number(cell_text(row["Budget"]))
        actual = parse_number(cell_text(row["Actual"]))
        problems = []
        if not line_item:
            problems.append("Line_Item")
        if not category:
            problems.append("Category")
        if not department:
            problems.append("Department")
        if not period:
            problems.append("Period")
        if budget is None:
            problems.append("Budget")
        if actual is None:
            problems.append("Actual")
        if problems:
            skipped.append(f"Row {row_number}: missing or invalid {', '.join(problems)}.")
            continue
        gap = actual - budget
        line_type = line_type_from_category(category)
        direction = variance_direction(line_type, gap)
        if unfavorable_only and not (direction == "unfavorable" and abs(gap) > threshold):
            skipped.append(
                f"Row {row_number} ({line_item}): {direction}, variance {money(gap)}."
            )
            continue
        values = {
            "period": period,
            "department": department,
            "category": category,
            "line_item": line_item,
            "line_type": line_type,
            "budget": budget,
            "actual": actual,
        }
        drivers = cell_text(row["Drivers"]) if "Drivers" in frame.columns else ""
        if drivers:
            values["drivers"] = drivers
        prompt = build_prompt("Variance Commentary", task, values)
        records.append(
            {
                "Row": row_number,
                "Line_Item": line_item,
                "Category": category,
                "Department": department,
                "Period": period,
                "Budget": budget,
                "Actual": actual,
                "Variance_$": gap,
                "Variance_%": None if budget == 0 else gap / budget * 100,
                "Direction": direction,
                "Prompt": prompt,
            }
        )
    result = pd.DataFrame(records)
    if result.empty:
        report = "No prompts were generated.\n"
    else:
        scope = (
            f"Unfavorable variances greater than {money(threshold)}."
            if unfavorable_only
            else "Every valid row."
        )
        blocks = [
            "FP&A variance prompts",
            f"Scope: {scope}",
            f"Prompts: {len(result)}",
            "",
        ]
        for number, record in enumerate(result.to_dict(orient="records"), start=1):
            blocks.extend(
                [
                    "=" * 80,
                    (
                        f"{number}. {record['Line_Item']} | {record['Department']} | "
                        f"{record['Period']} | {record['Direction']} {money(record['Variance_$'])}"
                    ),
                    "=" * 80,
                    record["Prompt"],
                    "",
                ]
            )
        report = "\n".join(blocks)
    return result, report, skipped


def preview_frame(frame: pd.DataFrame) -> pd.DataFrame:
    preview = frame[BULK_COLUMNS].copy()
    budgets = preview["Budget"].map(lambda value: parse_number(cell_text(value)))
    actuals = preview["Actual"].map(lambda value: parse_number(cell_text(value)))
    preview["Variance ($)"] = [
        None if budget is None or actual is None else actual - budget
        for budget, actual in zip(budgets, actuals)
    ]
    preview["Variance (%)"] = [
        None if budget in (None, 0) or actual is None else (actual - budget) / budget * 100
        for budget, actual in zip(budgets, actuals)
    ]
    preview["Direction"] = [
        ""
        if budget is None or actual is None
        else variance_direction(line_type_from_category(cell_text(category)), actual - budget)
        for category, budget, actual in zip(preview["Category"], budgets, actuals)
    ]
    return preview


PASTE_INSTRUCTIONS = """
1. Copy the prompt and paste it into ChatGPT or Claude as the first message.
2. The prompt already includes every column name, the data issues found in the file, and a sample of rows.
3. Download the chunked CSVs. Each chunk repeats the header so it can be read on its own.
4. Paste chunk 1 in the next message, then each following chunk. Ask the model to continue the same output columns and not repeat the header.
5. Save the model's final CSV. In Power BI, use Get data, then Text/CSV. Power Query will use the first row as headers.
""".strip()


def load_messy_table(uploaded, sheet: str | None) -> tuple[pd.DataFrame | None, list[str], str | None]:
    name = uploaded.name.lower()
    uploaded.seek(0)
    try:
        if name.endswith(".csv"):
            try:
                frame = pd.read_csv(uploaded)
            except UnicodeDecodeError:
                uploaded.seek(0)
                frame = pd.read_csv(uploaded, encoding="latin-1")
            return frame, [], None
        excel = pd.ExcelFile(uploaded)
        chosen = sheet if sheet in excel.sheet_names else excel.sheet_names[0]
        frame = excel.parse(chosen)
        return frame, excel.sheet_names, None
    except ImportError:
        return None, [], "Excel files need the openpyxl package. Install it, then upload the file again."
    except Exception:
        return None, [], "This file could not be read. Use a CSV or an .xlsx workbook."


def _examples(series: pd.Series, limit: int = 4) -> str:
    values = []
    for value in series.dropna().tolist():
        text = " ".join(str(value).split())
        if not text or text.lower() == "nan" or text in values:
            continue
        values.append(text[:60])
        if len(values) == limit:
            break
    return "; ".join(values) if values else "—"


def _text_issues(series: pd.Series) -> list[str]:
    raw = series.dropna().astype(str).head(2000)
    if raw.empty:
        return []
    issues = []
    if (raw != raw.str.strip()).any():
        issues.append("leading or trailing spaces")
    if (raw.str.strip() == "").any():
        issues.append("blank text that is not a true empty cell")
    currency = raw.str.contains(r"[$€£]|,|\(.*\)", regex=True)
    if currency.mean() >= 0.3:
        issues.append("currency symbols, thousands separators, or accounting parentheses")
    formats = {
        "YYYY-MM-DD": r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$",
        "M/D/YYYY": r"^\d{1,2}/\d{1,2}/\d{2,4}$",
        "D-Mon-YYYY": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$",
    }
    found = [label for label, pattern in formats.items() if raw.str.match(pattern).mean() >= 0.2]
    if len(found) > 1:
        issues.append("mixed date formats (" + ", ".join(found) + ")")
    elif found and not str(series.dtype).startswith("datetime"):
        issues.append(f"dates stored as text ({found[0]})")
    stripped = raw.str.strip()
    if stripped.nunique() > 1 and stripped.str.lower().nunique() < stripped.nunique():
        issues.append("inconsistent capitalization of the same text")
    return issues


def inspect_frame(frame: pd.DataFrame) -> dict:
    names = [str(column) for column in frame.columns]
    file_issues = []
    if any(name.lower().startswith("unnamed") for name in names):
        file_issues.append("One or more columns have no header (Unnamed).")
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        file_issues.append("Duplicate column names: " + ", ".join(duplicates) + ".")
    columns = []
    for name, series in frame.items():
        nulls = int(series.isna().sum())
        kind = str(series.dtype)
        text_like = kind in {"object", "string", "str"} or kind.startswith("string")
        issues = _text_issues(series) if text_like else []
        if nulls:
            issues.append(f"{nulls} empty cell(s)")
        columns.append(
            {
                "Column": str(name),
                "Stored as": str(series.dtype),
                "Empty cells": nulls,
                "Examples": _examples(series),
                "Issues": "; ".join(issues) if issues else "None noted",
            }
        )
    return {"rows": len(frame), "file_issues": file_issues, "columns": columns}


def build_cleaning_prompt(file_name: str, sheet: str | None, inspection: dict, sample_csv: str) -> str:
    column_lines = [
        (
            f"- {column['Column']} | stored as {column['Stored as']} | "
            f"empty cells: {column['Empty cells']} | examples: {column['Examples']} | "
            f"issues: {column['Issues']}"
        )
        for column in inspection["columns"]
    ]
    location = f"File: {file_name}"
    if sheet:
        location += f"\nSheet: {sheet}"
    file_issues = inspection["file_issues"] or ["No file-level header problems detected."]
    return "\n\n".join(
        [
            (
                "Role\n"
                "You are a senior FP&A data steward preparing a source file for Power Query and Power BI."
            ),
            (
                "Context\n"
                "Clean the financial extract described below. Use only the columns, issues, and sample rows "
                "provided, plus any later CSV chunks from the same file.\n\n"
                f"{location}\n"
                f"Rows in the file: {inspection['rows']}\n"
                f"Columns: {len(inspection['columns'])}\n\n"
                "File-level findings\n"
                f"{bullet(file_issues)}\n\n"
                "Column inventory\n"
                f"{chr(10).join(column_lines)}\n\n"
                "Sample rows (cell text may be shortened)\n"
                f"```csv\n{sample_csv.strip()}\n```"
            ),
            (
                "Task\n"
                "Produce a clean tabular dataset a finance analyst can load into Power Query without "
                "further reshaping. Standardize text, dates, numbers, and financial categories."
            ),
            (
                "Constraints\n"
                + bullet(
                    [
                        "Do not invent accounts, entities, departments, or amounts. If a value cannot be repaired from the cell itself, leave it blank and list it as an exception.",
                        "Keep every source row unless it is an exact duplicate. Add Source_Row with the original row number, counting the first data row as 1.",
                        "Trim text, collapse repeated internal spaces, and use consistent capitalization for categories. Do not change the spelling of account names except to remove obvious extra spaces.",
                        "Map financial categories only when the source text supports it. Allowed values: Revenue, COGS, OpEx, Other income, Other expense, Balance sheet, Unmapped. Cost of sales and COGS map to COGS. Operating expenses map to OpEx. Leave Unmapped when the category is ambiguous.",
                        "Convert dates to YYYY-MM-DD. If a date cannot be read unambiguously, leave it blank and report the source value.",
                        "Convert amounts to plain decimal numbers. Treat accounting parentheses as negative. Remove currency symbols and thousands separators. Do not scale numbers.",
                        "Represent missing values as empty CSV fields, not as N/A, null, or a hyphen.",
                        "Keep source columns that do not fit the target list. Clean their headers to letters, numbers, and underscores, and prefix those headers with Source_.",
                        "Return UTF-8 CSV with one header row, comma separators, and quotes around any field that contains a comma or line break. No title, notes, or subtotals inside the CSV.",
                        "If the user pastes later chunks from this same file, continue the same output columns and do not repeat the header.",
                    ]
                )
            ),
            (
                "Output format\n"
                + bullet(
                    [
                        "Cleaning log: short bullets of the repairs you made, tied to column names.",
                        "Exceptions: source row, column, original value, and why it was left blank or Unmapped.",
                        "One fenced csv block. Start with this header, then any Source_ columns: Source_Row,Date,Entity,Account,Account_Name,Category,Department,Description,Amount,Currency. Omit a target column only when the source has no field that can fill it, and say so in the cleaning log.",
                    ]
                )
            ),
        ]
    )


def sample_csv(frame: pd.DataFrame, rows: int = 8) -> str:
    sample = frame.head(rows).copy()
    for column in sample.columns:
        sample[column] = [
            "" if pd.isna(value) else " ".join(str(value).split())[:80] for value in sample[column]
        ]
    return sample.to_csv(index=False)


def split_for_ingestion(frame: pd.DataFrame, max_chars: int = 14000) -> list[pd.DataFrame]:
    chunks: list[pd.DataFrame] = []
    start = 0
    total = len(frame)
    while start < total:
        size = min(200, total - start)
        while size > 1 and len(frame.iloc[start : start + size].to_csv(index=False)) > max_chars:
            size //= 2
        chunks.append(frame.iloc[start : start + size])
        start += size
    return chunks


def ingestion_zip(frame: pd.DataFrame, prompt: str) -> tuple[bytes, int]:
    chunks = split_for_ingestion(frame)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("00_how_to_paste.txt", PASTE_INSTRUCTIONS + "\n")
        archive.writestr("01_cleaning_prompt.txt", prompt)
        for number, chunk in enumerate(chunks, start=1):
            archive.writestr(f"chunk_{number:03d}.csv", chunk.to_csv(index=False))
    return buffer.getvalue(), len(chunks)


def render_bi_pipeline() -> None:
    st.write(
        "Upload a raw GL extract or other messy finance file. The app profiles the columns and "
        "writes a prompt that asks ChatGPT or Claude for a Power Query-ready CSV."
    )
    uploaded = st.file_uploader(
        "Messy CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        key="bi_upload",
    )
    if uploaded is None:
        st.info("Choose a CSV or Excel export to preview its columns and sample rows.")
        return

    sheet = None
    sheet_names: list[str] = []
    if uploaded.name.lower().endswith((".xlsx", ".xls")):
        try:
            uploaded.seek(0)
            sheet_names = pd.ExcelFile(uploaded).sheet_names
        except ImportError:
            st.error("Excel files need the openpyxl package. Install it, then upload the file again.")
            return
        except Exception:
            st.error("This workbook could not be opened. Save it as .xlsx and try again.")
            return
        sheet = st.selectbox("Worksheet", sheet_names, key="bi_sheet")

    frame, _, load_error = load_messy_table(uploaded, sheet)
    if load_error or frame is None:
        st.error(load_error or "This file could not be read.")
        return
    if frame.empty or len(frame.columns) == 0:
        st.error("The file has no rows or no columns to profile.")
        return

    token = f"{uploaded.name}:{uploaded.size}:{sheet or ''}"
    if token != st.session_state.get("clean_token"):
        st.session_state.clean_token = token
        st.session_state.clean_prompt = ""
        st.session_state.clean_zip = b""
        st.session_state.clean_chunks = 0

    inspection = inspect_frame(frame)
    st.subheader("Preview")
    location = uploaded.name if sheet is None else f"{uploaded.name} · {sheet}"
    st.caption(f"{inspection['rows']} row(s) and {len(inspection['columns'])} column(s) in {location}.")
    if inspection["file_issues"]:
        st.warning(" ".join(inspection["file_issues"]))
    st.markdown("**Column names and what is in them**")
    st.dataframe(pd.DataFrame(inspection["columns"]), use_container_width=True, hide_index=True)
    st.markdown("**First rows**")
    st.dataframe(frame.head(8), use_container_width=True, hide_index=True)

    if st.button("Generate Data Cleaning & Structuring Prompt", type="primary"):
        prompt = build_cleaning_prompt(uploaded.name, sheet, inspection, sample_csv(frame))
        payload, chunk_count = ingestion_zip(frame, prompt)
        st.session_state.clean_prompt = prompt
        st.session_state.clean_zip = payload
        st.session_state.clean_chunks = chunk_count

    if st.session_state.get("clean_prompt"):
        with st.container(border=True):
            st.subheader("Paste this into ChatGPT or Claude")
            st.markdown(PASTE_INSTRUCTIONS)
            copy_button(st.session_state.clean_prompt)
            st.code(st.session_state.clean_prompt, language="markdown")
            st.download_button(
                f"Download raw data in {st.session_state.clean_chunks} chunk(s)",
                data=st.session_state.clean_zip,
                file_name="powerbi_prep_chunks.zip",
                mime="application/zip",
                use_container_width=True,
            )


def copy_button(text: str) -> None:
    payload = json.dumps(text)
    components.html(
        f"""
        <div style="display:flex; align-items:center; gap:12px; font-family:'Segoe UI', sans-serif;">
          <button id="copy-prompt" style="
              background:#1f4e79; color:#fff; border:none; border-radius:6px;
              padding:8px 14px; font-size:14px; font-weight:600; cursor:pointer;">
            Copy prompt
          </button>
          <span id="copy-status" style="color:#1f7a4d; font-size:14px;"></span>
        </div>
        <script>
          const text = {payload};
          const button = document.getElementById("copy-prompt");
          const status = document.getElementById("copy-status");
          button.addEventListener("click", () => {{
            const area = document.createElement("textarea");
            area.value = text;
            document.body.appendChild(area);
            area.select();
            let ok = false;
            try {{ ok = document.execCommand("copy"); }} catch (err) {{ ok = false; }}
            document.body.removeChild(area);
            if (ok) {{
              status.textContent = "Copied. Paste it into ChatGPT or Claude.";
            }} else if (navigator.clipboard) {{
              navigator.clipboard.writeText(text).then(() => {{
                status.textContent = "Copied. Paste it into ChatGPT or Claude.";
              }}).catch(() => {{
                status.textContent = "Select the prompt and copy it manually.";
                status.style.color = "#8a5a00";
              }});
            }} else {{
              status.textContent = "Select the prompt and copy it manually.";
              status.style.color = "#8a5a00";
            }}
          }});
        </script>
        """,
        height=48,
    )


st.markdown(
    """
    <style>
        .stApp { background: #f4f6f8; }
        [data-testid="stSidebar"] { background: #10233f; }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] li,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span { color: #e7eef6; }
        [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.15); }
        .brand-kicker {
            letter-spacing: 0.14em;
            text-transform: uppercase;
            font-size: 0.75rem;
            color: #8fb4d6;
            margin-bottom: 0;
        }
        .block-container { padding-top: 1.6rem; max-width: 1080px; }
        div[data-testid="stForm"] {
            background: #ffffff;
            border: 1px solid #e3e8ee;
            border-radius: 12px;
            padding: 1.1rem 1.2rem 0.4rem 1.2rem;
        }
        .stFormSubmitButton button, div.stButton > button {
            background: #1f4e79;
            color: #ffffff;
            border: none;
            border-radius: 6px;
            font-weight: 600;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

if "prompt" not in st.session_state:
    st.session_state.prompt = ""
if "prompt_task" not in st.session_state:
    st.session_state.prompt_task = "Variance Commentary"
if "bulk_token" not in st.session_state:
    st.session_state.bulk_token = ""
if "bulk_csv" not in st.session_state:
    st.session_state.bulk_csv = ""
if "bulk_report" not in st.session_state:
    st.session_state.bulk_report = ""
if "bulk_count" not in st.session_state:
    st.session_state.bulk_count = 0

with st.sidebar:
    st.markdown('<p class="brand-kicker">Finance planning</p>', unsafe_allow_html=True)
    st.header("FP&A Prompt & LLM Assistant")
    st.caption("Build a structured prompt, then paste it into ChatGPT or Claude.")
    mode = st.radio(
        "Workspace",
        ["Single prompt", "Bulk CSV Variance Prompts", "Messy Data to BI Pipeline"],
        key="workspace",
    )
    st.divider()
    if mode == "Single prompt":
        choice = st.radio("FP&A task", list(TASKS), key="task_choice", label_visibility="collapsed")
        if choice != st.session_state.prompt_task:
            st.session_state.prompt = ""
            st.session_state.prompt_task = choice
        st.divider()
        st.markdown(f"**{choice}**")
        st.write(TASKS[choice]["blurb"])
        st.divider()
        st.markdown(
            "1. Choose a task\n"
            "2. Enter the facts you already have\n"
            "3. Generate the prompt\n"
            "4. Copy it into your model"
        )
    elif mode == "Bulk CSV Variance Prompts":
        st.markdown("**Bulk CSV Variance Prompts**")
        st.write("One variance commentary prompt per budget line, ready to paste into a model.")
        st.divider()
        st.markdown(
            "Required columns:\n"
            "- Line_Item\n"
            "- Category\n"
            "- Department\n"
            "- Period\n"
            "- Budget\n"
            "- Actual"
        )
    else:
        st.markdown("**Messy Data to BI Pipeline**")
        st.write("Profile a raw extract and build a cleaning prompt for Power Query.")
        st.divider()
        st.markdown(
            "1. Upload a CSV or Excel file\n"
            "2. Review the columns and sample rows\n"
            "3. Generate the cleaning prompt\n"
            "4. Copy it, then paste any data chunks"
        )

st.markdown('<p class="brand-kicker">Prompt builder</p>', unsafe_allow_html=True)
st.title("FP&A Prompt & LLM Assistant")

if mode == "Single prompt":
    st.write(
        "Turn the numbers you already have into a prompt with a clear role, context, "
        "constraints, and output format."
    )
    task_name = choice
    task = TASKS[task_name]
    with st.form("task-inputs"):
        st.subheader(task_name)
        st.caption("Fields marked with * are required. Figures can include commas.")
        left, right = st.columns(2)
        for index, field in enumerate(task["fields"]):
            with left if index % 2 == 0 else right:
                render_field(task_name, field)
        submitted = st.form_submit_button("Generate Prompt", type="primary", use_container_width=True)

    problems: list[str] = []
    if submitted:
        collected, problems = collect(task_name, task)
        if problems:
            st.session_state.prompt = ""
        else:
            st.session_state.prompt = build_prompt(task_name, task, collected)
            st.session_state.prompt_task = task_name

    if problems:
        st.error("Add or correct: " + ", ".join(problems) + ".")
    elif st.session_state.prompt:
        with st.container(border=True):
            st.subheader("Generated prompt")
            st.caption("Copy this into ChatGPT or Claude. The prompt block also has its own copy icon.")
            copy_button(st.session_state.prompt)
            st.code(st.session_state.prompt, language="markdown")
    else:
        st.info("Enter the facts for this task, then choose Generate Prompt.")
elif mode == "Bulk CSV Variance Prompts":
    st.write(
        "Upload a budget-to-actual CSV. A category is treated as revenue when it mentions revenue, "
        "income, sales, or turnover. Words such as expense, cost of, COGS, or overhead keep the line as an expense."
    )
    uploaded = st.file_uploader("Budget versus actual CSV", type=["csv"])
    if uploaded is None:
        st.info("Choose a CSV with Line_Item, Category, Department, Period, Budget, and Actual.")
    else:
        token = f"{uploaded.name}:{uploaded.size}"
        if token != st.session_state.bulk_token:
            st.session_state.bulk_token = token
            st.session_state.bulk_csv = ""
            st.session_state.bulk_report = ""
            st.session_state.bulk_count = 0
            st.session_state.bulk_skipped = []
            st.session_state.bulk_preview = []
            st.session_state.bulk_scope = ""
        frame, load_error = load_variance_csv(uploaded)
        if load_error:
            st.error(load_error)
        else:
            st.subheader("Preview")
            st.caption(f"{len(frame)} row(s) in {uploaded.name}. An optional Drivers column is included when present.")
            display = preview_frame(frame)
            st.dataframe(
                display.style.format(
                    {
                        "Budget": lambda value: value if parse_number(cell_text(value)) is None else money(parse_number(cell_text(value))),
                        "Actual": lambda value: value if parse_number(cell_text(value)) is None else money(parse_number(cell_text(value))),
                        "Variance ($)": lambda value: "—" if pd.isna(value) else money(float(value)),
                        "Variance (%)": lambda value: "—" if pd.isna(value) else f"{float(value):,.1f}%",
                    },
                    na_rep="—",
                ),
                use_container_width=True,
                hide_index=True,
            )
            unfavorable_only = st.radio(
                "Which rows get a prompt",
                ["Every row", "Unfavorable items above a dollar threshold"],
                horizontal=True,
            )
            threshold = 0.0
            if unfavorable_only.startswith("Unfavorable"):
                threshold = st.number_input(
                    "Unfavorable variance must exceed",
                    min_value=0.0,
                    value=10_000.0,
                    step=1_000.0,
                    format="%.0f",
                    help="An expense over budget, or revenue under budget, by more than this amount.",
                )
            if st.button("Generate Prompts for All Rows", type="primary"):
                result, report, skipped = build_bulk_prompts(
                    frame,
                    unfavorable_only.startswith("Unfavorable"),
                    float(threshold),
                )
                st.session_state.bulk_count = len(result)
                st.session_state.bulk_report = report
                st.session_state.bulk_csv = "" if result.empty else result.to_csv(index=False)
                st.session_state.bulk_skipped = skipped
                st.session_state.bulk_preview = result.head(3)["Prompt"].tolist() if not result.empty else []
                st.session_state.bulk_scope = (
                    f"unfavorable variances greater than {money(float(threshold))}"
                    if unfavorable_only.startswith("Unfavorable")
                    else "every valid row"
                )

            skipped_rows = st.session_state.get("bulk_skipped", [])
            if st.session_state.bulk_count:
                st.success(
                    f"Generated {st.session_state.bulk_count} prompt(s) for {st.session_state.get('bulk_scope', 'the latest run')}."
                )
                if skipped_rows:
                    with st.expander(f"{len(skipped_rows)} row(s) were not included"):
                        st.write("\n".join(skipped_rows))
                csv_col, text_col = st.columns(2)
                csv_col.download_button(
                    "Download prompts CSV",
                    data=st.session_state.bulk_csv,
                    file_name="fpa_variance_prompts.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
                text_col.download_button(
                    "Download text report",
                    data=st.session_state.bulk_report,
                    file_name="fpa_variance_prompts.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
                for number, prompt_text in enumerate(st.session_state.get("bulk_preview", []), start=1):
                    with st.expander(f"Prompt {number}"):
                        st.code(prompt_text, language="markdown")
            elif st.session_state.bulk_report.startswith("No prompts"):
                st.warning("No rows matched the current settings.")
                if skipped_rows:
                    with st.expander("Why rows were skipped"):
                        st.write("\n".join(skipped_rows))
else:
    render_bi_pipeline()
