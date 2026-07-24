import streamlit as st
import pandas as pd
import sqlite3
import json
import os
import base64
from datetime import datetime, date
from reportlab.lib.pagesizes import A4, letter, legal
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

existing_banks = cursor.execute("SELECT COUNT(*) FROM bank_accounts").fetchone()[0]
if existing_banks == 0:
    cursor.execute('''
        INSERT INTO bank_accounts (label, bank_name, account_holder, account_number, ifsc_code, upi_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', ("Primary Account", "HDFC Bank", "Nexus Center of Events", "50200012345678", "HDFC0001234", "nexus@upi"))
    conn.commit()

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
    return get_setting('invoice_theme', "Editorial Dark & Asymmetric")

PAGE_SIZE_MAP = {
    "A4": (A4, "210mm", "297mm"),
    "Letter": (letter, "8.5in", "11in"),
    "Legal": (legal, "8.5in", "14in")
}

def get_theme_palette(theme):
    if theme == "Midnight Executive":
        return {"bg": "#090A0F", "sidebar": "#12141C", "primary": "#D4AF37", "text": "#F3F4F6", "muted": "#9CA3AF", "border": "#27272A"}
    elif theme == "Cyber-Industrial Monolith":
        return {"bg": "#0B0F19", "sidebar": "#111827", "primary": "#06B6D4", "text": "#F8FAFC", "muted": "#94A3B8", "border": "#1E293B"}
    elif theme == "Neo-Corporate Minimalist":
        return {"bg": "#FFFFFF", "sidebar": "#F8FAFC", "primary": "#2563EB", "text": "#0F172A", "muted": "#64748B", "border": "#E2E8F0"}
    elif theme == "Warm Editorial & Heritage":
        return {"bg": "#FDFBF7", "sidebar": "#F4F1EA", "primary": "#78350F", "text": "#292524", "muted": "#78716C", "border": "#E7E5E4"}
    elif theme == "Modern Minimalist (Clean Slate)":
        return {"bg": "#FFFFFF", "sidebar": "#F1F5F9", "primary": "#0F172A", "text": "#1E293B", "muted": "#64748B", "border": "#CBD5E1"}
    elif theme == "Executive Dark (Bold & Corporate)":
        return {"bg": "#111827", "sidebar": "#1F2937", "primary": "#60A5FA", "text": "#FFFFFF", "muted": "#9CA3AF", "border": "#374151"}
    elif theme == "Creative Vibrant (Blue & Slate)":
        return {"bg": "#0F172A", "sidebar": "#1E293B", "primary": "#3B82F6", "text": "#F8FAFC", "muted": "#94A3B8", "border": "#334155"}
    else: # Default: Editorial Dark & Asymmetric
        return {"bg": "#0F172A", "sidebar": "#1E293B", "primary": "#3B82F6", "text": "#F8FAFC", "muted": "#94A3B8", "border": "#334155"}

def make_watermark_callback(page_dimensions):
    def draw_watermark(canvas, doc):
        try:
            canvas.saveState()
            canvas.setFont("Helvetica-Bold", 45)
            canvas.setFillColor(colors.HexColor("#FFFFFF"), alpha=0.02)
            page_width, page_height = page_dimensions
            watermark_text = get_setting('company_name', DEFAULT_SETTINGS['company_name']).upper()
            canvas.translate(page_width / 2.0, page_height / 2.0)
            canvas.rotate(30)
            canvas.drawCentredString(0, 0, watermark_text)
            canvas.restoreState()
        except Exception:
            pass
    return draw_watermark

def generate_pdf(doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, items, subtotal, tax_amt, grand_total, bank_details=None, is_duplicate=False, theme="Editorial Dark & Asymmetric", is_non_tax=False, page_size_name="A4"):
    buffer = io.BytesIO()
    pagesize_tuple, _, _ = PAGE_SIZE_MAP.get(page_size_name, PAGE_SIZE_MAP["A4"])
    
    doc = SimpleDocTemplate(buffer, pagesize=pagesize_tuple, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()

    palette = get_theme_palette(theme)
    PRIMARY = colors.HexColor(palette["primary"])
    BG_DARK = colors.HexColor(palette["bg"])
    SIDEBAR_BG = colors.HexColor(palette["sidebar"])
    TEXT_MAIN = colors.HexColor(palette["text"])
    TEXT_MUTED = colors.HexColor(palette["muted"])
    BORDER_CLR = colors.HexColor(palette["border"])
    ACCENT_RED = colors.HexColor("#DC2626")

    comp_name_str = get_setting('company_name', DEFAULT_SETTINGS['company_name'])
    comp_sub_str = get_setting('company_sub', DEFAULT_SETTINGS['company_sub'])
    comp_state_str = get_setting('company_state', DEFAULT_SETTINGS['company_state'])

    if not bank_details:
        b_row = cursor.execute("SELECT bank_name, account_holder, account_number, ifsc_code, upi_id FROM bank_accounts LIMIT 1").fetchone()
        bank_details = b_row if b_row else ("HDFC Bank", "Nexus Center of Events", "50200012345678", "HDFC0001234", "nexus@upi")

    comp_title_style = ParagraphStyle('CompTitle', parent=styles['Heading1'], fontSize=14, leading=17, textColor=TEXT_MAIN, fontName="Helvetica-Bold")
    comp_sub_style = ParagraphStyle('CompSub', parent=styles['Normal'], fontSize=8, leading=11, textColor=TEXT_MUTED)
    doc_type_style = ParagraphStyle('DocType', parent=styles['Heading1'], fontSize=16, leading=19, textColor=TEXT_MAIN, alignment=2, fontName="Helvetica-Bold")
    table_hdr = ParagraphStyle('TblHdr', parent=styles['Normal'], fontSize=8.5, textColor=TEXT_MUTED, fontName="Helvetica-Bold")
    table_cell = ParagraphStyle('TblCell', parent=styles['Normal'], fontSize=8.5, textColor=TEXT_MAIN, leading=11, fontName="Helvetica")
    table_cell_r = ParagraphStyle('TblCellR', parent=styles['Normal'], fontSize=8.5, textColor=TEXT_MAIN, leading=11, alignment=2, fontName="Helvetica")
    tot_label_style = ParagraphStyle('TotLabel', parent=styles['Normal'], fontSize=9, textColor=TEXT_MUTED, alignment=2)
    tot_val_style = ParagraphStyle('TotVal', parent=styles['Normal'], fontSize=11, textColor=TEXT_MAIN, alignment=2, fontName="Helvetica-Bold")

    dup_text = f"<font color='{ACCENT_RED.hexval()}'><b>*** DUPLICATE COPY ***</b></font><br/>" if is_duplicate else ""
    
    sidebar_content = [
        Paragraph(comp_name_str, comp_title_style),
        Spacer(1, 4),
        Paragraph(comp_sub_str, comp_sub_style),
        Spacer(1, 15),
        Paragraph("<b>DOCUMENT NO:</b>", comp_sub_style),
        Paragraph(doc_num, table_cell),
        Spacer(1, 8),
        Paragraph("<b>DATE:</b>", comp_sub_style),
        Paragraph(str(doc_date), table_cell),
        Spacer(1, 8),
        Paragraph("<b>SUPPLIER STATE:</b>", comp_sub_style),
        Paragraph(comp_state_str, table_cell)
    ]

    main_header_content = [
        Paragraph(f"{dup_text}{doc_type.upper()}", doc_type_style),
        Spacer(1, 4),
        Paragraph(f"<b>Billed To:</b> {client_name} ({client_state if client_state else 'Karnataka'})", ParagraphStyle('M1', parent=styles['Normal'], fontSize=9, textColor=TEXT_MUTED, alignment=2))
    ]

    header_table = Table([[sidebar_content, main_header_content]], colWidths=[200, 335])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,0), SIDEBAR_BG),
        ('BACKGROUND', (1,0), (1,0), BG_DARK),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 12),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CLR),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))

    if is_non_tax:
        table_data = [[Paragraph("Item / Service Description", table_hdr), Paragraph("Qty", table_hdr), Paragraph("Amount (Rs.)", table_hdr)]]
        col_w = [355, 60, 120]
    else:
        table_data = [[Paragraph("Item / Service Description", table_hdr), Paragraph("Qty", table_hdr), Paragraph("Rate", table_hdr), Paragraph("Total", table_hdr)]]
        col_w = [295, 50, 90, 100]

    for idx, item in enumerate(items, start=1):
        line_sub = item['qty'] * item['rate']
        if is_non_tax:
            table_data.append([Paragraph(item['desc'], table_cell), Paragraph(str(item['qty']), table_cell_r), Paragraph(f"Rs. {line_sub:,.2f}", table_cell_r)])
        else:
            line_tax = line_sub * (item['tax_rate'] / 100)
            line_total = line_sub + line_tax
            table_data.append([Paragraph(item['desc'], table_cell), Paragraph(str(item['qty']), table_cell_r), Paragraph(f"Rs. {item['rate']:,.2f}", table_cell_r), Paragraph(f"Rs. {line_total:,.2f}", table_cell_r)])

    item_table = Table(table_data, colWidths=col_w)
    item_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LINEBELOW', (0,0), (-1,0), 1, PRIMARY),
        ('LINEBELOW', (0,1), (-1,-1), 0.5, BORDER_CLR),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 12))

    summary_rows = [["Subtotal:", f"Rs. {subtotal:,.2f}"]]
    if not is_non_tax:
        summary_rows.append(["Tax Amount:", f"Rs. {tax_amt:,.2f}"])
    summary_rows.append(["Grand Total:", f"Rs. {grand_total:,.2f}"])

    summary_table_data = []
    for r in summary_rows:
        is_grand = ("Grand Total" in r[0])
        l_style = tot_label_style if not is_grand else ParagraphStyle('GTL', parent=tot_label_style, fontSize=10, textColor=PRIMARY)
        v_style = table_cell_r if not is_grand else tot_val_style
        summary_table_data.append([Paragraph(r[0], l_style), Paragraph(r[1], v_style)])

    summary_table = Table(summary_table_data, colWidths=[375, 160])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('PADDING', (0,0), (-1,-1), 4),
        ('LINEABOVE', (0,-1), (-1,-1), 1, PRIMARY),
    ]))
    story.append(summary_table)

    watermark_cb = make_watermark_callback(pagesize_tuple)
    doc.build(story, onFirstPage=watermark_cb, onLaterPages=watermark_cb)
    buffer.seek(0)
    return buffer

def render_html_preview(doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, items, subtotal, tax_amt, grand_total, bank_details=None, is_duplicate=False, theme="Editorial Dark & Asymmetric", is_non_tax=False, page_size_name="A4"):
    comp_name_str = get_setting('company_name', DEFAULT_SETTINGS['company_name'])
    comp_sub_str = get_setting('company_sub', DEFAULT_SETTINGS['company_sub'])
    comp_state_str = get_setting('company_state', DEFAULT_SETTINGS['company_state'])
    
    palette = get_theme_palette(theme)
    
    dup_banner = f"<div style='color: #DC2626; font-weight: bold; font-size: 14px; margin-bottom: 6px;'>*** DUPLICATE COPY ***</div>" if is_duplicate else ""

    items_html = ""
    for idx, item in enumerate(items, start=1):
        line_sub = item['qty'] * item['rate']
        if is_non_tax:
            items_html += f"""
                <tr>
                    <td style="padding: 12px 0; border-bottom: 1px solid {palette['border']}; font-family: sans-serif; color: {palette['text']};">{item['desc']}</td>
                    <td style="padding: 12px 0; border-bottom: 1px solid {palette['border']}; text-align: right; color: {palette['text']};">{item['qty']}</td>
                    <td style="padding: 12px 0; border-bottom: 1px solid {palette['border']}; text-align: right; font-weight: 600; color: {palette['text']};">Rs. {line_sub:,.2f}</td>
                </tr>
            """
        else:
            line_tax = line_sub * (item['tax_rate'] / 100)
            line_total = line_sub + line_tax
            items_html += f"""
                <tr>
                    <td style="padding: 12px 0; border-bottom: 1px solid {palette['border']}; font-family: sans-serif; color: {palette['text']};">{item['desc']}</td>
                    <td style="padding: 12px 0; border-bottom: 1px solid {palette['border']}; text-align: right; color: {palette['text']};">{item['qty']}</td>
                    <td style="padding: 12px 0; border-bottom: 1px solid {palette['border']}; text-align: right; color: {palette['text']};">Rs. {item['rate']:,.2f}</td>
                    <td style="padding: 12px 0; border-bottom: 1px solid {palette['border']}; text-align: right; font-weight: 600; color: {palette['text']};">Rs. {line_total:,.2f}</td>
                </tr>
            """

    header_th = f"""
        <th style="text-align: left; font-size: 0.8rem; text-transform: uppercase; color: {palette['muted']}; padding-bottom: 10px; border-bottom: 1px solid {palette['border']};">Item Description</th>
        <th style="text-align: right; font-size: 0.8rem; text-transform: uppercase; color: {palette['muted']}; padding-bottom: 10px; border-bottom: 1px solid {palette['border']};">Qty</th>
        <th style="text-align: right; font-size: 0.8rem; text-transform: uppercase; color: {palette['muted']}; padding-bottom: 10px; border-bottom: 1px solid {palette['border']};">Amount</th>
    """ if is_non_tax else f"""
        <th style="text-align: left; font-size: 0.8rem; text-transform: uppercase; color: {palette['muted']}; padding-bottom: 10px; border-bottom: 1px solid {palette['border']};">Item Description</th>
        <th style="text-align: right; font-size: 0.8rem; text-transform: uppercase; color: {palette['muted']}; padding-bottom: 10px; border-bottom: 1px solid {palette['border']};">Qty</th>
        <th style="text-align: right; font-size: 0.8rem; text-transform: uppercase; color: {palette['muted']}; padding-bottom: 10px; border-bottom: 1px solid {palette['border']};">Rate</th>
        <th style="text-align: right; font-size: 0.8rem; text-transform: uppercase; color: {palette['muted']}; padding-bottom: 10px; border-bottom: 1px solid {palette['border']};">Total</th>
    """

    html_content = f"""
    <div style="max-width: 850px; margin: auto; background: {palette['bg']}; color: {palette['text']}; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; border-radius: 12px; overflow: hidden; display: grid; grid-template-columns: 280px 1fr; border-left: 6px solid {palette['primary']}; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.3);">
        <div style="background: {palette['sidebar']}; padding: 35px 25px; border-right: 1px solid {palette['border']}; display: flex; flex-direction: column; justify-content: space-between;">
            <div>
                <h1 style="font-size: 1.35rem; font-weight: 800; margin: 0 0 8px 0; color: {palette['text']}; text-transform: uppercase;">{comp_name_str}</h1>
                <p style="font-size: 0.8rem; color: {palette['muted']}; line-height: 1.4; margin: 0 0 25px 0;">{comp_sub_str}</p>
                
                <div style="font-size: 0.75rem; text-transform: uppercase; color: {palette['muted']}; margin-bottom: 4px;">Document Number</div>
                <div style="font-size: 0.9rem; font-weight: 600; margin-bottom: 16px; color: {palette['text']};">{doc_num}</div>

                <div style="font-size: 0.75rem; text-transform: uppercase; color: {palette['muted']}; margin-bottom: 4px;">Issue Date</div>
                <div style="font-size: 0.9rem; font-weight: 600; margin-bottom: 16px; color: {palette['text']};">{doc_date}</div>

                <div style="font-size: 0.75rem; text-transform: uppercase; color: {palette['muted']}; margin-bottom: 4px;">Supplier State</div>
                <div style="font-size: 0.9rem; font-weight: 600; color: {palette['text']};">{comp_state_str}</div>
            </div>
            <div style="font-size: 0.75rem; color: {palette['muted']}; margin-top: 30px;">
                Secure Digital Billing Suite<br/>Bangalore, Karnataka
            </div>
        </div>

        <div style="padding: 35px; display: flex; flex-direction: column; justify-content: space-between; position: relative;">
            <div style="position: absolute; right: 20px; bottom: 40px; font-size: 5rem; font-weight: 900; color: rgba(150, 150, 150, 0.05); pointer-events: none; text-transform: uppercase;">NEXUS</div>
            
            <div>
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 30px; border-bottom: 1px solid {palette['border']}; padding-bottom: 15px;">
                    <div>
                        {dup_banner}
                        <h2 style="font-size: 1.8rem; font-weight: 700; margin: 0; letter-spacing: -0.03em; color: {palette['text']};">{doc_type.upper()}</h2>
                    </div>
                    <div>
                        <span style="display: inline-flex; align-items: center; padding: 6px 14px; border-radius: 9999px; background-color: rgba(59, 130, 246, 0.15); color: {palette['primary']}; font-size: 0.75rem; font-weight: 600;">Verified &amp; Processed</span>
                    </div>
                </div>

                <div style="margin-bottom: 25px;">
                    <div style="font-size: 0.75rem; text-transform: uppercase; color: {palette['muted']}; margin-bottom: 4px;">Billed To</div>
                    <div style="font-size: 1rem; font-weight: 600; color: {palette['text']};">{client_name}</div>
                    <div style="font-size: 0.85rem; color: {palette['muted']}; margin-top: 2px;">State: {client_state if client_state else 'Karnataka'}</div>
                </div>

                <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                    <thead>
                        <tr>{header_th}</tr>
                    </thead>
                    <tbody>
                        {items_html}
                    </tbody>
                </table>
            </div>

            <div style="display: flex; justify-content: flex-end; margin-top: 20px;">
                <div style="width: 250px; border-left: 3px solid {palette['primary']}; padding-left: 15px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.85rem; color: {palette['muted']};">
                        <span>Subtotal</span>
                        <span>Rs. {subtotal:,.2f}</span>
                    </div>
                    {"<div style='display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.85rem; color: " + palette['muted'] + ";'><span>Tax</span><span>Rs. " + f"{tax_amt:,.2f}" + "</span></div>" if not is_non_tax else ""}
                    <div style="display: flex; justify-content: space-between; margin-top: 10px; padding-top: 10px; border-top: 1px solid {palette['border']}; font-size: 1.1rem; font-weight: 700; color: {palette['text']};">
                        <span>Total Due</span>
                        <span>Rs. {grand_total:,.2f}</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
    return html_content

st.title("🧾 Nexus Billing & Operations Suite")

choice = st.radio("Navigation Menu", ["Create Document", "Document History & Management", "Client Directory", "Company & Invoice Settings", "Recycle Bin"], horizontal=True)

st.sidebar.divider()
st.sidebar.subheader("🎨 Invoice Design & Branding")
current_theme = get_theme_from_db()
selected_theme = st.sidebar.selectbox(
    "Choose Invoice Theme Style", 
    [
        "Editorial Dark & Asymmetric",
        "Modern Minimalist (Clean Slate)",
        "Executive Dark (Bold & Corporate)",
        "Creative Vibrant (Blue & Slate)",
        "Neo-Corporate Minimalist", 
        "Midnight Executive", 
        "Cyber-Industrial Monolith", 
        "Warm Editorial & Heritage"
    ],
    index=0
)
if selected_theme != current_theme:
    save_theme_to_db(selected_theme)
    st.sidebar.success("Theme updated successfully!")

selected_page_size = st.sidebar.selectbox("📄 Print Page Size", ["A4", "Letter", "Legal"], index=0)

uploaded_logo = st.sidebar.file_uploader("Upload Company Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
if uploaded_logo is not None:
    save_logo_to_db(uploaded_logo)
    st.sidebar.success("Logo saved permanently!")

if choice == "Create Document":
    st.header("📝 Create Billing Document")
    
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        doc_type = st.selectbox("Document Type", ["Tax Invoice", "Non-Tax Invoice / Bill of Supply", "Estimate / Quotation", "Proforma Invoice", "Delivery Challan"])
    with col_b:
        is_non_tax = ("Non-Tax" in doc_type) or ("Delivery Challan" in doc_type)
        doc_prefix = "INV" if "Tax Invoice" in doc_type else ("NONTX" if "Non-Tax" in doc_type else ("EST" if "Estimate" in doc_type else ("CHL" if "Delivery Challan" in doc_type else "PRO")))
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
            st.session_state.item_list.append({"desc": item_desc, "qty": item_qty, "rate": item_rate, "tax_rate": item_tax})
            st.success(f"Added '{item_desc}' to document!")

    if st.session_state.item_list:
        st.write("### Current Items in Document")
        for idx, item in enumerate(st.session_state.item_list):
            line_sub = item['qty'] * item['rate']
            cols = st.columns([4, 1])
            with cols[0]:
                st.write(f"**{idx+1}. {item['desc']}** | Qty: {item['qty']} × ₹{item['rate']:,.2f} = **₹{line_sub:,.2f}**")
            with cols[1]:
                if st.button("🗑️ Remove", key=f"remove_item_{idx}"):
                    st.session_state.item_list.pop(idx)
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
            bank_details=selected_bank_tuple, is_duplicate=False, theme=selected_theme, is_non_tax=is_non_tax, page_size_name=selected_page_size
        )
        st.components.v1.html(preview_html, height=850, scrolling=True)

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
                bank_details=selected_bank_tuple, is_duplicate=False, theme=selected_theme, is_non_tax=is_non_tax, page_size_name=selected_page_size
            )
            st.download_button(label=f"📥 Download Original PDF ({selected_page_size})", data=pdf_buffer, file_name=f"{doc_num}.pdf", mime="application/pdf")
        with col_p2:
            pdf_dup_buffer = generate_pdf(
                doc_type, doc_num, client_name, client_phone, client_gstin, client_state, 
                str(doc_date), st.session_state.item_list, subtotal, tax_amt, grand_total, 
                bank_details=selected_bank_tuple, is_duplicate=True, theme=selected_theme, is_non_tax=is_non_tax, page_size_name=selected_page_size
            )
            st.download_button(label=f"📥 Download Duplicate Copy PDF ({selected_page_size})", data=pdf_dup_buffer, file_name=f"{doc_num}-DUPLICATE.pdf", mime="application/pdf")

elif choice == "Document History & Management":
    st.header("📂 Document History & Management")
    docs = cursor.execute("SELECT id, doc_type, doc_num, client_name, doc_date, grand_total, status FROM documents").fetchall()
    if docs:
        df_docs = pd.DataFrame(docs, columns=["ID", "Type", "Doc #", "Client", "Date", "Grand Total (₹)", "Status"])
        st.dataframe(df_docs, use_container_width=True)
    else:
        st.info("No documents found in history yet.")

elif choice == "Client Directory":
    st.header("📇 Client Directory")
    with st.form("new_client_form", clear_on_submit=True):
        nc_name = st.text_input("Client/Business Name")
        nc_phone = st.text_input("Phone Number")
        nc_email = st.text_input("Email Address")
        nc_address = st.text_area("Billing Address")
        nc_state = st.text_input("State", value="Karnataka")
        nc_tax = st.text_input("GSTIN / Tax ID")
        if st.form_submit_button("Save Client") and nc_name:
            cursor.execute("INSERT INTO clients (name, phone, email, address, state, tax_id) VALUES (?, ?, ?, ?, ?, ?)", (nc_name, nc_phone, nc_email, nc_address, nc_state, nc_tax))
            conn.commit()
            st.success("Client added successfully!")
            st.rerun()

elif choice == "Company & Invoice Settings":
    st.header("⚙️ Company Settings")
    with st.form("company_settings_form"):
        cfg_name = st.text_input("Company Name", value=get_setting('company_name', DEFAULT_SETTINGS['company_name']))
        cfg_sub = st.text_input("Tagline", value=get_setting('company_sub', DEFAULT_SETTINGS['company_sub']))
        if st.form_submit_button("Save Settings"):
            save_setting('company_name', cfg_name)
            save_setting('company_sub', cfg_sub)
            st.success("Settings saved!")

elif choice == "Recycle Bin":
    st.header("🗑️ Recycle Bin")
    del_docs = cursor.execute("SELECT bin_id, doc_num, client_name, grand_total, deleted_at FROM deleted_documents").fetchall()
    if del_docs:
        df_del = pd.DataFrame(del_docs, columns=["Bin ID", "Doc #", "Client", "Grand Total (₹)", "Deleted At"])
        st.dataframe(df_del, use_container_width=True)
    else:
        st.info("Recycle bin is empty.")
