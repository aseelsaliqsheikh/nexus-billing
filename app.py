import streamlit as st
import pandas as pd
import sqlite3
import json
import os
from datetime import datetime, date
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import io

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Nexus Billing & Operations", page_icon="🧾", layout="wide")

# --- DATABASE SETUP ---
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
        id INTEGER PRIMARY KEY,
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
conn.commit()

# --- AUTOMATIC SCHEMA MIGRATION ---
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

# --- COMPANY DETAILS ---
COMPANY_NAME = "NEXUS CENTER OF EVENTS"
COMPANY_SUB = "Event Planning, Execution & Corporate Management"
COMPANY_ADDR = "Bangalore, Karnataka, India"
COMPANY_STATE = "Karnataka"
COMPANY_PHONE = "+91 98765 43210"
COMPANY_EMAIL = "info@nexusevents.com"
COMPANY_GSTIN = "29AAAAA0000A1Z5"

# --- BANK / PAYMENT DETAILS ---
BANK_NAME = "HDFC Bank"
ACCOUNT_HOLDER = "Nexus Center of Events"
ACCOUNT_NUMBER = "50200012345678"
IFSC_CODE = "HDFC0001234"
UPI_ID = "nexus@upi"

# --- HELPER FUNCTIONS FOR PERSISTENT LOGO ---
def save_logo_to_db(uploaded_file):
    if uploaded_file is not None:
        logo_bytes = uploaded_file.getvalue()
        cursor.execute("REPLACE INTO settings (key, value) VALUES ('company_logo', ?)", (logo_bytes,))
        conn.commit()

def get_logo_from_db():
    row = cursor.execute("SELECT value FROM settings WHERE key = 'company_logo'").fetchone()
    if row and row[0]:
        return io.BytesIO(row[0])
    return None

# --- PROFESSIONAL PDF GENERATOR ENGINE ---
def generate_pdf(doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, items, subtotal, tax_amt, grand_total, is_duplicate=False):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = getSampleStyleSheet()

    PRIMARY = colors.HexColor("#0F172A")    
    SECONDARY = colors.HexColor("#2563EB")  
    TEXT_DARK = colors.HexColor("#1E293B")  
    BG_LIGHT = colors.HexColor("#F8FAFC")   
    BORDER_CLR = colors.HexColor("#CBD5E1") 
    ACCENT_RED = colors.HexColor("#DC2626") 

    comp_title_style = ParagraphStyle('CompTitle', parent=styles['Heading1'], fontSize=15, leading=17, textColor=PRIMARY, fontName="Helvetica-Bold")
    comp_sub_style = ParagraphStyle('CompSub', parent=styles['Normal'], fontSize=8.5, leading=11, textColor=TEXT_DARK)
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
            logo_img = Image(logo_file, width=100, height=50)
            logo_img.hAlign = 'CENTER'
            
            logo_container = Table([[logo_img]], colWidths=[110])
            logo_container.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), PRIMARY),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 4),
            ]))
        except Exception:
            logo_container = None

    company_info_p = [
        Paragraph(COMPANY_NAME, comp_title_style),
        Paragraph(f"<b>{COMPANY_SUB}</b>", comp_sub_style),
        Paragraph(COMPANY_ADDR, comp_sub_style),
        Paragraph(f"Phone: {COMPANY_PHONE} | Email: {COMPANY_EMAIL}", comp_sub_style),
        Paragraph(f"<b>GSTIN:</b> {COMPANY_GSTIN}", comp_sub_style)
    ]
    
    company_col = [logo_container, Spacer(1, 4)] + company_info_p if logo_container else company_info_p

    dup_text = f"<font color='{ACCENT_RED.hexval()}'><b>*** DUPLICATE COPY ***</b></font><br/>" if is_duplicate else ""
    meta_info_p = [
        Paragraph(f"{dup_text}{doc_type.upper()}", doc_type_style),
        Spacer(1, 6),
        Paragraph(f"<b>Document No:</b> {doc_num}", ParagraphStyle('M1', parent=meta_label, alignment=2)),
        Paragraph(f"<b>Date:</b> {doc_date}", ParagraphStyle('M2', parent=meta_label, alignment=2)),
        Paragraph(f"<b>Place of Supply:</b> {client_state if client_state else COMPANY_STATE}", ParagraphStyle('M3', parent=meta_label, alignment=2))
    ]

    header_table = Table([[company_col, meta_info_p]], colWidths=[310, 230])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY, spaceBefore=2, spaceAfter=8))

    c_state_str = client_state if client_state else "Karnataka"
    is_intra_state = (c_state_str.strip().lower() == COMPANY_STATE.lower())

    client_p = [
        Paragraph("<b>BILL TO:</b>", ParagraphStyle('BTo', parent=styles['Normal'], fontSize=9, textColor=SECONDARY, fontName="Helvetica-Bold")),
        Paragraph(f"<b>{client_name}</b>", ParagraphStyle('CName', parent=styles['Normal'], fontSize=10, textColor=TEXT_DARK, fontName="Helvetica-Bold")),
        Paragraph(f"Contact: {client_phone if client_phone else 'N/A'}", meta_label),
        Paragraph(f"State: {c_state_str}", meta_label),
        Paragraph(f"<b>Client GSTIN:</b> {client_gstin if client_gstin else 'N/A'}", meta_label)
    ]
    
    tax_type_str = "Intra-State GST (CGST + SGST)" if is_intra_state else "Inter-State GST (IGST)"
    gst_info_p = [
        Paragraph("<b>TAX REGIME DETAILS:</b>", ParagraphStyle('TReg', parent=styles['Normal'], fontSize=9, textColor=SECONDARY, fontName="Helvetica-Bold")),
        Paragraph(f"Tax Treatment: <b>{tax_type_str}</b>", meta_label),
        Paragraph(f"Supplier GSTIN: <b>{COMPANY_GSTIN}</b>", meta_label)
    ]

    client_table = Table([[client_p, gst_info_p]], colWidths=[310, 230])
    client_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_CLR),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(client_table)
    story.append(Spacer(1, 10))

    if is_intra_state:
        table_data = [[
            Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr),
            Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr),
            Paragraph("CGST", table_hdr), Paragraph("SGST", table_hdr), Paragraph("Total (Rs.)", table_hdr)
        ]]
        col_w = [25, 205, 35, 75, 50, 50, 100]
    else:
        table_data = [[
            Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr),
            Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr),
            Paragraph("IGST", table_hdr), Paragraph("Total (Rs.)", table_hdr)
        ]]
        col_w = [25, 235, 40, 80, 60, 100]

    for idx, item in enumerate(items, start=1):
        line_sub = item['qty'] * item['rate']
        line_tax = line_sub * (item['tax_rate'] / 100)
        line_total = line_sub + line_tax

        if is_intra_state:
            half_tax_pct = item['tax_rate'] / 2
            table_data.append([
                Paragraph(str(idx), table_cell), Paragraph(item['desc'], table_cell),
                Paragraph(str(item['qty']), table_cell_r), Paragraph(f"Rs. {item['rate']:,.2f}", table_cell_r),
                Paragraph(f"{half_tax_pct:.1f}%", table_cell_r), Paragraph(f"{half_tax_pct:.1f}%", table_cell_r),
                Paragraph(f"Rs. {line_total:,.2f}", table_cell_r)
            ])
        else:
            table_data.append([
                Paragraph(str(idx), table_cell), Paragraph(item['desc'], table_cell),
                Paragraph(str(item['qty']), table_cell_r), Paragraph(f"Rs. {item['rate']:,.2f}", table_cell_r),
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

    bank_text = (
        f"<b>Account Holder:</b> {ACCOUNT_HOLDER}<br/>"
        f"<b>Bank:</b> {BANK_NAME} | <b>Account No:</b> {ACCOUNT_NUMBER}<br/>"
        f"<b>IFSC:</b> {IFSC_CODE} | <b>UPI ID:</b> {UPI_ID}"
    )

    pay_p = [
        Paragraph("<b>PAYMENT / REMITTANCE DETAILS:</b>", ParagraphStyle('PHead', parent=styles['Normal'], fontSize=8.5, textColor=SECONDARY, fontName="Helvetica-Bold")),
        Spacer(1, 2), Paragraph(bank_text, meta_label)
    ]
    
    terms_p = [
        Paragraph("<b>TERMS & CONDITIONS:</b>", ParagraphStyle('THead', parent=styles['Normal'], fontSize=8.5, textColor=SECONDARY, fontName="Helvetica-Bold")),
        Spacer(1, 2), Paragraph("1. Payment due within 15 days of invoice date.<br/>2. Quote invoice # on payment.<br/>3. Subject to Bangalore jurisdiction.", meta_label)
    ]

    footer_table = Table([[pay_p, terms_p]], colWidths=[280, 260])
    footer_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_CLR),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(footer_table)

    doc.build(story)
    buffer.seek(0)
    return buffer

# --- HTML PREVIEW RENDERER (Actual Layout Simulation) ---
def render_html_preview(doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, items, subtotal, tax_amt, grand_total, is_duplicate=False):
    c_state_str = client_state if client_state else "Karnataka"
    is_intra_state = (c_state_str.strip().lower() == COMPANY_STATE.lower())
    
    dup_banner = f"<div style='color: #DC2626; font-weight: bold; font-size: 16px; margin-bottom: 5px;'>*** DUPLICATE COPY ***</div>" if is_duplicate else ""
    
    items_html = ""
    for idx, item in enumerate(items, start=1):
        line_sub = item['qty'] * item['rate']
        line_tax = line_sub * (item['tax_rate'] / 100)
        line_total = line_sub + line_tax
        
        if is_intra_state:
            half_tax = item['tax_rate'] / 2
            items_html += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1; text-align: center;">{idx}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1;">{item['desc']}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1; text-align: right;">{item['qty']}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1; text-align: right;">Rs. {item['rate']:,.2f}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1; text-align: right;">{half_tax:.1f}%</td>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1; text-align: right;">{half_tax:.1f}%</td>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1; text-align: right;">Rs. {line_total:,.2f}</td>
                </tr>
            """
        else:
            items_html += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1; text-align: center;">{idx}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1;">{item['desc']}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1; text-align: right;">{item['qty']}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1; text-align: right;">Rs. {item['rate']:,.2f}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1; text-align: right;">{item['tax_rate']}%</td>
                    <td style="padding: 8px; border-bottom: 1px solid #CBD5E1; text-align: right;">Rs. {line_total:,.2f}</td>
                </tr>
            """

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
        <tr style='border-top: 2px solid #0F172A; font-weight: bold; font-size: 14px; color: #0F172A;'>
            <td style='padding: 8px; text-align: right;'>Grand Total:</td>
            <td style='padding: 8px; text-align: right;'>Rs. {grand_total:,.2f}</td>
        </tr>
    """

    header_headers = """
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: center;">#</th>
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: left;">Item / Service Description</th>
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: right;">Qty</th>
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: right;">Rate (Rs.)</th>
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: right;">CGST</th>
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: right;">SGST</th>
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: right;">Total (Rs.)</th>
    """ if is_intra_state else """
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: center;">#</th>
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: left;">Item / Service Description</th>
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: right;">Qty</th>
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: right;">Rate (Rs.)</th>
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: right;">IGST</th>
        <th style="padding: 8px; background-color: #0F172A; color: white; text-align: right;">Total (Rs.)</th>
    """

    html_content = f"""
    <div style="background-color: #ffffff; color: #1E293B; padding: 30px; font-family: Helvetica, Arial, sans-serif; border: 1px solid #CBD5E1; border-radius: 6px; max-width: 800px; margin: auto;">
        <!-- Header Section -->
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="vertical-align: top; width: 55%;">
                    <div style="font-size: 18px; font-weight: bold; color: #0F172A;">{COMPANY_NAME}</div>
                    <div style="font-size: 11px; font-weight: bold; color: #1E293B; margin-top: 2px;">{COMPANY_SUB}</div>
                    <div style="font-size: 11px; color: #475569; margin-top: 2px;">{COMPANY_ADDR}</div>
                    <div style="font-size: 11px; color: #475569;">Phone: {COMPANY_PHONE} | Email: {COMPANY_EMAIL}</div>
                    <div style="font-size: 11px; color: #475569; margin-top: 2px;"><b>GSTIN:</b> {COMPANY_GSTIN}</div>
                </td>
                <td style="vertical-align: top; text-align: right; width: 45%;">
                    {dup_banner}
                    <div style="font-size: 20px; font-weight: bold; color: #2563EB;">{doc_type.upper()}</div>
                    <div style="font-size: 11px; color: #1E293B; margin-top: 6px;"><b>Document No:</b> {doc_num}</div>
                    <div style="font-size: 11px; color: #1E293B;"><b>Date:</b> {doc_date}</div>
                    <div style="font-size: 11px; color: #1E293B;"><b>Place of Supply:</b> {c_state_str}</div>
                </td>
            </tr>
        </table>
        
        <hr style="border: none; border-top: 1.5px solid #0F172A; margin: 15px 0;" />

        <!-- Client & Tax Details Box -->
        <table style="width: 100%; border-collapse: collapse; background-color: #F8FAFC; border: 0.5px solid #CBD5E1; margin-bottom: 15px;">
            <tr>
                <td style="padding: 12px; vertical-align: top; width: 50%;">
                    <div style="font-size: 11px; font-weight: bold; color: #2563EB; margin-bottom: 4px;">BILL TO:</div>
                    <div style="font-size: 12px; font-weight: bold; color: #0F172A;">{client_name}</div>
                    <div style="font-size: 11px; color: #475569;">Contact: {client_phone if client_phone else 'N/A'}</div>
                    <div style="font-size: 11px; color: #475569;">State: {c_state_str}</div>
                    <div style="font-size: 11px; color: #475569;"><b>Client GSTIN:</b> {client_gstin if client_gstin else 'N/A'}</div>
                </td>
                <td style="padding: 12px; vertical-align: top; width: 50%; border-left: 0.5px solid #CBD5E1;">
                    <div style="font-size: 11px; font-weight: bold; color: #2563EB; margin-bottom: 4px;">TAX REGIME DETAILS:</div>
                    <div style="font-size: 11px; color: #475569;">Tax Treatment: <b>{"Intra-State GST (CGST + SGST)" if is_intra_state else "Inter-State GST (IGST)"}</b></div>
                    <div style="font-size: 11px; color: #475569; margin-top: 2px;">Supplier GSTIN: <b>{COMPANY_GSTIN}</b></div>
                </td>
            </tr>
        </table>

        <!-- Line Items Table -->
        <table style="width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 15px;">
            <thead>
                <tr>
                    {header_headers}
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
        </table>

        <!-- Summary Totals Table -->
        <table style="width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 20px;">
            <tr>
                <td style="width: 60%;"></td>
                <td style="width: 40%;">
                    <table style="width: 100%; border-collapse: collapse;">
                        {tax_summary_html}
                    </table>
                </td>
            </tr>
        </table>

        <!-- Footer / Payment & Terms -->
        <table style="width: 100%; border-collapse: collapse; background-color: #F8FAFC; border: 0.5px solid #CBD5E1;">
            <tr>
                <td style="padding: 10px; vertical-align: top; width: 50%;">
                    <div style="font-size: 10px; font-weight: bold; color: #2563EB; margin-bottom: 3px;">PAYMENT / REMITTANCE DETAILS:</div>
                    <div style="font-size: 10px; color: #475569; line-height: 1.4;">
                        <b>Account Holder:</b> {ACCOUNT_HOLDER}<br/>
                        <b>Bank:</b> {BANK_NAME} | <b>Account No:</b> {ACCOUNT_NUMBER}<br/>
                        <b>IFSC:</b> {IFSC_CODE} | <b>UPI ID:</b> {UPI_ID}
                    </div>
                </td>
                <td style="padding: 10px; vertical-align: top; width: 50%; border-left: 0.5px solid #CBD5E1;">
                    <div style="font-size: 10px; font-weight: bold; color: #2563EB; margin-bottom: 3px;">TERMS & CONDITIONS:</div>
                    <div style="font-size: 10px; color: #475569; line-height: 1.4;">
                        1. Payment due within 15 days of invoice date.<br/>
                        2. Quote invoice # on payment.<br/>
                        3. Subject to Bangalore jurisdiction.
                    </div>
                </td>
            </tr>
        </table>
    </div>
    """
    return html_content

# --- STREAMLIT APP NAVIGATION ---
st.title("🧾 Nexus Billing & Operations Suite")

menu = ["Create Document", "Document History & Management", "Client Directory"]
choice = st.sidebar.selectbox("Navigation", menu)

st.sidebar.divider()
st.sidebar.subheader("🖼️ Invoice Branding")
uploaded_logo = st.sidebar.file_uploader("Upload Company Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
if uploaded_logo is not None:
    save_logo_to_db(uploaded_logo)
    st.sidebar.success("Logo saved permanently!")

# --- 1. CREATE DOCUMENT ---
if choice == "Create Document":
    st.header("📝 Create Billing Document")
    
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        doc_type = st.selectbox("Document Type", ["Tax Invoice", "Estimate / Quotation", "Proforma Invoice"])
    with col_b:
        doc_prefix = "INV" if doc_type == "Tax Invoice" else ("EST" if "Estimate" in doc_type else "PRO")
        doc_num = st.text_input("Document #", f"{doc_prefix}-{date.today().strftime('%Y%m%d')}-01")
    with col_c:
        doc_date = st.date_input("Date", date.today())

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
            st.session_state.item_list.append({
                "desc": item_desc,
                "qty": item_qty,
                "rate": item_rate,
                "tax_rate": item_tax
            })
            st.success(f"Added '{item_desc}'")

    if st.session_state.item_list:
        st.write("### Current Items in Document")
        items_df = pd.DataFrame(st.session_state.item_list)
        st.dataframe(items_df, use_container_width=True)
        
        if st.button("Clear All Items"):
            st.session_state.item_list = []
            st.rerun()

        subtotal = sum(i['qty'] * i['rate'] for i in st.session_state.item_list)
        tax_amt = sum((i['qty'] * i['rate']) * (i['tax_rate']/100) for i in st.session_state.item_list)
        grand_total = subtotal + tax_amt

        st.divider()
        st.markdown(f"#### Subtotal: ₹{subtotal:,.2f} | GST Tax Total: ₹{tax_amt:,.2f}")
        st.markdown(f"### **Grand Total: ₹{grand_total:,.2f}**")

        # --- LIVE PREVIEW TAB CONTAINER ---
        st.divider()
        st.subheader("👁️ Live Layout Preview")
        preview_tab, save_tab = st.tabs(["📄 View Actual Layout", "💾 Save Document"])

        with preview_tab:
            st.info("Below is the exact visual representation of how the layout looks before generating or downloading the final copy.")
            html_preview = render_html_preview(
                doc_type, doc_num, client_name if client_name else "Client Name Placeholder", 
                client_phone, client_gstin, client_state, str(doc_date), 
                st.session_state.item_list, subtotal, tax_amt, grand_total
            )
            st.components.v1.html(html_preview, height=650, scrolling=True)

        with save_tab:
            doc_status = st.selectbox("Initial Status", ["Paid", "Pending", "Sent", "Draft"])

            if st.button("💾 Generate & Save Document"):
                items_json = json.dumps(st.session_state.item_list)
                cursor.execute('''
                    INSERT INTO documents (doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (doc_type, doc_num, client_name, client_phone, client_gstin, client_state, str(doc_date), subtotal, tax_amt, grand_total, doc_status, items_json))
                conn.commit()

                if client_mode == "New Client (Quick Add)" and client_name:
                    cursor.execute("INSERT INTO clients (name, phone, state, tax_id) VALUES (?, ?, ?, ?)", (client_name, client_phone, client_state, client_gstin))
                    conn.commit()

                st.session_state.item_list = []
                st.success(f"{doc_type} '{doc_num}' created successfully!")

                pdf_data = generate_pdf(
                    doc_type, doc_num, client_name, client_phone, client_gstin, client_state, 
                    str(doc_date), json.loads(items_json), subtotal, tax_amt, grand_total
                )
                st.download_button(
                    label=f"📄 Download {doc_type} PDF",
                    data=pdf_data,
                    file_name=f"{doc_num}.pdf",
                    mime="application/pdf"
                )

# --- 2. DOCUMENT HISTORY & MANAGEMENT ---
elif choice == "Document History & Management":
    st.header("📊 Document Register & Management")

    df = pd.read_sql_query("SELECT id, doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json FROM documents ORDER BY id DESC", conn)

    if not df.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Revenue Billed", f"₹{df[df['doc_type']=='Tax Invoice']['grand_total'].sum():,.2f}")
        m2.metric("Pending Invoices Amount", f"₹{df[(df['doc_type']=='Tax Invoice') & (df['status']=='Pending')]['grand_total'].sum():,.2f}")
        m3.metric("Total Documents Issued", len(df))

        st.divider()
        st.subheader("Document Register")
        st.dataframe(df[['id', 'doc_type', 'doc_num', 'client_name', 'client_state', 'doc_date', 'grand_total', 'status']], use_container_width=True)

        st.divider()
        st.subheader("🛠️ Manage Document")
        
        selected_id = st.number_input("Enter Document ID to Action", min_value=int(df['id'].min()), max_value=int(df['id'].max()), step=1)
        doc_row = df[df['id'] == selected_id]

        if not doc_row.empty:
            doc_data = doc_row.iloc[0]
            try:
                items_list = json.loads(doc_data['items_json'])
            except:
                items_list = []

            tab_view, tab_print, tab_status, tab_delete, tab_bin = st.tabs([
                "👁️ View Actual Layout", "🖨️ Print Copies", "🔄 Update Status", "🗑️ Move to Recycle Bin", "♻️ Recycle Bin"
            ])

            with tab_view:
                st.markdown(f"### **Visual Layout Preview — {doc_data['doc_type']} (#{doc_data['doc_num']})**")
                html_preview_existing = render_html_preview(
                    doc_data['doc_type'], doc_data['doc_num'], doc_data['client_name'], 
                    doc_data['client_phone'], doc_data['client_gstin'], doc_data['client_state'],
                    doc_data['doc_date'], items_list, doc_data['subtotal'], doc_data['tax_amt'], 
                    doc_data['grand_total']
                )
                st.components.v1.html(html_preview_existing, height=650, scrolling=True)

            with tab_print:
                st.subheader("🖨️ Print / Download Copies")
                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    pdf_orig = generate_pdf(
                        doc_data['doc_type'], doc_data['doc_num'], doc_data['client_name'], doc_data['client_phone'],
                        doc_data['client_gstin'], doc_data['client_state'], doc_data['doc_date'], items_list,
                        doc_data['subtotal'], doc_data['tax_amt'], doc_data['grand_total'], is_duplicate=False
                    )
                    st.download_button(label="📥 Download Original Copy", data=pdf_orig, file_name=f"{doc_data['doc_num']}_Original.pdf", mime="application/pdf")
                with col_p2:
                    pdf_dup = generate_pdf(
                        doc_data['doc_type'], doc_data['doc_num'], doc_data['client_name'], doc_data['client_phone'],
                        doc_data['client_gstin'], doc_data['client_state'], doc_data['doc_date'], items_list,
                        doc_data['subtotal'], doc_data['tax_amt'], doc_data['grand_total'], is_duplicate=True
                    )
                    st.download_button(label="📥 Download Duplicate Copy", data=pdf_dup, file_name=f"{doc_data['doc_num']}_Duplicate.pdf", mime="application/pdf")

            with tab_status:
                st.subheader("🔄 Update Status")
                new_status = st.selectbox("Select New Status", ["Paid", "Pending", "Sent", "Draft"], index=["Paid", "Pending", "Sent", "Draft"].index(doc_data['status']) if doc_data['status'] in ["Paid", "Pending", "Sent", "Draft"] else 0)
                if st.button("Update Status"):
                    cursor.execute("UPDATE documents SET status = ? WHERE id = ?", (new_status, int(selected_id)))
                    conn.commit()
                    st.success("Document status updated successfully!")
                    st.rerun()

            with tab_delete:
                st.warning("Moving this document to the Recycle Bin will remove it from active records. You can restore it anytime from the Recycle Bin tab.")
                if st.button("🗑️ Move Document to Recycle Bin", type="primary"):
                    cursor.execute('''
                        INSERT INTO deleted_documents (id, doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json, deleted_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (doc_data['id'], doc_data['doc_type'], doc_data['doc_num'], doc_data['client_name'], doc_data['client_phone'], doc_data['client_gstin'], doc_data['client_state'], doc_data['doc_date'], doc_data['subtotal'], doc_data['tax_amt'], doc_data['grand_total'], doc_data['status'], doc_data['items_json'], str(date.today())))
                    cursor.execute("DELETE FROM documents WHERE id = ?", (int(selected_id),))
                    conn.commit()
                    st.success("Document moved to Recycle Bin!")
                    st.rerun()

            with tab_bin:
                st.subheader("♻️ Recycle Bin — Deleted Documents")
                bin_df = pd.read_sql_query("SELECT id, doc_type, doc_num, client_name, grand_total, deleted_at FROM deleted_documents ORDER BY id DESC", conn)
                if not bin_df.empty:
                    st.dataframe(bin_df, use_container_width=True)
                    restore_id = st.number_input("Enter ID to Restore or Delete Permanently", min_value=int(bin_df['id'].min()), max_value=int(bin_df['id'].max()), step=1, key="restore_id_input")
                    
                    col_r1, col_r2 = st.columns(2)
                    with col_r1:
                        if st.button("♻️ Restore Document"):
                            bin_row = cursor.execute("SELECT * FROM deleted_documents WHERE id = ?", (int(restore_id),)).fetchone()
                            if bin_row:
                                cursor.execute('''
                                    INSERT INTO documents (id, doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, subtotal, tax_amt, grand_total, status, items_json)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (bin_row[0], bin_row[1], bin_row[2], bin_row[3], bin_row[4], bin_row[5], bin_row[6], bin_row[7], bin_row[8], bin_row[9], bin_row[10], bin_row[11], bin_row[12]))
                                cursor.execute("DELETE FROM deleted_documents WHERE id = ?", (int(restore_id),))
                                conn.commit()
                                st.success("Document successfully restored!")
                                st.rerun()
                    with col_r2:
                        if st.button("❌ Delete Permanently", type="primary"):
                            cursor.execute("DELETE FROM deleted_documents WHERE id = ?", (int(restore_id),))
                            conn.commit()
                            st.warning("Document permanently deleted.")
                            st.rerun()
                else:
                    st.info("Recycle bin is currently empty.")
    else:
        st.info("No documents generated yet. Create one from the sidebar menu!")

# --- 3. CLIENT DIRECTORY ---
elif choice == "Client Directory":
    st.header("📇 Client Directory")
    
    clients_df = pd.read_sql_query("SELECT id, name, phone, email, address, state, tax_id FROM clients ORDER BY name ASC", conn)
    
    with st.form("add_client_form", clear_on_submit=True):
        st.subheader("Add New Client Profile")
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            new_c_name = st.text_input("Client / Business Name")
            new_c_phone = st.text_input("Phone Number")
            new_c_email = st.text_input("Email Address")
        with c_col2:
            new_c_state = st.text_input("State", value="Karnataka")
            new_c_gstin = st.text_input("GSTIN / Tax ID")
            new_c_addr = st.text_area("Billing Address")
            
        submitted_client = st.form_submit_button("Save Client")
        if submitted_client and new_c_name:
            cursor.execute("INSERT INTO clients (name, phone, email, address, state, tax_id) VALUES (?, ?, ?, ?, ?, ?)",
                           (new_c_name, new_c_phone, new_c_email, new_c_addr, new_c_state, new_c_gstin))
            conn.commit()
            st.success(f"Client '{new_c_name}' added successfully!")
            st.rerun()

    st.divider()
    st.subheader("Existing Clients Register")
    if not clients_df.empty:
        st.dataframe(clients_df, use_container_width=True)
    else:
        st.info("No clients registered yet.")
