import streamlit as st
import pandas as pd
import sqlite3
import json
import os
import base64
from datetime import datetime, date
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
import io

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Nexus Billing & Operations", page_icon="🧾", layout="wide")

# --- DATABASE SETUP & SCHEMA MIGRATION ---
conn = sqlite3.connect("billing.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone TEXT, email TEXT, address TEXT, state TEXT, tax_id TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_type TEXT, doc_num TEXT, client_name TEXT, client_phone TEXT, client_gstin TEXT, client_state TEXT,
        doc_date TEXT, subtotal REAL, tax_amt REAL, grand_total REAL,
        status TEXT, items_json TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS deleted_documents (
        bin_id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_id INTEGER,
        doc_type TEXT, doc_num TEXT, client_name TEXT, client_phone TEXT, client_gstin TEXT, client_state TEXT,
        doc_date TEXT, subtotal REAL, tax_amt REAL, grand_total REAL,
        status TEXT, items_json TEXT, deleted_at TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value BLOB
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS bank_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT, bank_name TEXT, account_holder TEXT, account_number TEXT, ifsc_code TEXT, upi_id TEXT
    )
''')
conn.commit()

# Ensure older database schemas automatically catch up with required columns
try:
    cursor.execute("ALTER TABLE clients ADD COLUMN state TEXT DEFAULT 'Karnataka'")
    conn.commit()
except sqlite3.OperationalError:
    pass

try:
    cursor.execute("ALTER TABLE clients ADD COLUMN tax_id TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass

try:
    cursor.execute("ALTER TABLE documents ADD COLUMN client_gstin TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass

try:
    cursor.execute("ALTER TABLE documents ADD COLUMN client_state TEXT DEFAULT 'Karnataka'")
    conn.commit()
except sqlite3.OperationalError:
    pass

# Safe verification for deleted_documents table schema structure
cursor.execute("PRAGMA table_info(deleted_documents)")
deleted_cols = [col[1] for col in cursor.fetchall()]
if "bin_id" not in deleted_cols or "original_id" not in deleted_cols:
    cursor.execute("DROP TABLE IF EXISTS deleted_documents")
    cursor.execute('''
        CREATE TABLE deleted_documents (
            bin_id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER,
            doc_type TEXT, doc_num TEXT, client_name TEXT, client_phone TEXT, client_gstin TEXT, client_state TEXT,
            doc_date TEXT, subtotal REAL, tax_amt REAL, grand_total REAL,
            status TEXT, items_json TEXT, deleted_at TEXT
        )
    ''')
    conn.commit()

# Ensure a default bank account exists if table is empty
existing_banks = cursor.execute("SELECT COUNT(*) FROM bank_accounts").fetchone()[0]
if existing_banks == 0:
    cursor.execute('''
        INSERT INTO bank_accounts (label, bank_name, account_holder, account_number, ifsc_code, upi_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', ("Primary Account", "HDFC Bank", "Nexus Center of Events", "50200012345678", "HDFC0001234", "nexus@upi"))
    conn.commit()

# --- DEFAULT COMPANY & SETTINGS FUNCTIONS ---
DEFAULT_SETTINGS = {
    "company_name": "NEXUS CENTER OF EVENTS",
    "company_sub": "Event Planning, Execution & Corporate Management",
    "company_addr": "Bangalore, Karnataka, India",
    "company_state": "Karnataka",
    "company_phone": "+91 98765 43210",
    "company_email": "info@nexusevents.com",
    "company_gstin": "29AAAAA0000A1Z5",
    "terms_conditions": "1. Payment due within 15 days of invoice date.\n2. Quote invoice # on payment.\n3. Subject to Bangalore jurisdiction."
}

def get_setting(key, default_val):
    row = cursor.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row and row[0] is not None:
        try:
            return row[0].decode('utf-8')
        except Exception:
            return default_val
    return default_val

def save_setting(key, val):
    cursor.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val.encode('utf-8')))
    conn.commit()

# --- HELPER FUNCTIONS FOR PERSISTENT LOGO & THEME ---
def save_logo_to_db(uploaded_file):
    if uploaded_file is not None:
        logo_bytes = uploaded_file.getvalue()
        cursor.execute("REPLACE INTO settings (key, value) VALUES ('company_logo_blob', ?)", (logo_bytes,))
        conn.commit()

def get_logo_from_db():
    row = cursor.execute("SELECT value FROM settings WHERE key = 'company_logo_blob'").fetchone()
    if row and row[0]:
        return io.BytesIO(row[0])
    return None

def save_theme_to_db(theme_name):
    save_setting('invoice_theme', theme_name)

def get_theme_from_db():
    return get_setting('invoice_theme', "Modern Minimalist (Clean Slate)")

# --- TEXT WATERMARK CANVAS CALLBACK ---
def draw_watermark(canvas, doc):
    try:
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 55)
        canvas.setFillColor(colors.HexColor("#0F172A"), alpha=0.08)
        page_width, page_height = letter
        
        watermark_text = get_setting('company_name', DEFAULT_SETTINGS['company_name']).upper()
        canvas.translate(page_width / 2.0, page_height / 2.0)
        canvas.rotate(30)
        canvas.drawCentredString(0, 0, watermark_text)
        canvas.restoreState()
    except Exception:
        pass

# --- PROFESSIONAL PDF GENERATOR ENGINE ---
def generate_pdf(doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, items, subtotal, tax_amt, grand_total, bank_details=None, is_duplicate=False, theme="Modern Minimalist (Clean Slate)", is_non_tax=False):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = getSampleStyleSheet()

    if theme == "Executive Dark (Bold & Corporate)":
        PRIMARY = colors.HexColor("#111827")
        SECONDARY = colors.HexColor("#4B5563")
        ACCENT_BG = colors.HexColor("#F3F4F6")
        TEXT_DARK = colors.HexColor("#1F2937")
        BORDER_CLR = colors.HexColor("#E5E7EB")
    elif theme == "Creative Vibrant (Blue & Slate)":
        PRIMARY = colors.HexColor("#1E3A8A")
        SECONDARY = colors.HexColor("#2563EB")
        ACCENT_BG = colors.HexColor("#EFF6FF")
        TEXT_DARK = colors.HexColor("#1E293B")
        BORDER_CLR = colors.HexColor("#BFDBFE")
    elif theme == "Warm Editorial (Classic & Refined)":
        PRIMARY = colors.HexColor("#78350F")
        SECONDARY = colors.HexColor("#D97706")
        ACCENT_BG = colors.HexColor("#FFFBEB")
        TEXT_DARK = colors.HexColor("#451A03")
        BORDER_CLR = colors.HexColor("#FDE68A")
    else:  # Modern Minimalist
        PRIMARY = colors.HexColor("#0F172A")
        SECONDARY = colors.HexColor("#64748B")
        ACCENT_BG = colors.HexColor("#F8FAFC")
        TEXT_DARK = colors.HexColor("#334155")
        BORDER_CLR = colors.HexColor("#E2E8F0")

    ACCENT_RED = colors.HexColor("#DC2626")

    comp_name_str = get_setting('company_name', DEFAULT_SETTINGS['company_name'])
    comp_sub_str = get_setting('company_sub', DEFAULT_SETTINGS['company_sub'])
    comp_addr_str = get_setting('company_addr', DEFAULT_SETTINGS['company_addr'])
    comp_state_str = get_setting('company_state', DEFAULT_SETTINGS['company_state'])
    comp_phone_str = get_setting('company_phone', DEFAULT_SETTINGS['company_phone'])
    comp_email_str = get_setting('company_email', DEFAULT_SETTINGS['company_email'])
    comp_gstin_str = get_setting('company_gstin', DEFAULT_SETTINGS['company_gstin'])
    terms_str = get_setting('terms_conditions', DEFAULT_SETTINGS['terms_conditions'])

    if not bank_details:
        b_row = cursor.execute("SELECT bank_name, account_holder, account_number, ifsc_code, upi_id FROM bank_accounts LIMIT 1").fetchone()
        bank_details = b_row if b_row else ("HDFC Bank", "Nexus Center of Events", "50200012345678", "HDFC0001234", "nexus@upi")

    bank_name_str, acc_holder_str, acc_num_str, ifsc_str, upi_str = bank_details

    comp_title_style = ParagraphStyle('CompTitle', parent=styles['Heading1'], fontSize=16, leading=18, textColor=PRIMARY, fontName="Helvetica-Bold")
    comp_sub_style = ParagraphStyle('CompSub', parent=styles['Normal'], fontSize=8.5, leading=11, textColor=SECONDARY)
    doc_type_style = ParagraphStyle('DocType', parent=styles['Heading1'], fontSize=18, leading=20, textColor=SECONDARY, alignment=2, fontName="Helvetica-Bold")
    meta_label = ParagraphStyle('MetaLabel', parent=styles['Normal'], fontSize=8.5, leading=11, textColor=TEXT_DARK)
    table_hdr = ParagraphStyle('TblHdr', parent=styles['Normal'], fontSize=8.5, textColor=colors.white, fontName="Helvetica-Bold", alignment=1)
    table_cell = ParagraphStyle('TblCell', parent=styles['Normal'], fontSize=8.5, textColor=TEXT_DARK, leading=11)
    table_cell_r = ParagraphStyle('TblCellR', parent=styles['Normal'], fontSize=8.5, textColor=TEXT_DARK, leading=11, alignment=2)
    tot_label_style = ParagraphStyle('TotLabel', parent=styles['Normal'], fontSize=9, textColor=TEXT_DARK, alignment=2, fontName="Helvetica-Bold")
    tot_val_style = ParagraphStyle('TotVal', parent=styles['Normal'], fontSize=11, textColor=PRIMARY, alignment=2, fontName="Helvetica-Bold")

    logo_file = get_logo_from_db()
    logo_container = None
    if logo_file:
        try:
            logo_img = Image(logo_file, width=130, height=65)
            logo_img.hAlign = 'LEFT'
            logo_container = logo_img
        except Exception:
            logo_container = None

    dup_text = f"<font color='{ACCENT_RED.hexval()}'><b>*** DUPLICATE COPY ***</b></font><br/>" if is_duplicate else ""
    meta_info_p = [
        Paragraph(f"{dup_text}{doc_type.upper()}", doc_type_style),
        Spacer(1, 4),
        Paragraph(f"<b>Document No:</b> {doc_num}", ParagraphStyle('M1', parent=meta_label, alignment=2)),
        Paragraph(f"<b>Date:</b> {doc_date}", ParagraphStyle('M2', parent=meta_label, alignment=2)),
        Paragraph(f"<b>Place of Supply:</b> {client_state if client_state else comp_state_str}", ParagraphStyle('M3', parent=meta_label, alignment=2))
    ]

    is_delivery_challan = ("Delivery Challan" in doc_type)

    if is_delivery_challan:
        company_gstin_line = "<b>Delivery Challan (Goods Transport / Movement)</b>"
    elif is_non_tax:
        company_gstin_line = "<b>Non-Tax Invoice (Bill of Supply / Receipt)</b>"
    else:
        company_gstin_line = f"<b>GSTIN:</b> {comp_gstin_str}"

    company_info_p = [
        Paragraph(comp_name_str, comp_title_style),
        Paragraph(f"<b>{comp_sub_str}</b>", comp_sub_style),
        Paragraph(comp_addr_str, comp_sub_style),
        Paragraph(f"Phone: {comp_phone_str} | Email: {comp_email_str}", comp_sub_style),
        Paragraph(company_gstin_line, comp_sub_style)
    ]

    left_header_content = [logo_container, Spacer(1, 4), company_info_p] if logo_container else company_info_p

    header_table = Table([[left_header_content, meta_info_p]], colWidths=[310, 230])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY, spaceBefore=2, spaceAfter=8))

    c_state_str = client_state if client_state else "Karnataka"
    is_intra_state = (c_state_str.strip().lower() == comp_state_str.lower())

    client_p = [
        Paragraph("<b>BILLED / DELIVERED TO:</b>", ParagraphStyle('BTo', parent=styles['Normal'], fontSize=9, textColor=PRIMARY, fontName="Helvetica-Bold")),
        Paragraph(f"<b>{client_name}</b>", ParagraphStyle('CName', parent=styles['Normal'], fontSize=10, textColor=TEXT_DARK, fontName="Helvetica-Bold")),
        Paragraph(f"Contact: {client_phone if client_phone else 'N/A'}", meta_label),
        Paragraph(f"State: {c_state_str}", meta_label),
        Paragraph(f"<b>Client GSTIN:</b> {client_gstin if client_gstin and not is_non_tax else 'N/A'}", meta_label)
    ]
    
    if is_delivery_challan:
        gst_info_p = [
            Paragraph("<b>CHALLAN DETAILS:</b>", ParagraphStyle('TReg', parent=styles['Normal'], fontSize=9, textColor=PRIMARY, fontName="Helvetica-Bold")),
            Paragraph("Document Purpose: <b>Delivery of Goods (Non-Tax Supply)</b>", meta_label),
            Paragraph(f"Supplier Status: <b>{comp_name_str}</b>", meta_label),
            Paragraph(f"Status: <b>Active Record</b>", meta_label)
        ]
    elif is_non_tax:
        gst_info_p = [
            Paragraph("<b>INVOICE DETAILS:</b>", ParagraphStyle('TReg', parent=styles['Normal'], fontSize=9, textColor=PRIMARY, fontName="Helvetica-Bold")),
            Paragraph("Tax Type: <b>Non-Tax / Composition / Bill of Supply</b>", meta_label),
            Paragraph(f"Supplier Status: <b>Unregistered / Non-Taxable Service</b>", meta_label),
            Paragraph(f"Status: <b>Active Record</b>", meta_label)
        ]
    else:
        tax_type_str = "Intra-State GST (CGST + SGST)" if is_intra_state else "Inter-State GST (IGST)"
        gst_info_p = [
            Paragraph("<b>TAX REGIME & DETAILS:</b>", ParagraphStyle('TReg', parent=styles['Normal'], fontSize=9, textColor=PRIMARY, fontName="Helvetica-Bold")),
            Paragraph(f"Tax Treatment: <b>{tax_type_str}</b>", meta_label),
            Paragraph(f"Supplier GSTIN: <b>{comp_gstin_str}</b>", meta_label),
            Paragraph(f"Status: <b>Active Record</b>", meta_label)
        ]

    client_table = Table([[client_p, gst_info_p]], colWidths=[310, 230])
    client_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), ACCENT_BG),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_CLR),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(client_table)
    story.append(Spacer(1, 10))

    if is_non_tax:
        table_data = [[
            Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr),
            Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr),
            Paragraph("Total Amount (Rs.)", table_hdr)
        ]]
        col_w = [30, 260, 50, 90, 110]
    elif is_intra_state:
        table_data = [[
            Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr),
            Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr),
            Paragraph("Amount (Rs.)", table_hdr),
            Paragraph("CGST", table_hdr), Paragraph("SGST", table_hdr), Paragraph("Total (Rs.)", table_hdr)
        ]]
        col_w = [25, 175, 35, 65, 75, 45, 45, 80]
    else:
        table_data = [[
            Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr),
            Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr),
            Paragraph("Amount (Rs.)", table_hdr),
            Paragraph("IGST", table_hdr), Paragraph("Total (Rs.)", table_hdr)
        ]]
        col_w = [25, 205, 40, 75, 85, 55, 95]

    for idx, item in enumerate(items, start=1):
        line_sub = item['qty'] * item['rate']
        if is_non_tax:
            line_total = line_sub
            table_data.append([
                Paragraph(str(idx), table_cell), Paragraph(item['desc'], table_cell),
                Paragraph(str(item['qty']), table_cell_r), Paragraph(f"Rs. {item['rate']:,.2f}", table_cell_r),
                Paragraph(f"Rs. {line_total:,.2f}", table_cell_r)
            ])
        else:
            line_tax = line_sub * (item['tax_rate'] / 100)
            line_total = line_sub + line_tax
            if is_intra_state:
                half_tax_pct = item['tax_rate'] / 2
                table_data.append([
                    Paragraph(str(idx), table_cell), Paragraph(item['desc'], table_cell),
                    Paragraph(str(item['qty']), table_cell_r), Paragraph(f"Rs. {item['rate']:,.2f}", table_cell_r),
                    Paragraph(f"Rs. {line_sub:,.2f}", table_cell_r),
                    Paragraph(f"{half_tax_pct:.1f}%", table_cell_r), Paragraph(f"{half_tax_pct:.1f}%", table_cell_r),
                    Paragraph(f"Rs. {line_total:,.2f}", table_cell_r)
                ])
            else:
                table_data.append([
                    Paragraph(str(idx), table_cell), Paragraph(item['desc'], table_cell),
                    Paragraph(str(item['qty']), table_cell_r), Paragraph(f"Rs. {item['rate']:,.2f}", table_cell_r),
                    Paragraph(f"Rs. {line_sub:,.2f}", table_cell_r),
                    Paragraph(f"{item['tax_rate']}%", table_cell_r), Paragraph(f"Rs. {line_total:,.2f}", table_cell_r)
                ])

    item_table = Table(table_data, colWidths=col_w)
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_CLR),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 10))

    if is_non_tax:
        summary_rows = [["Grand Total:", f"Rs. {grand_total:,.2f}"]]
    else:
        summary_rows = [["Subtotal:", f"Rs. {subtotal:,.2f}"]]
        if is_intra_state:
            half_tax = tax_amt / 2
            summary_rows.append(["CGST (Central Tax):", f"Rs. {half_tax:,.2f}"])
            summary_rows.append(["SGST (State Tax):", f"Rs. {half_tax:,.2f}"])
        else:
            summary_rows.append(["IGST (Integrated Tax):", f"Rs. {tax_amt:,.2f}"])
        summary_rows.append(["Grand Total:", f"Rs. {grand_total:,.2f}"])

    summary_table_data = []
    for r in summary_rows:
        is_grand = (r[0] == "Grand Total:")
        l_style = tot_label_style if not is_grand else ParagraphStyle('GTL', parent=tot_label_style, fontSize=11, textColor=PRIMARY)
        v_style = table_cell_r if not is_grand else tot_val_style
        summary_table_data.append([Paragraph(r[0], l_style), Paragraph(r[1], v_style)])

    summary_table = Table(summary_table_data, colWidths=[380, 160])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('PADDING', (0,0), (-1,-1), 4),
        ('LINEABOVE', (0,-1), (-1,-1), 1, PRIMARY),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 12))

    formatted_terms = terms_str.replace('\n', '<br/>')
    terms_p = [
        Paragraph("<b>TERMS & CONDITIONS:</b>", ParagraphStyle('THead', parent=styles['Normal'], fontSize=8.5, textColor=PRIMARY, fontName="Helvetica-Bold")),
        Spacer(1, 2), Paragraph(formatted_terms, meta_label)
    ]

    if is_delivery_challan:
        # For Delivery Challans, omit payment details and use full width for terms or instructions
        footer_table = Table([[terms_p]], colWidths=[540])
    else:
        bank_text = (
            f"<b>Account Holder:</b> {acc_holder_str}<br/>"
            f"<b>Bank:</b> {bank_name_str} | <b>Account No:</b> {acc_num_str}<br/>"
            f"<b>IFSC:</b> {ifsc_str} | <b>UPI ID:</b> {upi_str}"
        )
        pay_p = [
            Paragraph("<b>PAYMENT / REMITTANCE DETAILS:</b>", ParagraphStyle('PHead', parent=styles['Normal'], fontSize=8.5, textColor=PRIMARY, fontName="Helvetica-Bold")),
            Spacer(1, 2), Paragraph(bank_text, meta_label)
        ]
        footer_table = Table([[pay_p, terms_p]], colWidths=[280, 260])

    footer_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), ACCENT_BG),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_CLR),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(footer_table)

    doc.build(story, onFirstPage=draw_watermark, onLaterPages=draw_watermark)
    buffer.seek(0)
    return buffer

# --- HTML PREVIEW RENDERER ---
def render_html_preview(doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, items, subtotal, tax_amt, grand_total, bank_details=None, is_duplicate=False, theme="Modern Minimalist (Clean Slate)", is_non_tax=False):
    if theme == "Executive Dark (Bold & Corporate)":
        primary_color = "#111827"
        secondary_color = "#4B5563"
        accent_bg = "#F3F4F6"
        border_clr = "#E5E7EB"
    elif theme == "Creative Vibrant (Blue & Slate)":
        primary_color = "#1E3A8A"
        secondary_color = "#2563EB"
        accent_bg = "#EFF6FF"
        border_clr = "#BFDBFE"
    elif theme == "Warm Editorial (Classic & Refined)":
        primary_color = "#78350F"
        secondary_color = "#D97706"
        accent_bg = "#FFFBEB"
        border_clr = "#FDE68A"
    else:
        primary_color = "#0F172A"
        secondary_color = "#64748B"
        accent_bg = "#F8FAFC"
        border_clr = "#E2E8F0"

    comp_name_str = get_setting('company_name', DEFAULT_SETTINGS['company_name'])
    comp_sub_str = get_setting('company_sub', DEFAULT_SETTINGS['company_sub'])
    comp_addr_str = get_setting('company_addr', DEFAULT_SETTINGS['company_addr'])
    comp_state_str = get_setting('company_state', DEFAULT_SETTINGS['company_state'])
    comp_phone_str = get_setting('company_phone', DEFAULT_SETTINGS['company_phone'])
    comp_email_str = get_setting('company_email', DEFAULT_SETTINGS['company_email'])
    comp_gstin_str = get_setting('company_gstin', DEFAULT_SETTINGS['company_gstin'])
    terms_str = get_setting('terms_conditions', DEFAULT_SETTINGS['terms_conditions'])

    if not bank_details:
        b_row = cursor.execute("SELECT bank_name, account_holder, account_number, ifsc_code, upi_id FROM bank_accounts LIMIT 1").fetchone()
        bank_details = b_row if b_row else ("HDFC Bank", "Nexus Center of Events", "50200012345678", "HDFC0001234", "nexus@upi")

    bank_name_str, acc_holder_str, acc_num_str, ifsc_str, upi_str = bank_details

    c_state_str = client_state if client_state else "Karnataka"
    is_intra_state = (c_state_str.strip().lower() == comp_state_str.lower())
    is_delivery_challan = ("Delivery Challan" in doc_type)
    
    dup_banner = f"<div style='color: #DC2626; font-weight: bold; font-size: 16px; margin-bottom: 5px;'>*** DUPLICATE COPY ***</div>" if is_duplicate else ""
    
    text_watermark_html = f"""
    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-30deg); opacity: 0.08; z-index: 10; pointer-events: none; font-size: 55px; font-weight: bold; color: {primary_color}; white-space: nowrap; font-family: Helvetica, Arial, sans-serif;">
        {comp_name_str.upper()}
    </div>
    """

    items_html = ""
    for idx, item in enumerate(items, start=1):
        line_sub = item['qty'] * item['rate']
        if is_non_tax:
            line_total = line_sub
            items_html += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: center;">{idx}</td>
                    <td style="padding: 8px; border-bottom: 1px solid {border_clr};">{item['desc']}</td>
                    <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">{item['qty']}</td>
                    <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">Rs. {item['rate']:,.2f}</td>
                    <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">Rs. {line_total:,.2f}</td>
                </tr>
            """
        else:
            line_tax = line_sub * (item['tax_rate'] / 100)
            line_total = line_sub + line_tax
            if is_intra_state:
                half_tax = item['tax_rate'] / 2
                items_html += f"""
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: center;">{idx}</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr};">{item['desc']}</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">{item['qty']}</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">Rs. {item['rate']:,.2f}</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">Rs. {line_sub:,.2f}</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">{half_tax:.1f}%</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">{half_tax:.1f}%</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">Rs. {line_total:,.2f}</td>
                    </tr>
                """
            else:
                items_html += f"""
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: center;">{idx}</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr};">{item['desc']}</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">{item['qty']}</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">Rs. {item['rate']:,.2f}</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">Rs. {line_sub:,.2f}</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">{item['tax_rate']}%</td>
                        <td style="padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;">Rs. {line_total:,.2f}</td>
                    </tr>
                """

    if is_non_tax:
        tax_summary_html = f"""
            <tr style='border-top: 2px solid {primary_color}; font-weight: bold; font-size: 14px; color: {primary_color};'>
                <td style='padding: 8px; text-align: right;'>Grand Total:</td>
                <td style='padding: 8px; text-align: right;'>Rs. {grand_total:,.2f}</td>
            </tr>
        """
    else:
        tax_summary_html = f"<tr><td style='padding: 6px; text-align: right;'>Subtotal:</td><td style='padding: 6px; text-align: right;'>Rs. {subtotal:,.2f}</td></tr>"
        if is_intra_state:
            half_tax_tot = tax_amt / 2
            tax_summary_html += f"""
                <tr><td style='padding: 6px; text-align: right;'>CGST (Central Tax):</td><td style='padding: 6px; text-align: right;'>Rs. {half_tax_tot:,.2f}</td></tr>
                <tr><td style='padding: 6px; text-align: right;'>SGST (State Tax):</td><td style='padding: 6px; text-align: right;'>Rs. {half_tax_tot:,.2f}</td></tr>
            """
        else:
            tax_summary_html += f"<tr><td style='padding: 6px; text-align: right;'>IGST (Integrated Tax):</td><td style='padding: 6px; text-align: right;'>Rs. {tax_amt:,.2f}</td></tr>"
        
        tax_summary_html += f"""
            <tr style='border-top: 2px solid {primary_color}; font-weight: bold; font-size: 14px; color: {primary_color};'>
                <td style='padding: 8px; text-align: right;'>Grand Total:</td>
                <td style='padding: 8px; text-align: right;'>Rs. {grand_total:,.2f}</td>
            </tr>
        """

    if is_non_tax:
        header_headers = f"""
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: center;">#</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: left;">Item / Service Description</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">Qty</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">Rate (Rs.)</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">Total Amount (Rs.)</th>
        """
    else:
        header_headers = f"""
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: center;">#</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: left;">Item / Service Description</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">Qty</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">Rate (Rs.)</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">Amount (Rs.)</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">CGST</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">SGST</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">Total (Rs.)</th>
        """ if is_intra_state else f"""
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: center;">#</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: left;">Item / Service Description</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">Qty</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">Rate (Rs.)</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">Amount (Rs.)</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">IGST</th>
            <th style="padding: 8px; background-color: {primary_color}; color: white; text-align: right;">Total (Rs.)</th>
        """

    if is_delivery_challan:
        company_gstin_display = "<b>Delivery Challan (Goods Transport / Movement)</b>"
        tax_treatment_display = "Challan Purpose: <b>Goods Dispatch / Movement</b>"
    elif is_non_tax:
        company_gstin_display = "<b>Non-Tax Invoice / Bill of Supply</b>"
        tax_treatment_display = "Tax Treatment: <b>Non-Taxable / Unregistered</b>"
    else:
        company_gstin_display = f"<b>GSTIN:</b> {comp_gstin_str}"
        tax_treatment_display = f"Tax Treatment: <b>{'Intra-State GST (CGST + SGST)' if is_intra_state else 'Inter-State GST (IGST)'}</b>"

    formatted_terms_html = terms_str.replace('\n', '<br/>')

    if is_delivery_challan:
        footer_block_html = f"""
        <table style="width: 100%; border-collapse: collapse; background-color: {accent_bg}; border: 0.5px solid {border_clr}; position: relative; z-index: 1;">
            <tr>
                <td style="padding: 10px; vertical-align: top; width: 100%;">
                    <div style="font-size: 10px; font-weight: bold; color: {primary_color}; margin-bottom: 3px;">TERMS & CONDITIONS:</div>
                    <div style="font-size: 10px; color: #475569; line-height: 1.4;">
                        {formatted_terms_html}
                    </div>
                </td>
            </tr>
        </table>
        """
    else:
        footer_block_html = f"""
        <table style="width: 100%; border-collapse: collapse; background-color: {accent_bg}; border: 0.5px solid {border_clr}; position: relative; z-index: 1;">
            <tr>
                <td style="padding: 10px; vertical-align: top; width: 50%;">
                    <div style="font-size: 10px; font-weight: bold; color: {primary_color}; margin-bottom: 3px;">PAYMENT / REMITTANCE DETAILS:</div>
                    <div style="font-size: 10px; color: #475569; line-height: 1.4;">
                        <b>Account Holder:</b> {acc_holder_str}<br/>
                        <b>Bank:</b> {bank_name_str} | <b>Account No:</b> {acc_num_str}<br/>
                        <b>IFSC:</b> {ifsc_str} | <b>UPI ID:</b> {upi_str}
                    </div>
                </td>
                <td style="padding: 10px; vertical-align: top; width: 50%; border-left: 0.5px solid {border_clr};">
                    <div style="font-size: 10px; font-weight: bold; color: {primary_color}; margin-bottom: 3px;">TERMS & CONDITIONS:</div>
                    <div style="font-size: 10px; color: #475569; line-height: 1.4;">
                        {formatted_terms_html}
                    </div>
                </td>
            </tr>
        </table>
        """

    html_content = f"""
    <div style="position: relative; background-color: #ffffff; color: #1E293B; padding: 30px; font-family: Helvetica, Arial, sans-serif; border: 1px solid {border_clr}; border-radius: 6px; max-width: 800px; margin: auto; overflow: hidden;">
        
        {text_watermark_html}

        <table style="width: 100%; border-collapse: collapse; position: relative; z-index: 1;">
            <tr>
                <td style="vertical-align: top; width: 55%;">
                    <div style="font-size: 18px; font-weight: bold; color: {primary_color};">{comp_name_str}</div>
                    <div style="font-size: 11px; font-weight: bold; color: {secondary_color}; margin-top: 2px;">{comp_sub_str}</div>
                    <div style="font-size: 11px; color: #475569; margin-top: 2px;">{comp_addr_str}</div>
                    <div style="font-size: 11px; color: #475569;">Phone: {comp_phone_str} | Email: {comp_email_str}</div>
                    <div style="font-size: 11px; color: #475569; margin-top: 2px;">{company_gstin_display}</div>
                </td>
                <td style="vertical-align: top; text-align: right; width: 45%;">
                    {dup_banner}
                    <div style="font-size: 20px; font-weight: bold; color: {secondary_color};">{doc_type.upper()}</div>
                    <div style="font-size: 11px; color: #1E293B; margin-top: 6px;"><b>Document No:</b> {doc_num}</div>
                    <div style="font-size: 11px; color: #1E293B;"><b>Date:</b> {doc_date}</div>
                    <div style="font-size: 11px; color: #1E293B;"><b>Place of Supply:</b> {c_state_str}</div>
                </td>
            </tr>
        </table>
        
        <hr style="border: none; border-top: 1.5px solid {primary_color}; margin: 15px 0; position: relative; z-index: 1;" />

        <table style="width: 100%; border-collapse: collapse; background-color: {accent_bg}; border: 0.5px solid {border_clr}; margin-bottom: 15px; position: relative; z-index: 1;">
            <tr>
                <td style="padding: 12px; vertical-align: top; width: 50%;">
                    <div style="font-size: 11px; font-weight: bold; color: {primary_color}; margin-bottom: 4px;">BILLED / DELIVERED TO:</div>
                    <div style="font-size: 12px; font-weight: bold; color: #0F172A;">{client_name}</div>
                    <div style="font-size: 11px; color: #475569;">Contact: {client_phone if client_phone else 'N/A'}</div>
                    <div style="font-size: 11px; color: #475569;">State: {c_state_str}</div>
                    <div style="font-size: 11px; color: #475569;"><b>Client GSTIN:</b> {client_gstin if client_gstin and not is_non_tax else 'N/A'}</div>
                </td>
                <td style="padding: 12px; vertical-align: top; width: 50%; border-left: 0.5px solid {border_clr};">
                    <div style="font-size: 11px; font-weight: bold; color: {primary_color}; margin-bottom: 4px;">DOCUMENT REGIME & DETAILS:</div>
                    <div style="font-size: 11px; color: #475569;">{tax_treatment_display}</div>
                    <div style="font-size: 11px; color: #475569; margin-top: 2px;">Supplier Status: <b>Active Record</b></div>
                </td>
            </tr>
        </table>

        <table style="width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 15px; position: relative; z-index: 1;">
            <thead>
                <tr>{header_headers}</tr>
            </thead>
            <tbody>{items_html}</tbody>
        </table>

        <table style="width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 20px; position: relative; z-index: 1;">
            <tr>
                <td style="width: 60%;"></td>
                <td style="width: 40%;">
                    <table style="width: 100%; border-collapse: collapse;">
                        {tax_summary_html}
                    </table>
                </td>
            </tr>
        </table>

        {footer_block_html}
    </div>
    """
    return html_content

# --- STREAMLIT APP NAVIGATION ---
st.title("🧾 Nexus Billing & Operations Suite")

choice = st.radio("Navigation Menu", ["Create Document", "Document History & Management", "Client Directory", "Company & Invoice Settings", "Recycle Bin"], horizontal=True)

st.sidebar.divider()
st.sidebar.subheader("🎨 Invoice Design & Branding")
current_theme = get_theme_from_db()
selected_theme = st.sidebar.selectbox(
    "Choose Invoice Theme Style", 
    ["Modern Minimalist (Clean Slate)", "Executive Dark (Bold & Corporate)", "Creative Vibrant (Blue & Slate)", "Warm Editorial (Classic & Refined)"],
    index=["Modern Minimalist (Clean Slate)", "Executive Dark (Bold & Corporate)", "Creative Vibrant (Blue & Slate)", "Warm Editorial (Classic & Refined)"].index(current_theme) if current_theme in ["Modern Minimalist (Clean Slate)", "Executive Dark (Bold & Corporate)", "Creative Vibrant (Blue & Slate)", "Warm Editorial (Classic & Refined)"] else 0
)
if selected_theme != current_theme:
    save_theme_to_db(selected_theme)
    st.sidebar.success("Theme updated successfully!")

uploaded_logo = st.sidebar.file_uploader("Upload Company Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
if uploaded_logo is not None:
    save_logo_to_db(uploaded_logo)
    st.sidebar.success("Logo saved permanently!")

# --- 1. CREATE DOCUMENT ---
if choice == "Create Document":
    st.header("📝 Create Billing Document")
    
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        doc_type = st.selectbox(
            "Document Type", 
            [
                "Tax Invoice", 
                "Non-Tax Invoice / Bill of Supply", 
                "Estimate / Quotation", 
                "Proforma Invoice", 
                "Delivery Challan"
            ]
        )
    with col_b:
        is_non_tax = ("Non-Tax" in doc_type) or ("Delivery Challan" in doc_type)
        if "Tax Invoice" in doc_type:
            doc_prefix = "INV"
        elif "Non-Tax" in doc_type:
            doc_prefix = "NONTX"
        elif "Estimate" in doc_type:
            doc_prefix = "EST"
        elif "Delivery Challan" in doc_type:
            doc_prefix = "CHL"
        else:
            doc_prefix = "PRO"
            
        doc_num = st.text_input("Document #", f"{doc_prefix}-{date.today().strftime('%Y%m%d')}-01")
    with col_c:
        doc_date = st.date_input("Date", date.today())
    with col_d:
        saved_banks = cursor.execute("SELECT id, label, bank_name, account_holder, account_number, ifsc_code, upi_id FROM bank_accounts").fetchall()
        bank_options = {f"{b[1]} ({b[2]} - {b[4][-4:]})": b[2:] for b in saved_banks}
        selected_bank_label = st.selectbox("Remittance Bank Account", list(bank_options.keys()))
        selected_bank_tuple = bank_options[selected_bank_label]

    st.subheader("Client Information")
    clients_db = cursor.execute("SELECT name, phone, state, tax_id FROM clients").fetchall()
    saved_clients = [c[0] for c in clients_db]
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        client_mode = st.radio("Client Selection", ["Existing Client", "New Client (Quick Add)"], horizontal=True)
        if client_mode == "Existing Client" and saved_clients:
            client_name = st.selectbox("Select Client", saved_clients)
            selected_client_tuple = next((c for c in clients_db if c[0] == client_name), ("", "", "Karnataka", ""))
            client_phone = selected_client_tuple[1]
            client_state = selected_client_tuple[2]
            client_gstin = selected_client_tuple[3]
        else:
            client_name = st.text_input("Client Name / Business Name")
            client_phone = st.text_input("Mobile Number")
            client_state = st.text_input("Client State", value="Karnataka")
            client_gstin = st.text_input("Client GSTIN (Optional)")
    
    st.divider()
    st.subheader("📦 Line Items")
    
    if "item_list" not in st.session_state:
        st.session_state.item_list = []

    with st.form("add_item_form", clear_on_submit=True):
        st.write("Add multiple line items one by one below:")
        if is_non_tax:
            f_col1, f_col2, f_col3 = st.columns([3, 1, 1])
            with f_col1:
                item_desc = st.text_input("Item Description / Service Name")
            with f_col2:
                item_qty = st.number_input("Qty / Days", min_value=1, value=1)
            with f_col3:
                item_rate = st.number_input("Rate (₹)", min_value=0.0, step=500.0)
            item_tax = 0.0
        else:
            f_col1, f_col2, f_col3, f_col4 = st.columns([3, 1, 1, 1])
            with f_col1:
                item_desc = st.text_input("Item Description / Service Name")
            with f_col2:
                item_qty = st.number_input("Qty / Days", min_value=1, value=1)
            with f_col3:
                item_rate = st.number_input("Rate (₹)", min_value=0.0, step=500.0)
            with f_col4:
                item_tax = st.number_input("GST Tax %", min_value=0.0, value=18.0)
        
        add_item_btn = st.form_submit_button("+ Add Line Item")
        if add_item_btn and item_desc:
            st.session_state.item_list.append({
                "desc": item_desc,
                "qty": item_qty,
                "rate": item_rate,
                "tax_rate": item_tax
            })
            st.success(f"Added '{item_desc}' to document!")

    if st.session_state.item_list:
        st.write("### Current Items in Document")
        
        for idx, item in enumerate(st.session_state.item_list):
            line_sub = item['qty'] * item['rate']
            cols = st.columns([4, 1])
            with cols[0]:
                if is_non_tax:
                    st.write(f"**{idx+1}. {item['desc']}** | Qty: {item['qty']} × ₹{item['rate']:,.2f} = **₹{line_sub:,.2f}** (Non-Tax)")
                else:
                    st.write(f"**{idx+1}. {item['desc']}** | Qty: {item['qty']} × ₹{item['rate']:,.2f} = **₹{line_sub:,.2f}** | Tax: {item['tax_rate']}%")
            with cols[1]:
                if st.button("🗑️ Remove", key=f"remove_item_{idx}"):
                    st.session_state.item_list.pop(idx)
                    st.rerun()

        if st.button("Clear All Items"):
            st.session_state.item_list = []
            st.rerun()

    subtotal = sum(i['qty'] * i['rate'] for i in st.session_state.item_list)
    tax_amt = 0.0 if is_non_tax else sum((i['qty'] * i['rate']) * (i['tax_rate'] / 100) for i in st.session_state.item_list)
    grand_total = subtotal + tax_amt

    st.divider()
    st.subheader("👁️ Live Document Preview & Export")

    if st.session_state.item_list and client_name:
        preview_html = render_html_preview(
            doc_type, doc_num, client_name, client_phone, client_gstin, client_state, 
            str(doc_date), st.session_state.item_list, subtotal, tax_amt, grand_total, 
            bank_details=selected_bank_tuple, is_duplicate=False, theme=selected_theme, is_non_tax=is_non_tax
        )
        st.components.v1.html(preview_html, height=750, scrolling=True)

        if st.button("💾 Save Document to Database"):
            items_json = json.dumps(st.session_state.item_list)
            cursor.execute('''
                INSERT INTO documents (doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (doc_type, doc_num, client_name, client_phone, client_gstin, client_state, str(doc_date), subtotal, tax_amt, grand_total, "Issued", items_json))
            conn.commit()
            st.success("Document successfully saved to database!")

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            pdf_buffer = generate_pdf(
                doc_type, doc_num, client_name, client_phone, client_gstin, client_state, 
                str(doc_date), st.session_state.item_list, subtotal, tax_amt, grand_total, 
                bank_details=selected_bank_tuple, is_duplicate=False, theme=selected_theme, is_non_tax=is_non_tax
            )
            st.download_button(
                label="📥 Download Original PDF",
                data=pdf_buffer,
                file_name=f"{doc_num}.pdf",
                mime="application/pdf"
            )
        with col_p2:
            pdf_dup_buffer = generate_pdf(
                doc_type, doc_num, client_name, client_phone, client_gstin, client_state, 
                str(doc_date), st.session_state.item_list, subtotal, tax_amt, grand_total, 
                bank_details=selected_bank_tuple, is_duplicate=True, theme=selected_theme, is_non_tax=is_non_tax
            )
            st.download_button(
                label="📥 Download Duplicate Copy PDF",
                data=pdf_dup_buffer,
                file_name=f"{doc_num}-DUPLICATE.pdf",
                mime="application/pdf"
            )
    else:
        st.info("Please add at least one line item and fill in the client name to generate the preview and export options.")

# --- 2. DOCUMENT HISTORY & MANAGEMENT ---
elif choice == "Document History & Management":
    st.header("📂 Document History & Management")
    docs = cursor.execute("SELECT id, doc_type, doc_num, client_name, doc_date, grand_total, status FROM documents").fetchall()
    
    if docs:
        df_docs = pd.DataFrame(docs, columns=["ID", "Type", "Doc #", "Client", "Date", "Grand Total (₹)", "Status"])
        st.dataframe(df_docs, use_container_width=True)
        
        doc_ids = [d[0] for d in docs]
        selected_doc_id = st.selectbox("Select Document ID for Actions", doc_ids)
        
        if selected_doc_id:
            row = cursor.execute("SELECT doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json FROM documents WHERE id = ?", (selected_doc_id,)).fetchone()
            if row:
                d_type, d_num, c_name, c_phone, c_gstin, c_state, d_date, sub, tax, g_tot, status, i_json = row
                items = json.loads(i_json)
                is_non_tax_doc = ("Non-Tax" in d_type) or ("Delivery Challan" in d_type)
                
                st.write(f"### Managing: {d_num} ({c_name})")
                
                preview_html = render_html_preview(
                    d_type, d_num, c_name, c_phone, c_gstin, c_state, d_date, items, sub, tax, g_tot, is_duplicate=False, theme=selected_theme, is_non_tax=is_non_tax_doc
                )
                st.components.v1.html(preview_html, height=600, scrolling=True)

                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    pdf_buf = generate_pdf(
                        d_type, d_num, c_name, c_phone, c_gstin, c_state, d_date, items, sub, tax, g_tot, is_duplicate=False, theme=selected_theme, is_non_tax=is_non_tax_doc
                    )
                    st.download_button("📥 Download PDF", data=pdf_buf, file_name=f"{d_num}.pdf", mime="application/pdf", key=f"dl_{selected_doc_id}")
                with col_h2:
                    if st.button("🗑️ Move to Recycle Bin", key=f"del_{selected_doc_id}"):
                        cursor.execute('''
                            INSERT INTO deleted_documents (original_id, doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json, deleted_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (selected_doc_id, d_type, d_num, c_name, c_phone, c_gstin, c_state, d_date, sub, tax, g_tot, status, i_json, str(datetime.now())))
                        cursor.execute("DELETE FROM documents WHERE id = ?", (selected_doc_id,))
                        conn.commit()
                        st.success("Document moved to Recycle Bin successfully!")
                        st.rerun()
    else:
        st.info("No documents found in history yet.")

# --- 3. CLIENT DIRECTORY ---
elif choice == "Client Directory":
    st.header("📇 Client Directory")
    
    with st.form("new_client_form", clear_on_submit=True):
        st.subheader("Add New Client Profile")
        nc_name = st.text_input("Client/Business Name")
        nc_phone = st.text_input("Phone Number")
        nc_email = st.text_input("Email Address")
        nc_address = st.text_area("Billing Address")
        nc_state = st.text_input("State", value="Karnataka")
        nc_tax = st.text_input("GSTIN / Tax ID")
        
        submitted = st.form_submit_button("Save Client")
        if submitted and nc_name:
            cursor.execute("INSERT INTO clients (name, phone, email, address, state, tax_id) VALUES (?, ?, ?, ?, ?, ?)",
                           (nc_name, nc_phone, nc_email, nc_address, nc_state, nc_tax))
            conn.commit()
            st.success(f"Client '{nc_name}' added successfully!")
            st.rerun()

    st.subheader("Saved Clients List")
    all_clients = cursor.execute("SELECT id, name, phone, email, state, tax_id FROM clients").fetchall()
    if all_clients:
        df_clients = pd.DataFrame(all_clients, columns=["ID", "Name", "Phone", "Email", "State", "GSTIN"])
        st.dataframe(df_clients, use_container_width=True)
    else:
        st.info("No client records found.")

# --- 4. COMPANY & INVOICE SETTINGS ---
elif choice == "Company & Invoice Settings":
    st.header("⚙️ Company & Invoice Customization Settings")
    st.write("Update your company profile, business details, manage multiple bank accounts, and configure default terms & conditions below.")

    with st.form("company_settings_form"):
        st.subheader("🏢 Company Information")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            cfg_name = st.text_input("Company Name", value=get_setting('company_name', DEFAULT_SETTINGS['company_name']))
            cfg_sub = st.text_input("Company Tagline / Subtitle", value=get_setting('company_sub', DEFAULT_SETTINGS['company_sub']))
            cfg_addr = st.text_input("Company Address", value=get_setting('company_addr', DEFAULT_SETTINGS['company_addr']))
        with col_s2:
            cfg_state = st.text_input("Company State", value=get_setting('company_state', DEFAULT_SETTINGS['company_state']))
            cfg_phone = st.text_input("Phone Number", value=get_setting('company_phone', DEFAULT_SETTINGS['company_phone']))
            cfg_email = st.text_input("Email Address", value=get_setting('company_email', DEFAULT_SETTINGS['company_email']))
            cfg_gstin = st.text_input("GSTIN Number", value=get_setting('company_gstin', DEFAULT_SETTINGS['company_gstin']))

        st.subheader("📜 Terms & Conditions")
        cfg_terms = st.text_area("Terms & Conditions (One per line)", value=get_setting('terms_conditions', DEFAULT_SETTINGS['terms_conditions']), height=100)

        save_settings_btn = st.form_submit_button("💾 Save Company Settings")
        if save_settings_btn:
            save_setting('company_name', cfg_name)
            save_setting('company_sub', cfg_sub)
            save_setting('company_addr', cfg_addr)
            save_setting('company_state', cfg_state)
            save_setting('company_phone', cfg_phone)
            save_setting('company_email', cfg_email)
            save_setting('company_gstin', cfg_gstin)
            save_setting('terms_conditions', cfg_terms)
            st.success("Company settings updated successfully!")

    st.divider()
    st.subheader("🏦 Manage Bank Accounts")
    st.write("Add multiple bank accounts below. You can select your preferred account when creating an invoice.")

    with st.form("add_bank_form", clear_on_submit=True):
        b_col1, b_col2 = st.columns(2)
        with b_col1:
            bank_label = st.text_input("Account Label / Nickname (e.g. Primary HDFC, Current ICICI)")
            b_name = st.text_input("Bank Name")
            b_holder = st.text_input("Account Holder Name", value="Nexus Center of Events")
        with b_col2:
            b_accnum = st.text_input("Account Number")
            b_ifsc = st.text_input("IFSC Code")
            b_upi = st.text_input("UPI ID")

        add_bank_btn = st.form_submit_button("+ Save New Bank Account")
        if add_bank_btn and bank_label and b_accnum:
            cursor.execute("INSERT INTO bank_accounts (label, bank_name, account_holder, account_number, ifsc_code, upi_id) VALUES (?, ?, ?, ?, ?, ?)",
                           (bank_label, b_name, b_holder, b_accnum, b_ifsc, b_upi))
            conn.commit()
            st.success(f"Bank account '{bank_label}' added successfully!")
            st.rerun()

    st.write("### Saved Bank Accounts")
    all_banks = cursor.execute("SELECT id, label, bank_name, account_holder, account_number, ifsc_code, upi_id FROM bank_accounts").fetchall()
    if all_banks:
        df_banks = pd.DataFrame(all_banks, columns=["ID", "Label", "Bank Name", "Holder", "Account No", "IFSC", "UPI ID"])
        st.dataframe(df_banks, use_container_width=True)
        
        bank_ids_to_del = [b[0] for b in all_banks]
        del_bank_id = st.selectbox("Select Bank ID to Delete", bank_ids_to_del, key="del_bank_select")
        if st.button("🗑️ Delete Selected Bank Account"):
            if len(all_banks) > 1:
                cursor.execute("DELETE FROM bank_accounts WHERE id = ?", (del_bank_id,))
                conn.commit()
                st.success("Bank account deleted successfully!")
                st.rerun()
            else:
                st.warning("You must keep at least one bank account in the system.")
    else:
        st.info("No bank accounts registered.")

# --- 5. RECYCLE BIN ---
elif choice == "Recycle Bin":
    st.header("🗑️ Recycle Bin (Deleted Documents)")
    del_docs = cursor.execute("SELECT bin_id, doc_num, client_name, grand_total, deleted_at FROM deleted_documents").fetchall()
    
    if del_docs:
        df_del = pd.DataFrame(del_docs, columns=["Bin ID", "Doc #", "Client", "Grand Total (₹)", "Deleted At"])
        st.dataframe(df_del, use_container_width=True)
        
        bin_ids = [d[0] for d in del_docs]
        selected_bin_id = st.selectbox("Select Bin ID to Restore or Purge", bin_ids)
        
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("♻️ Restore Document"):
                row = cursor.execute("SELECT original_id, doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json FROM deleted_documents WHERE bin_id = ?", (selected_bin_id,)).fetchone()
                if row:
                    orig_id, d_type, d_num, c_name, c_phone, c_gstin, c_state, d_date, sub, tax, g_tot, status, i_json = row
                    cursor.execute('''
                        INSERT INTO documents (id, doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (orig_id, d_type, d_num, c_name, c_phone, c_gstin, c_state, d_date, sub, tax, g_tot, status, i_json))
                    cursor.execute("DELETE FROM deleted_documents WHERE bin_id = ?", (selected_bin_id,))
                    conn.commit()
                    st.success("Document restored successfully!")
                    st.rerun()
        with col_b2:
            if st.button("🔥 Permanently Delete"):
                cursor.execute("DELETE FROM deleted_documents WHERE bin_id = ?", (selected_bin_id,))
                conn.commit()
                st.success("Document permanently purged from database!")
                st.rerun()
    else:
        st.info("Recycle bin is empty.")
