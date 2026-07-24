import io
import sqlite3
from datetime import datetime
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# --- PAGE CONFIGURATION & SIZE DICTIONARY ---
PAGE_SIZES = {
    "A4 (Standard)": (595.27, 841.89),
    "Letter (US Standard)": (612.00, 792.00),
    "Legal (US Business)": (612.00, 1008.00),
    "A5 (Compact)": (419.53, 595.27)
}

st.set_page_config(page_title="Nexus Billing & Operations", page_icon="🧾", layout="wide")

# --- DATABASE SETUP ---
conn = sqlite3.connect("nexus_billing.db", check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name TEXT,
            account_holder TEXT,
            account_number TEXT,
            ifsc_code TEXT,
            upi_id TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_type TEXT,
            doc_num TEXT,
            client_name TEXT,
            grand_total REAL,
            doc_date TEXT,
            is_deleted INTEGER DEFAULT 0
        )
    """)
    conn.commit()

init_db()

# Seed default settings if empty
DEFAULT_SETTINGS = {
    'company_name': 'NEXUS CENTER OF EVENTS',
    'company_sub': 'Event Planning, Execution & Corporate Management',
    'company_addr': 'Bangalore, Karnataka, India',
    'company_state': 'Karnataka',
    'company_phone': '+91 98765 43210',
    'company_email': 'info@nexusevents.com',
    'company_gstin': '29AAAAA0000A1Z5',
    'terms_conditions': '1. Payment due within 15 days of invoice date.\n2. Quote invoice # on payment.\n3. Subject to Bangalore jurisdiction.'
}

for k, v in DEFAULT_SETTINGS.items():
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
conn.commit()

def get_setting(key, default=''):
    row = cursor.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default

def get_logo_from_db():
    row = cursor.execute("SELECT value FROM settings WHERE key = 'company_logo'").fetchone()
    return row[0] if row and row[0] else None

# --- STREAMLIT SIDEBAR PRINT PAGE SETUP & DROPDOWN ---
st.sidebar.markdown("---")
st.sidebar.subheader("🖨️ Document Print Settings")
selected_page_size_name = st.sidebar.selectbox(
    "Select Print Page Size",
    options=list(PAGE_SIZES.keys()),
    index=0,
    help="Choose the target page size format for PDF generation and dynamic watermark scaling."
)
target_page_width, target_page_height = PAGE_SIZES[selected_page_size_name]

# --- DYNAMIC WATERMARK CANVAS CALLBACK (AUTO-ADJUSTS TO SELECTED PAGE SIZE) ---
def draw_watermark(canvas, doc):
    try:
        canvas.saveState()
        
        # Dynamically retrieve exact dimensions of the active page from doc or canvas
        page_width, page_height = getattr(doc, 'pagesize', (canvas._pagesize[0], canvas._pagesize[1]))
        
        watermark_text = get_setting('company_name', DEFAULT_SETTINGS['company_name']).upper()
        
        # Calculate dynamic font size scaling based on page width to prevent any letter cutoff
        dynamic_font_size = max(24, int(page_width * 0.068))
        canvas.setFont("Helvetica-Bold", dynamic_font_size)
        canvas.setFillColor(colors.HexColor("#0F172A"), alpha=0.08)
        
        # Perfectly center and balance translation based on text length and rotation angle
        canvas.translate((page_width / 2.0) - (len(watermark_text) * 1.2), (page_height / 2.0) - (dynamic_font_size * 0.8))
        canvas.rotate(30)
        canvas.drawCentredString(0, 0, watermark_text)
        canvas.restoreState()
    except Exception:
        pass

# --- PROFESSIONAL PDF GENERATOR ENGINE ---
def generate_pdf(doc_type, doc_num, client_name, client_phone, client_gstin, client_state, doc_date, items, subtotal, tax_amt, grand_total, bank_details=None, is_duplicate=False, theme="Modern Minimalist (Clean Slate)", is_non_tax=False, page_size_tuple=(595.27, 841.89)):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page_size_tuple, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
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

    total_page_width = page_size_tuple[0]
    printable_width = total_page_width - 72.0
    left_col_width = printable_width * 0.592
    right_col_width = printable_width - left_col_width

    header_table = Table([[left_header_content, meta_info_p]], colWidths=[left_col_width, right_col_width])
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

    client_table = Table([[client_p, gst_info_p]], colWidths=[left_col_width, right_col_width])
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
        col_w = [30, printable_width - 280, 50, 100, 100]
    elif is_intra_state:
        table_data = [[
            Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr),
            Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr),
            Paragraph("Amount (Rs.)", table_hdr),
            Paragraph("CGST", table_hdr), Paragraph("SGST", table_hdr), Paragraph("Total (Rs.)", table_hdr)
        ]]
        col_w = [25, printable_width - 345, 35, 65, 75, 45, 45, 55]
    else:
        table_data = [[
            Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr),
            Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr),
            Paragraph("Amount (Rs.)", table_hdr),
            Paragraph("IGST", table_hdr), Paragraph("Total (Rs.)", table_hdr)
        ]]
        col_w = [25, printable_width - 330, 40, 70, 80, 50, 65]

    sample_items = items if items else [{'desc': 'Event Management & Logistics Support', 'qty': 1, 'rate': 15000.0, 'tax_rate': 18.0}]

    for idx, item in enumerate(sample_items, start=1):
        line_sub = item['qty'] * item['rate']
        tax_rate = item.get('tax_rate', 18.0)
        if is_non_tax:
            line_total = line_sub
            table_data.append([
                Paragraph(str(idx), table_cell), Paragraph(item['desc'], table_cell),
                Paragraph(str(item['qty']), table_cell_r), Paragraph(f"Rs. {item['rate']:,.2f}", table_cell_r),
                Paragraph(f"Rs. {line_total:,.2f}", table_cell_r)
            ])
        else:
            line_tax = line_sub * (tax_rate / 100)
            line_total = line_sub + line_tax
            if is_intra_state:
                half_tax_pct = tax_rate / 2
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
                    Paragraph(f"{tax_rate}%", table_cell_r), Paragraph(f"Rs. {line_total:,.2f}", table_cell_r)
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

    summary_table = Table(summary_table_data, colWidths=[printable_width - 160, 160])
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
        footer_table = Table([[terms_p]], colWidths=[printable_width])
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
        half_footer_w = printable_width / 2.0
        footer_table = Table([[pay_p, terms_p]], colWidths=[half_footer_w, printable_width - half_footer_w])

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

# --- STREAMLIT UI APP INTERFACE ---
st.title("🧾 Nexus Center of Events - Document Suite")
st.write("Generate fully responsive professional documents with dynamic page sizing and auto-adjusting watermarks.")

with st.form("invoice_form"):
    col1, col2 = st.columns(2)
    with col1:
        doc_type = st.selectbox("Document Type", ["Tax Invoice", "Delivery Challan", "Bill of Supply", "Estimate / Quotation"])
        doc_num = st.text_input("Document Number", value="INV-2026-001")
        client_name = st.text_input("Client Name", value="Acme Corporation")
    with col2:
        doc_date = st.text_input("Date", value=datetime.now().strftime("%Y-%m-%d"))
        client_state = st.text_input("Client State", value="Karnataka")
        theme = st.selectbox("Visual Theme", ["Modern Minimalist (Clean Slate)", "Executive Dark (Bold & Corporate)", "Creative Vibrant (Blue & Slate)", "Warm Editorial (Classic & Refined)"])
    
    submitted = st.form_submit_button("Generate & Download PDF")

if submitted:
    pdf_buffer = generate_pdf(
        doc_type=doc_type,
        doc_num=doc_num,
        client_name=client_name,
        client_phone="+91 90000 11111",
        client_gstin="29BBBBB1111B1Z2",
        client_state=client_state,
        doc_date=doc_date,
        items=[{'desc': 'Corporate Stage Setup & Lighting', 'qty': 1, 'rate': 25000.0, 'tax_rate': 18.0}],
        subtotal=25000.0,
        tax_amt=4500.0,
        grand_total=29500.0,
        theme=theme,
        page_size_tuple=(target_page_width, target_page_height)
    )
    st.success(f"Document generated successfully using {selected_page_size_name} format!")
    st.download_button(
        label="📥 Download PDF Document",
        data=pdf_buffer,
        file_name=f"{doc_num}.pdf",
        mime="application/pdf"
    )
