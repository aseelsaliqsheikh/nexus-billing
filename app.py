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
import io
import streamlit_authenticator as stauth

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Nexus Billing & Operations", page_icon="🧾", layout="wide")

# --- USER CREDENTIALS & AUTHENTICATION SETUP ---
credentials = {
    "usernames": {
        "admin": {
            "email": "admin@nexus.com",
            "first_name": "Admin",
            "last_name": "User",
            "password": "your_secure_password_here" 
        }
    }
}

authenticator = stauth.Authenticate(
    credentials,
    cookie_name="nexus_billing_cookie",
    key="nexus_secret_signature_key",
    cookie_expiry_days=30
)

# --- TRACK ACTIVE SESSIONS GLOBALLY ---
if "active_sessions" not in st.session_state:
    st.session_state["active_sessions"] = set()

# --- INITIALIZE SESSION STATE ITEMS EARLY ---
if "items" not in st.session_state or not isinstance(st.session_state.items, list) or len(st.session_state.items) == 0:
    st.session_state.items = [{'desc': '', 'qty': 1.0, 'rate': 0.0, 'tax_rate': 18.0}]

# --- LOGIN SCREEN ---
try:
    authenticator.login()
except Exception as e:
    st.error(e)

authentication_status = st.session_state.get("authentication_status")

if authentication_status == False:
    st.error("Username/password is incorrect")
elif authentication_status == None:
    st.warning("Please enter your username and password")
    
    try:
        username_forgot_pw, email_forgot_pw, new_random_password = authenticator.forgot_password("Forgot password?")
        if username_forgot_pw:
            st.success("New password generated successfully!")
            st.info(f"Temporary Password (Dev View): {new_random_password}")
        elif username_forgot_pw == False:
            st.error("Username not found")
    except Exception:
        pass

elif authentication_status == True:
    name = st.session_state.get("name")
    username = st.session_state.get("username")
    
    st.session_state["active_sessions"].add(st.session_state.get('token', 'active_user_session'))

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

    try: cursor.execute("ALTER TABLE clients ADD COLUMN state TEXT DEFAULT 'Karnataka'"); conn.commit()
    except sqlite3.OperationalError: pass

    try: cursor.execute("ALTER TABLE clients ADD COLUMN tax_id TEXT"); conn.commit()
    except sqlite3.OperationalError: pass

    try: cursor.execute("ALTER TABLE documents ADD COLUMN client_gstin TEXT"); conn.commit()
    except sqlite3.OperationalError: pass

    try: cursor.execute("ALTER TABLE documents ADD COLUMN client_state TEXT DEFAULT 'Karnataka'"); conn.commit()
    except sqlite3.OperationalError: pass

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
            try: return row[0].decode('utf-8')
            except Exception: return default_val
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
        if row and row[0]: return io.BytesIO(row[0])
        return None

    def save_theme_to_db(theme_name): save_setting('invoice_theme', theme_name)
    def get_theme_from_db(): return get_setting('invoice_theme', "Modern Minimalist (Clean Slate)")

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

    def generate_pdf(doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, items, subtotal, tax_amt, grand_total, bank_details=None, is_duplicate=False, theme="Modern Minimalist (Clean Slate)", is_non_tax=False):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        story = []
        styles = getSampleStyleSheet()

        if theme == "Executive Dark (Bold & Corporate)":
            PRIMARY, SECONDARY, ACCENT_BG, TEXT_DARK, BORDER_CLR = colors.HexColor("#111827"), colors.HexColor("#4B5563"), colors.HexColor("#F3F4F6"), colors.HexColor("#1F2937"), colors.HexColor("#E5E7EB")
        elif theme == "Creative Vibrant (Blue & Slate)":
            PRIMARY, SECONDARY, ACCENT_BG, TEXT_DARK, BORDER_CLR = colors.HexColor("#1E3A8A"), colors.HexColor("#2563EB"), colors.HexColor("#EFF6FF"), colors.HexColor("#1E293B"), colors.HexColor("#BFDBFE")
        elif theme == "Warm Editorial (Classic & Refined)":
            PRIMARY, SECONDARY, ACCENT_BG, TEXT_DARK, BORDER_CLR = colors.HexColor("#78350F"), colors.HexColor("#D97706"), colors.HexColor("#FFFBEB"), colors.HexColor("#451A03"), colors.HexColor("#FDE68A")
        else:
            PRIMARY, SECONDARY, ACCENT_BG, TEXT_DARK, BORDER_CLR = colors.HexColor("#0F172A"), colors.HexColor("#64748B"), colors.HexColor("#F8FAFC"), colors.HexColor("#334155"), colors.HexColor("#E2E8F0")

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
        logo_container = Image(logo_file, width=130, height=65) if logo_file else None
        if logo_container:
            logo_container.hAlign = 'LEFT'

        dup_text = f"<font color='{ACCENT_RED.hexval()}'><b>*** DUPLICATE COPY ***</b></font><br/>" if is_duplicate else ""
        meta_info_p = [
            Paragraph(f"{dup_text}{doc_type.upper()}", doc_type_style),
            Spacer(1, 4),
            Paragraph(f"<b>Document No:</b> {doc_num}", ParagraphStyle('M1', parent=meta_label, alignment=2)),
            Paragraph(f"<b>Date:</b> {doc_date}", ParagraphStyle('M2', parent=meta_label, alignment=2)),
            Paragraph(f"<b>Place of Supply:</b> {client_state if client_state else comp_state_str}", ParagraphStyle('M3', parent=meta_label, alignment=2))
        ]

        company_gstin_line = f"<b>GSTIN:</b> {comp_gstin_str}" if not is_non_tax else "<b>Non-Tax Invoice (Bill of Supply / Receipt)</b>"
        company_info_p = [
            Paragraph(comp_name_str, comp_title_style),
            Paragraph(f"<b>{comp_sub_str}</b>", comp_sub_style),
            Paragraph(comp_addr_str, comp_sub_style),
            Paragraph(f"Phone: {comp_phone_str} | Email: {comp_email_str}", comp_sub_style),
            Paragraph(company_gstin_line, comp_sub_style)
        ]

        left_header_content = [logo_container, Spacer(1, 4), company_info_p] if logo_container else company_info_p
        header_table = Table([[left_header_content, meta_info_p]], colWidths=[310, 230])
        header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0)]))
        story.append(header_table)
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY, spaceBefore=2, spaceAfter=8))

        c_state_str = client_state if client_state else "Karnataka"
        is_intra_state = (c_state_str.strip().lower() == comp_state_str.lower())

        client_p = [
            Paragraph("<b>BILLED TO:</b>", ParagraphStyle('BTo', parent=styles['Normal'], fontSize=9, textColor=PRIMARY, fontName="Helvetica-Bold")),
            Paragraph(f"<b>{client_name}</b>", ParagraphStyle('CName', parent=styles['Normal'], fontSize=10, textColor=TEXT_DARK, fontName="Helvetica-Bold")),
            Paragraph(f"Contact: {client_phone if client_phone else 'N/A'}", meta_label),
            Paragraph(f"State: {c_state_str}", meta_label),
            Paragraph(f"<b>Client GSTIN:</b> {client_gstin if client_gstin and not is_non_tax else 'N/A'}", meta_label)
        ]
        
        if not is_non_tax:
            tax_type_str = "Intra-State GST (CGST + SGST)" if is_intra_state else "Inter-State GST (IGST)"
            gst_info_p = [
                Paragraph("<b>TAX REGIME & DETAILS:</b>", ParagraphStyle('TReg', parent=styles['Normal'], fontSize=9, textColor=PRIMARY, fontName="Helvetica-Bold")),
                Paragraph(f"Tax Treatment: <b>{tax_type_str}</b>", meta_label),
                Paragraph(f"Supplier GSTIN: <b>{comp_gstin_str}</b>", meta_label),
                Paragraph(f"Status: <b>Active Record</b>", meta_label)
            ]
        else:
            gst_info_p = [
                Paragraph("<b>INVOICE DETAILS:</b>", ParagraphStyle('TReg', parent=styles['Normal'], fontSize=9, textColor=PRIMARY, fontName="Helvetica-Bold")),
                Paragraph("Tax Type: <b>Non-Tax / Composition / Bill of Supply</b>", meta_label),
                Paragraph(f"Supplier Status: <b>Unregistered / Non-Taxable Service</b>", meta_label),
                Paragraph(f"Status: <b>Active Record</b>", meta_label)
            ]

        client_table = Table([[client_p, gst_info_p]], colWidths=[310, 230])
        client_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), ACCENT_BG), ('PADDING', (0,0), (-1,-1), 8), ('BOX', (0,0), (-1,-1), 0.5, BORDER_CLR), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
        story.append(client_table)
        story.append(Spacer(1, 10))

        if is_non_tax:
            table_data = [[Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr), Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr), Paragraph("Total Amount (Rs.)", table_hdr)]]
            col_w = [30, 260, 50, 90, 110]
        elif is_intra_state:
            table_data = [[Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr), Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr), Paragraph("Amount (Rs.)", table_hdr), Paragraph("CGST", table_hdr), Paragraph("SGST", table_hdr), Paragraph("Total (Rs.)", table_hdr)]]
            col_w = [25, 175, 35, 65, 75, 45, 45, 80]
        else:
            table_data = [[Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr), Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr), Paragraph("Amount (Rs.)", table_hdr), Paragraph("IGST", table_hdr), Paragraph("Total (Rs.)", table_hdr)]]
            col_w = [25, 205, 40, 75, 85, 55, 95]

        for idx, item in enumerate(items, start=1):
            line_sub = item['qty'] * item['rate']
            if is_non_tax:
                line_total = line_sub
                table_data.append([Paragraph(str(idx), table_cell), Paragraph(item['desc'], table_cell), Paragraph(str(item['qty']), table_cell_r), Paragraph(f"Rs. {item['rate']:,.2f}", table_cell_r), Paragraph(f"Rs. {line_total:,.2f}", table_cell_r)])
            else:
                line_tax = line_sub * (item['tax_rate'] / 100)
                line_total = line_sub + line_tax
                if is_intra_state:
                    half_tax_pct = item['tax_rate'] / 2
                    table_data.append([Paragraph(str(idx), table_cell), Paragraph(item['desc'], table_cell), Paragraph(str(item['qty']), table_cell_r), Paragraph(f"Rs. {item['rate']:,.2f}", table_cell_r), Paragraph(f"Rs. {line_sub:,.2f}", table_cell_r), Paragraph(f"{half_tax_pct:.1f}%", table_cell_r), Paragraph(f"{half_tax_pct:.1f}%", table_cell_r), Paragraph(f"Rs. {line_total:,.2f}", table_cell_r)])
                else:
                    table_data.append([Paragraph(str(idx), table_cell), Paragraph(item['desc'], table_cell), Paragraph(str(item['qty']), table_cell_r), Paragraph(f"Rs. {item['rate']:,.2f}", table_cell_r), Paragraph(f"Rs. {line_sub:,.2f}", table_cell_r), Paragraph(f"{item['tax_rate']}%", table_cell_r), Paragraph(f"Rs. {line_total:,.2f}", table_cell_r)])

        item_table = Table(table_data, colWidths=col_w)
        item_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), PRIMARY), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('GRID', (0,0), (-1,-1), 0.5, BORDER_CLR), ('PADDING', (0,0), (-1,-1), 6)]))
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
        summary_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'RIGHT'), ('PADDING', (0,0), (-1,-1), 4), ('LINEABOVE', (0,-1), (-1,-1), 1, PRIMARY)]))
        story.append(summary_table)
        story.append(Spacer(1, 12))

        bank_text = f"<b>Account Holder:</b> {acc_holder_str}<br/><b>Bank:</b> {bank_name_str} | <b>Account No:</b> {acc_num_str}<br/><b>IFSC:</b> {ifsc_str} | <b>UPI ID:</b> {upi_str}"
        pay_p = [Paragraph("<b>PAYMENT / REMITTANCE DETAILS:</b>", ParagraphStyle('PHead', parent=styles['Normal'], fontSize=8.5, textColor=PRIMARY, fontName="Helvetica-Bold")), Spacer(1, 2), Paragraph(bank_text, meta_label)]
        formatted_terms = terms_str.replace('\n', '<br/>')
        terms_p = [Paragraph("<b>TERMS & CONDITIONS:</b>", ParagraphStyle('THead', parent=styles['Normal'], fontSize=8.5, textColor=PRIMARY, fontName="Helvetica-Bold")), Spacer(1, 2), Paragraph(formatted_terms, meta_label)]

        footer_table = Table([[pay_p, terms_p]], colWidths=[280, 260])
        footer_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), ACCENT_BG), ('PADDING', (0,0), (-1,-1), 8), ('BOX', (0,0), (-1,-1), 0.5, BORDER_CLR), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
        story.append(footer_table)

        doc.build(story, onFirstPage=draw_watermark, onLaterPages=draw_watermark)
        buffer.seek(0)
        return buffer

    def render_html_preview(doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, items, subtotal, tax_amt, grand_total, bank_details=None, is_duplicate=False, theme="Modern Minimalist (Clean Slate)", is_non_tax=False):
        if theme == "Executive Dark (Bold & Corporate)":
            primary_color, secondary_color, accent_bg, border_clr = "#111827", "#4B5563", "#F3F4F6", "#E5E7EB"
        elif theme == "Creative Vibrant (Blue & Slate)":
            primary_color, secondary_color, accent_bg, border_clr = "#1E3A8A", "#2563EB", "#EFF6FF", "#BFDBFE"
        elif theme == "Warm Editorial (Classic & Refined)":
            primary_color, secondary_color, accent_bg, border_clr = "#78350F", "#D97706", "#FFFBEB", "#FDE68A"
        else:
            primary_color, secondary_color, accent_bg, border_clr = "#0F172A", "#64748B", "#F8FAFC", "#E2E8F0"

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
        dup_banner = f"<div style='color: #DC2626; font-weight: bold; font-size: 16px; margin-bottom: 5px;'>*** DUPLICATE COPY ***</div>" if is_duplicate else ""

        items_html = ""
        for idx, item in enumerate(items, start=1):
            line_sub = item['qty'] * item['rate']
            if is_non_tax:
                line_total = line_sub
                items_html += f"<tr><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: center;'>{idx}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr};'>{item['desc']}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>{item['qty']}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>Rs. {item['rate']:,.2f}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>Rs. {line_total:,.2f}</td></tr>"
            else:
                line_tax = line_sub * (item['tax_rate'] / 100)
                line_total = line_sub + line_tax
                if is_intra_state:
                    half_tax = item['tax_rate'] / 2
                    items_html += f"<tr><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: center;'>{idx}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr};'>{item['desc']}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>{item['qty']}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>Rs. {item['rate']:,.2f}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>Rs. {line_sub:,.2f}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>{half_tax:.1f}%</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>{half_tax:.1f}%</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>Rs. {line_total:,.2f}</td></tr>"
                else:
                    items_html += f"<tr><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: center;'>{idx}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr};'>{item['desc']}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>{item['qty']}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>Rs. {item['rate']:,.2f}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>Rs. {line_sub:,.2f}</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>{item['tax_rate']}%</td><td style='padding: 8px; border-bottom: 1px solid {border_clr}; text-align: right;'>Rs. {line_total:,.2f}</td></tr>"

        if is_non_tax:
            tax_summary_html = f"<tr style='border-top: 2px solid {primary_color}; font-weight: bold; font-size: 14px; color: {primary_color};'><td style='padding: 8px; text-align: right;'>Grand Total:</td><td style='padding: 8px; text-align: right;'>Rs. {grand_total:,.2f}</td></tr>"
        else:
            tax_summary_html = f"<tr><td style='padding: 6px; text-align: right;'>Subtotal:</td><td style='padding: 6px; text-align: right;'>Rs. {subtotal:,.2f}</td></tr>"
            if is_intra_state:
                half_tax_tot = tax_amt / 2
                tax_summary_html += f"<tr><td style='padding: 6px; text-align: right;'>CGST:</td><td style='padding: 6px; text-align: right;'>Rs. {half_tax_tot:,.2f}</td></tr><tr><td style='padding: 6px; text-align: right;'>SGST:</td><td style='padding: 6px; text-align: right;'>Rs. {half_tax_tot:,.2f}</td></tr>"
            else:
                tax_summary_html += f"<tr><td style='padding: 6px; text-align: right;'>IGST:</td><td style='padding: 6px; text-align: right;'>Rs. {tax_amt:,.2f}</td></tr>"
            tax_summary_html += f"<tr style='border-top: 2px solid {primary_color}; font-weight: bold; font-size: 14px; color: {primary_color};'><td style='padding: 8px; text-align: right;'>Grand Total:</td><td style='padding: 8px; text-align: right;'>Rs. {grand_total:,.2f}</td></tr>"

        header_headers = f"<th style='padding: 8px; background-color: {primary_color}; color: white; text-align: center;'>#</th><th style='padding: 8px; background-color: {primary_color}; color: white;'>Description</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>Qty</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>Rate</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>Total</th>" if is_non_tax else (f"<th style='padding: 8px; background-color: {primary_color}; color: white; text-align: center;'>#</th><th style='padding: 8px; background-color: {primary_color}; color: white;'>Description</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>Qty</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>Rate</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>Amount</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>CGST</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>SGST</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>Total</th>" if is_intra_state else f"<th style='padding: 8px; background-color: {primary_color}; color: white; text-align: center;'>#</th><th style='padding: 8px; background-color: {primary_color}; color: white;'>Description</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>Qty</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>Rate</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>Amount</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>IGST</th><th style='padding: 8px; background-color: {primary_color}; color: white; text-align: right;'>Total</th>")

        return f"""
        <div style="background-color: #ffffff; color: #1E293B; padding: 30px; font-family: Helvetica, sans-serif; border: 1px solid {border_clr}; border-radius: 6px; max-width: 800px; margin: auto;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="vertical-align: top; width: 55%;">
                        <div style="font-size: 18px; font-weight: bold; color: {primary_color};">{comp_name_str}</div>
                        <div style="font-size: 11px; font-weight: bold; color: {secondary_color};">{comp_sub_str}</div>
                        <div style="font-size: 11px; color: #475569;">{comp_addr_str}</div>
                        <div style="font-size: 11px; color: #475569;">Phone: {comp_phone_str} | Email: {comp_email_str}</div>
                    </td>
                    <td style="vertical-align: top; text-align: right; width: 45%;">
                        {dup_banner}
                        <div style="font-size: 20px; font-weight: bold; color: {secondary_color};">{doc_type.upper()}</div>
                        <div style="font-size: 11px;"><b>Document No:</b> {doc_num}</div>
                        <div style="font-size: 11px;"><b>Date:</b> {doc_date}</div>
                    </td>
                </tr>
            </table>
            <hr style="border: none; border-top: 1.5px solid {primary_color}; margin: 15px 0;" />
            <table style="width: 100%; background-color: {accent_bg}; border: 0.5px solid {border_clr}; margin-bottom: 15px;">
                <tr>
                    <td style="padding: 12px; vertical-align: top; width: 50%;">
                        <div style="font-size: 11px; font-weight: bold; color: {primary_color};">BILLED TO:</div>
                        <div style="font-size: 12px; font-weight: bold;">{client_name}</div>
                        <div style="font-size: 11px; color: #475569;">Contact: {client_phone if client_phone else 'N/A'}</div>
                        <div style="font-size: 11px; color: #475569;">State: {c_state_str}</div>
                    </td>
                </tr>
            </table>
            <table style="width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 15px;">
                <thead><tr>{header_headers}</tr></thead>
                <tbody>{items_html}</tbody>
            </table>
            <table style="width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 20px;">
                <tr><td style="width: 60%;"></td><td style="width: 40%;"><table style="width: 100%;">{tax_summary_html}</table></td></tr>
            </table>
        </div>"""

    # --- SIDEBAR CONTROLS & AUTH SESSION ---
    with st.sidebar:
        st.write(f"Welcome, **{name}**!")
        authenticator.logout("Logout", "sidebar")
        
        if username == "admin":
            st.divider()
            st.subheader("Admin Controls")
            st.write(f"Active sessions tracked: {len(st.session_state['active_sessions'])}")
            if st.button("Terminate All Other Sessions"):
                st.session_state["active_sessions"] = set()
                st.success("All remote sessions cleared.")
                st.rerun()

        st.divider()
        st.subheader("🎨 Invoice Design & Branding")
        current_theme = get_theme_from_db()
        selected_theme = st.sidebar.selectbox(
            "Choose Invoice Theme Style", 
            ["Modern Minimalist (Clean Slate)", "Executive Dark (Bold & Corporate)", "Creative Vibrant (Blue & Slate)", "Warm Editorial (Classic & Refined)"],
            index=["Modern Minimalist (Clean Slate)", "Executive Dark (Bold & Corporate)", "Creative Vibrant (Blue & Slate)", "Warm Editorial (Classic & Refined)"].index(current_theme) if current_theme in ["Modern Minimalist (Clean Slate)", "Executive Dark (Bold & Corporate)", "Creative Vibrant (Blue & Slate)", "Warm Editorial (Classic & Refined)"] else 0
        )
        if selected_theme != current_theme:
            save_theme_to_db(selected_theme)
            st.sidebar.success("Theme updated!")

        uploaded_logo = st.sidebar.file_uploader("Upload Company Logo", type=["png", "jpg", "jpeg"])
        if uploaded_logo is not None:
            save_logo_to_db(uploaded_logo)
            st.sidebar.success("Logo saved!")

    # --- MAIN APP NAVIGATION ---
    st.title("🧾 Nexus Billing & Operations Suite")
    choice = st.radio("Navigation Menu", ["Create Document", "Document History & Management", "Client Directory", "Company & Invoice Settings", "Recycle Bin"], horizontal=True)

    # --- 1. CREATE DOCUMENT ---
    if choice == "Create Document":
        st.header("📝 Create Billing Document")
        
        # Safely enforce list type for session state items
        if "items" not in st.session_state or not isinstance(st.session_state.items, list) or len(st.session_state.items) == 0:
            st.session_state.items = [{'desc': '', 'qty': 1.0, 'rate': 0.0, 'tax_rate': 18.0}]

        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            doc_type = st.selectbox("Document Type", ["Tax Invoice", "Non-Tax Invoice / Bill of Supply", "Estimate / Quotation", "Proforma Invoice"])
        with col_b:
            is_non_tax = ("Non-Tax" in doc_type)
            doc_prefix = "NONTX" if is_non_tax else ("INV" if doc_type == "Tax Invoice" else ("EST" if "Estimate" in doc_type else "PRO"))
            doc_num = st.text_input("Document #", f"{doc_prefix}-{datetime.now().strftime('%Y%m%d%H%M')}")
        with col_c: doc_date = st.date_input("Document Date", date.today())
        with col_d: status = st.selectbox("Payment Status", ["Unpaid", "Paid", "Partially Paid", "Overdue", "Draft"]) if "Invoice" in doc_type else st.selectbox("Status", ["Draft", "Sent", "Accepted", "Rejected"])

        st.subheader("Client Information")
        clients_df = pd.read_sql("SELECT name FROM clients", conn)
        client_names = ["-- New Client --"] + clients_df['name'].tolist()
        sel_client = st.selectbox("Select Existing Client", client_names)

        client_name, client_phone, client_email, client_addr, client_state, client_gstin = "", "", "", "", "Karnataka", ""
        if sel_client != "-- New Client --":
            c_row = cursor.execute("SELECT name, phone, email, address, state, tax_id FROM clients WHERE name=?", (sel_client,)).fetchone()
            if c_row: client_name, client_phone, client_email, client_addr, client_state, client_gstin = c_row

        cc1, cc2, cc3 = st.columns(3)
        client_name = cc1.text_input("Client Name", client_name)
        client_phone = cc2.text_input("Client Phone", client_phone)
        client_gstin = cc3.text_input("Client GSTIN (Leave blank if unreg.)", client_gstin)
        client_state = st.selectbox("Place of Supply (State)", ["Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"], index=15 if not client_state else ["Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"].index(client_state))

        st.subheader("Line Items")
        
        # Robust check to prevent method collision or corruption
        if "items" not in st.session_state or not isinstance(st.session_state.items, list):
            st.session_state.items = [{'desc': '', 'qty': 1.0, 'rate': 0.0, 'tax_rate': 18.0}]

        temp_items = []
        
        for idx, item_data in enumerate(st.session_state.items):
            if not isinstance(item_data, dict):
                item_data = {'desc': '', 'qty': 1.0, 'rate': 0.0, 'tax_rate': 18.0}

            col_desc, col_qty, col_rate, col_tax = st.columns([4, 1, 1, 1])
            
            with col_desc:
                entered_desc = st.text_input(f"Description {idx+1}", value=item_data.get('desc', ''), key=f"d_input_{idx}")
            with col_qty:
                entered_qty = st.number_input(f"Qty {idx+1}", min_value=0.1, value=float(item_data.get('qty', 1.0)), key=f"q_input_{idx}")
            with col_rate:
                entered_rate = st.number_input(f"Rate {idx+1}", min_value=0.0, value=float(item_data.get('rate', 0.0)), key=f"r_input_{idx}")
            
            if not is_non_tax:
                current_t = item_data.get('tax_rate', 18.0)
                t_options = [0.0, 5.0, 12.0, 18.0, 28.0]
                t_idx = t_options.index(current_t) if current_t in t_options else 3
                with col_tax:
                    entered_tax = st.selectbox(f"GST {idx+1}", t_options, index=t_idx, key=f"t_input_{idx}")
            else:
                entered_tax = 0.0

            temp_items.append({
                'desc': entered_desc,
                'qty': entered_qty,
                'rate': entered_rate,
                'tax_rate': entered_tax
            })

        st.session_state.items = temp_items

        if st.button("➕ Add Another Item"):
            if not isinstance(st.session_state.items, list):
                st.session_state.items = []
            st.session_state.items.append({'desc': '', 'qty': 1.0, 'rate': 0.0, 'tax_rate': 18.0 if not is_non_tax else 0.0})
            st.rerun()

        subtotal = sum(i['qty'] * i['rate'] for i in st.session_state.items)
        if not is_non_tax: tax_amt = sum((i['qty'] * i['rate']) * (i['tax_rate']/100) for i in st.session_state.items)
        else: tax_amt = 0.0
        grand_total = subtotal + tax_amt

        col_tot1, col_tot2 = st.columns(2)
        with col_tot1:
            st.metric("Subtotal", f"Rs. {subtotal:,.2f}")
            if not is_non_tax: st.metric("Total Tax", f"Rs. {tax_amt:,.2f}")
        with col_tot2:
            st.metric("Grand Total", f"Rs. {grand_total:,.2f}")

        if st.button("Preview HTML & Layout"):
            st.markdown(render_html_preview(doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, st.session_state.items, subtotal, tax_amt, grand_total, is_duplicate=False, theme=get_theme_from_db(), is_non_tax=is_non_tax), unsafe_allow_html=True)

        if st.button("💾 Save & Generate Final PDF"):
            if client_name and len(st.session_state.items) > 0 and st.session_state.items[0]['desc']:
                if sel_client == "-- New Client --":
                    cursor.execute("INSERT INTO clients (name, phone, email, address, state, tax_id) VALUES (?, ?, ?, ?, ?, ?)", (client_name, client_phone, client_email, client_addr, client_state, client_gstin))
                else:
                    cursor.execute("UPDATE clients SET phone=?, email=?, address=?, state=?, tax_id=? WHERE name=?", (client_phone, client_email, client_addr, client_state, client_gstin, client_name))
                
                items_j = json.dumps(st.session_state.items)
                cursor.execute('''INSERT INTO documents (doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (doc_type, doc_num, client_name, client_phone, client_gstin, client_state, str(doc_date), subtotal, tax_amt, grand_total, status, items_j))
                conn.commit()
                st.success("Document Saved to Database!")

                pdf_buf = generate_pdf(doc_type, doc_num, client_name, client_phone, client_gstin, client_state, str(doc_date), st.session_state.items, subtotal, tax_amt, grand_total, theme=get_theme_from_db(), is_non_tax=is_non_tax)
                st.download_button(label="📥 Download Original PDF", data=pdf_buf, file_name=f"{doc_num}.pdf", mime="application/pdf")
                st.session_state.items = [{'desc': '', 'qty': 1.0, 'rate': 0.0, 'tax_rate': 18.0 if not is_non_tax else 0.0}]
            else:
                st.error("Please enter Client Name and at least one item description.")

    # --- 2. DOCUMENT HISTORY ---
    elif choice == "Document History & Management":
        st.header("📂 Document History")
        docs = pd.read_sql("SELECT id, doc_type, doc_num, doc_date, client_name, grand_total, status FROM documents ORDER BY id DESC", conn)
        if not docs.empty:
            st.dataframe(docs, use_container_width=True)
            sel_id = st.selectbox("Select Document ID to Manage", docs['id'].tolist())
            d_row = cursor.execute("SELECT doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json FROM documents WHERE id=?", (sel_id,)).fetchone()
            if d_row:
                st.markdown(f"**Selected:** {d_row[1]} for {d_row[2]}")
                r_type, r_num, r_cname, r_cphone, r_cgstin, r_cstate, r_date, r_sub, r_tax, r_grand, r_stat, r_itemsj = d_row
                is_ntx = ("Non-Tax" in r_type)

                co1, co2 = st.columns(2)
                with co1:
                    new_stat = st.selectbox("Update Status", ["Unpaid", "Paid", "Partially Paid", "Overdue", "Draft", "Sent", "Accepted", "Rejected"], index=["Unpaid", "Paid", "Partially Paid", "Overdue", "Draft", "Sent", "Accepted", "Rejected"].index(r_stat) if r_stat in ["Unpaid", "Paid", "Partially Paid", "Overdue", "Draft", "Sent", "Accepted", "Rejected"] else 0)
                    if st.button("Update Status"):
                        cursor.execute("UPDATE documents SET status=? WHERE id=?", (new_stat, sel_id))
                        conn.commit()
                        st.success("Status updated!"); st.rerun()
                with co2:
                    if st.button("🗑️ Move to Recycle Bin", type="primary"):
                        cursor.execute("INSERT INTO deleted_documents (original_id, doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (sel_id, r_type, r_num, r_cname, r_cphone, r_cgstin, r_cstate, r_date, r_sub, r_tax, r_grand, r_stat, r_itemsj, str(datetime.now())))
                        cursor.execute("DELETE FROM documents WHERE id=?", (sel_id,))
                        conn.commit()
                        st.warning("Document moved to Recycle Bin!"); st.rerun()

                r_items = json.loads(r_itemsj)
                st.markdown("### Generate PDF")
                p1, p2 = st.columns(2)
                with p1:
                    orig_pdf_buf = generate_pdf(r_type, r_num, r_cname, r_cphone, r_cgstin, r_cstate, r_date, r_items, r_sub, r_tax, r_grand, is_duplicate=False, theme=get_theme_from_db(), is_non_tax=is_ntx)
                    st.download_button(label="📥 Download Original PDF", data=orig_pdf_buf, file_name=f"{r_num}_Original.pdf", mime="application/pdf")
                with p2:
                    dup_pdf_buf = generate_pdf(r_type, r_num, r_cname, r_cphone, r_cgstin, r_cstate, r_date, r_items, r_sub, r_tax, r_grand, is_duplicate=True, theme=get_theme_from_db(), is_non_tax=is_ntx)
                    st.download_button(label="📥 Download Duplicate PDF", data=dup_pdf_buf, file_name=f"{r_num}_Duplicate.pdf", mime="application/pdf")

    # --- 3. CLIENT DIRECTORY ---
    elif choice == "Client Directory":
        st.header("👥 Client Directory")
        clients = pd.read_sql("SELECT id, name, phone, email, state, tax_id FROM clients", conn)
        st.dataframe(clients, use_container_width=True)

    # --- 4. COMPANY & INVOICE SETTINGS ---
    elif choice == "Company & Invoice Settings":
        st.header("⚙️ Company Settings")
        
        comp_name = st.text_input("Company Name", get_setting('company_name', DEFAULT_SETTINGS['company_name']))
        comp_sub = st.text_input("Subtitle / Tagline", get_setting('company_sub', DEFAULT_SETTINGS['company_sub']))
        comp_addr = st.text_area("Address", get_setting('company_addr', DEFAULT_SETTINGS['company_addr']))
        comp_state = st.text_input("Company State (For GST Calculation)", get_setting('company_state', DEFAULT_SETTINGS['company_state']))
        comp_phone = st.text_input("Phone", get_setting('company_phone', DEFAULT_SETTINGS['company_phone']))
        comp_email = st.text_input("Email", get_setting('company_email', DEFAULT_SETTINGS['company_email']))
        comp_gstin = st.text_input("Company GSTIN", get_setting('company_gstin', DEFAULT_SETTINGS['company_gstin']))
        terms = st.text_area("Default Terms & Conditions", get_setting('terms_conditions', DEFAULT_SETTINGS['terms_conditions']))

        if st.button("Save Company Settings"):
            save_setting('company_name', comp_name)
            save_setting('company_sub', comp_sub)
            save_setting('company_addr', comp_addr)
            save_setting('company_state', comp_state)
            save_setting('company_phone', comp_phone)
            save_setting('company_email', comp_email)
            save_setting('company_gstin', comp_gstin)
            save_setting('terms_conditions', terms)
            st.success("Settings Saved!")

    # --- 5. RECYCLE BIN ---
    elif choice == "Recycle Bin":
        st.header("🗑️ Recycle Bin")
        del_docs = pd.read_sql("SELECT bin_id, original_id, doc_num, client_name, deleted_at FROM deleted_documents", conn)
        if not del_docs.empty:
            st.dataframe(del_docs, use_container_width=True)
            restore_id = st.selectbox("Select bin_id to restore", del_docs['bin_id'].tolist())
            if st.button("♻️ Restore Document"):
                r_doc = cursor.execute("SELECT original_id, doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json FROM deleted_documents WHERE bin_id=?", (restore_id,)).fetchone()
                if r_doc:
                    cursor.execute("INSERT INTO documents (id, doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", r_doc)
                    cursor.execute("DELETE FROM deleted_documents WHERE bin_id=?", (restore_id,))
                    conn.commit()
                    st.success("Document Restored!")
                    st.rerun()
        else:
            st.info("Recycle bin is empty.")
