# Copyright (c) 2026, Faircode and contributors
# For license information, please see license.txt

# import frappe


# def execute(filters=None):
# 	columns, data = [], []
# 	return columns, data




import frappe
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_daybook_data(filters)
    return columns, data


# -------------------- COLUMNS --------------------

def get_columns():
    return [
        {"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 90},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 110},
        {"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link",
         "options": "voucher_type", "width": 140},
        # {"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 220},
        # {"label": _("Income Account"), "fieldname": "income_account", "fieldtype": "Data", "width": 200},
        {"label": _("Income Amount"), "fieldname": "income_amount", "fieldtype": "Currency", "width": 130},
        {"label": _("Expense Account"), "fieldname": "expense_account", "fieldtype": "Data", "width": 200},
        {"label": _("Expense Amount"), "fieldname": "expense_amount", "fieldtype": "Currency", "width": 130},
        {"label": _("Outstanding Amount"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 130},
        # {"label": _("Cumulative Income"), "fieldname": "cumulative_income", "fieldtype": "Currency", "width": 130},
        # {"label": _("Cumulative Expense"), "fieldname": "cumulative_expense", "fieldtype": "Currency", "width": 130},
        {"label": _("Net Balance"), "fieldname": "net_balance", "fieldtype": "Currency", "width": 130},
    ]


# -------------------- DATE CONDITION --------------------

def get_date_condition(filters, field):
    condition = ""
    if filters.get("from_date"):
        condition += f" AND {field} >= %(from_date)s"
    if filters.get("to_date"):
        condition += f" AND {field} <= %(to_date)s"
    return condition


# -------------------- MAIN DATA --------------------

def get_daybook_data(filters):
    data = []
    data.extend(get_journal_entries(filters))

    # Sort by date then creation time
    data.sort(key=lambda x: (getdate(x["date"]), x.get("creation", "")))

    return process_entries(data)


# -------------------- JOURNAL ENTRY & SALES/PURCHASE INVOICES --------------------

def get_journal_entries(filters):
    date_condition = get_date_condition(filters, "je.posting_date")

    # Get Journal Entries
    query = f"""
        SELECT
            je.name AS voucher_no,
            je.posting_date AS date,
            je.creation,
            je.user_remark AS description,
            jea.debit,
            jea.credit,
            acc.account_name,
            acc.root_type,
            'Journal Entry' as voucher_type,
            jea.idx
        FROM `tabJournal Entry` je
        INNER JOIN `tabJournal Entry Account` jea ON je.name = jea.parent
        INNER JOIN `tabAccount` acc ON jea.account = acc.name
        WHERE je.docstatus = 1
        {date_condition}
        ORDER BY je.posting_date, je.creation, jea.idx
    """

    rows = frappe.db.sql(query, filters, as_dict=True)
    vouchers = {}

    for r in rows:
        if r.voucher_no not in vouchers:
            vouchers[r.voucher_no] = {
                "date": r.date,
                "creation": r.creation,
                "voucher_no": r.voucher_no,
                "voucher_type": r.voucher_type,
                # "description": r.description or "",
                "income_entries": [],
                "expense_entries": [],
                "outstanding": 0
            }

        # Income: root_type = Income with credit > 0
        if r.root_type == "Income" and r.credit > 0:
            vouchers[r.voucher_no]["income_entries"].append({
                "account": r.account_name,
                "amount": r.credit
            })

        # Expense: root_type = Expense with debit > 0
        elif r.root_type == "Expense" and r.debit > 0:
            vouchers[r.voucher_no]["expense_entries"].append({
                "account": r.account_name,
                "amount": r.debit
            })

    # Get Sales Invoices (Income)
    query_si = f"""
        SELECT
            si.name AS voucher_no,
            si.posting_date AS date,
            si.creation,
            si.title AS description,
            si.grand_total as amount,
            si.outstanding_amount as outstanding,
            acc.account_name,
            'Sales Invoice' as voucher_type
        FROM `tabSales Invoice` si
        INNER JOIN `tabAccount` acc ON si.debit_to = acc.name
        WHERE si.docstatus = 1
        {date_condition}
    """
    
    si_rows = frappe.db.sql(query_si, filters, as_dict=True)
    for r in si_rows:
        if r.voucher_no not in vouchers:
            vouchers[r.voucher_no] = {
                "date": r.date,
                "creation": r.creation,
                "voucher_no": r.voucher_no,
                "voucher_type": r.voucher_type,
                # "description": r.description or "",
                "income_entries": [],
                "expense_entries": [],
               "outstanding": r.get("outstanding", 0) if hasattr(r, 'get') else (getattr(r, 'outstanding', 0) or 0)
            }
        else:
            # update outstanding if present
            try:
                vouchers[r.voucher_no]["outstanding"] = r.get("outstanding", 0)
            except Exception:
                vouchers[r.voucher_no]["outstanding"] = getattr(r, "outstanding", 0) or 0
        
        # Add income from the revenue accounts in Sales Invoice
        vouchers[r.voucher_no]["income_entries"].append({
            "account": "Sales/Revenue",
            "amount": r.amount
        })

    # Get Purchase Invoices (Expense)
    query_pi = f"""
        SELECT
            pi.name AS voucher_no,
            pi.posting_date AS date,
            pi.creation,
            pi.title AS description,
            pi.grand_total as amount,
            pi.outstanding_amount as outstanding,
            acc.account_name,
            'Purchase Invoice' as voucher_type
        FROM `tabPurchase Invoice` pi
        INNER JOIN `tabAccount` acc ON pi.credit_to = acc.name
        WHERE pi.docstatus = 1
        {date_condition}
    """
    
    pi_rows = frappe.db.sql(query_pi, filters, as_dict=True)
    for r in pi_rows:
        if r.voucher_no not in vouchers:
            vouchers[r.voucher_no] = {
                "date": r.date,
                "creation": r.creation,
                "voucher_no": r.voucher_no,
                "voucher_type": r.voucher_type,
                "description": r.description or "",
                "income_entries": [],
                "expense_entries": [],
                "outstanding": r.get("outstanding", 0) if hasattr(r, 'get') else (getattr(r, 'outstanding', 0) or 0)
            }
        else:
            try:
                vouchers[r.voucher_no]["outstanding"] = r.get("outstanding", 0)
            except Exception:
                vouchers[r.voucher_no]["outstanding"] = getattr(r, "outstanding", 0) or 0
        
        # Add expense from Purchase Invoice
        vouchers[r.voucher_no]["expense_entries"].append({
            "account": "Purchase/Expense",
            "amount": r.amount
        })

    return list(vouchers.values())

# -------------------- PROCESS ENTRIES & TOTALS --------------------

def process_entries(entries):
    result = []
    cumulative_income = 0
    cumulative_expense = 0
    cumulative_outstanding = 0

    for e in entries:
        total_income = sum(i["amount"] for i in e["income_entries"])
        total_expense = sum(i["amount"] for i in e["expense_entries"])

        if not total_income and not total_expense:
            continue

        cumulative_income += total_income
        cumulative_expense += total_expense
        outstanding_val = e.get("outstanding", 0)
        cumulative_outstanding += outstanding_val

        result.append({
            "date": e["date"],
            "voucher_type": e["voucher_type"],
            "voucher_no": e["voucher_no"],
            "description": e.get("description", ""),
            "income_account": ", ".join(i["account"] for i in e["income_entries"]),
            "income_amount": total_income,
            "expense_account": ", ".join(i["account"] for i in e["expense_entries"]),
            "expense_amount": total_expense,
            "outstanding_amount": outstanding_val,
            # "cumulative_income": cumulative_income,
            # "cumulative_expense": cumulative_expense,
            "net_balance": cumulative_income - cumulative_expense-cumulative_outstanding
        })

    if result:
        # Append TOTAL row
        result.append({
            "description": _("TOTAL"),
            "income_amount": cumulative_income,
            "expense_amount": cumulative_expense,
            "outstanding_amount": cumulative_outstanding,
            "cumulative_income": cumulative_income,
            "cumulative_expense": cumulative_expense,
            "net_balance": cumulative_income - cumulative_expense-cumulative_outstanding
        })

    return result
