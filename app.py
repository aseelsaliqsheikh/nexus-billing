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

# --- NAVIGATION & APP TABS ---
st.title("🧾 Nexus Center of Events - Document Suite")
st.write("Manage your events, clients, bank accounts, and generate fully responsive professional PDFs with dynamic sizing and watermarks.")

tabs = st.tabs(["📄 Generate Document", "⚙️ Company Settings", "🏦 Bank Accounts", "📊 Document History"])

# --- TAB 1: GENERATE DOCUMENT ---
with tabs[0]:
    st.subheader("Generate Professional Document")
    
    # Sidebar control for page sizing specific to printing
    st.sidebar.markdown("---")
    st.sidebar.subheader("🖨️ Document Print Settings")
    selected_page_size_name = st.sidebar.selectbox(
        "Select Print Page Size",
        options=list(PAGE_SIZES.keys()),
        index=0,
        help="Choose target page size format for PDF generation and dynamic watermark scaling."
    )
    target_page_width, target_page_height = PAGE_SIZES[selected_page_size_name]

    with st.form("invoice_form"):
        col1, col2 = st.columns(2)
        with col1:
            doc_type = st.selectbox("Document Type", ["Tax Invoice", "Delivery Challan", "Bill of Supply", "Estimate / Quotation"])
            doc_num = st.text_input("Document Number", value="INV-2026-001")
            client_name = st.text_input("Client Name", value="Acme Corporation")
            client_phone = st.text_input("Client Phone", value="+91 90000 11111")
        with col2:
            doc_date = st.text_input("Date", value=datetime.now().strftime("%Y-%m-%d"))
            client_state = st.text_input("Client State", value="Karnataka")
            client_gstin = st.text_input("Client GSTIN", value="29BBBBB1111B1Z2")
            theme = st.selectbox("Visual Theme", ["Modern Minimalist (Clean Slate)", "Executive Dark (Bold & Corporate)", "Creative Vibrant (Blue & Slate)", "Warm Editorial (Classic & Refined)"])
        
        st.markdown("---")
        st.write("### Line Items")
        item_desc = st.text_input("Item / Service Description", value="Corporate Stage Setup & Lighting")
        col_item1, col_item2, col_item3 = st.columns(3)
        with col_item1:
            item_qty = st.number_input("Quantity", min_value=1, value=1)
        with col_item2:
            item_rate = st.number_input("Rate (Rs.)", min_value=0.0, value=25000.0, step=500.0)
        with col_item3:
            item_tax_rate = st.number_input("Tax Rate (%)", min_value=0.0, value=18.0, step=1.0)

        submitted = st.form_submit_button("Generate & Download PDF")

    if submitted:
        subtotal = item_qty * item_rate
        is_non_tax = ("Bill of Supply" in doc_type) or ("Delivery Challan" in doc_type) or ("Estimate" in doc_type)
        tax_amt = 0.0 if is_non_tax else subtotal * (item_tax_rate / 100.0)
        grand_total = subtotal + tax_amt

        # --- DYNAMIC WATERMARK CANVAS CALLBACK ---
        def draw_watermark(canvas, doc):
            try:
                canvas.saveState()
                page_width, page_height = getattr(doc, 'pagesize', (canvas._pagesize[0], canvas._pagesize[1]))
                watermark_text = get_setting('company_name', DEFAULT_SETTINGS['company_name']).upper()
                dynamic_font_size = max(24, int(page_width * 0.068))
                canvas.setFont("Helvetica-Bold", dynamic_font_size)
                canvas.setFillColor(colors.HexColor("#0F172A"), alpha=0.08)
                canvas.translate((page_width / 2.0) - (len(watermark_text) * 1.2), (page_height / 2.0) - (dynamic_font_size * 0.8))
                canvas.rotate(30)
                canvas.drawCentredString(0, 0, watermark_text)
                canvas.restoreState()
            except Exception:
                pass

        # --- PROFESSIONAL PDF GENERATOR ENGINE ---
        def generate_pdf():
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=(target_page_width, target_page_height), rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
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
            if logo_container: logo_container.hAlign = 'LEFT'

            meta_info_p = [
                Paragraph(f"{doc_type.upper()}", doc_type_style),
                Spacer(1, 4),
                Paragraph(f"<b>Document No:</b> {doc_num}", ParagraphStyle('M1', parent=meta_label, alignment=2)),
                Paragraph(f"<b>Date:</b> {doc_date}", ParagraphStyle('M2', parent=meta_label, alignment=2)),
                Paragraph(f"<b>Place of Supply:</b> {client_state if client_state else comp_state_str}", ParagraphStyle('M3', parent=meta_label, alignment=2))
            ]

            is_delivery_challan = ("Delivery Challan" in doc_type)
            company_gstin_line = "<b>Delivery Challan (Goods Transport)</b>" if is_delivery_challan else ("<b>Non-Tax Invoice</b>" if is_non_tax else f"<b>GSTIN:</b> {comp_gstin_str}")

            company_info_p = [
                Paragraph(comp_name_str, comp_title_style),
                Paragraph(f"<b>{comp_sub_str}</b>", comp_sub_style),
                Paragraph(comp_addr_str, comp_sub_style),
                Paragraph(f"Phone: {comp_phone_str} | Email: {comp_email_str}", comp_sub_style),
                Paragraph(company_gstin_line, comp_sub_style)
            ]

            left_header_content = [logo_container, Spacer(1, 4), company_info_p] if logo_container else company_info_p
            printable_width = target_page_width - 72.0
            left_col_width = printable_width * 0.592
            right_col_width = printable_width - left_col_width

            header_table = Table([[left_header_content, meta_info_p]], colWidths=[left_col_width, right_col_width])
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
            
            gst_info_p = [
                Paragraph("<b>TAX REGIME & DETAILS:</b>", ParagraphStyle('TReg', parent=styles['Normal'], fontSize=9, textColor=PRIMARY, fontName="Helvetica-Bold")),
                Paragraph(f"Tax Treatment: <b>{'Intra-State (CGST + SGST)' if is_intra_state else 'Inter-State (IGST)'}</b>", meta_label),
                Paragraph(f"Supplier GSTIN: <b>{comp_gstin_str}</b>", meta_label),
                Paragraph(f"Status: <b>Active Record</b>", meta_label)
            ]

            client_table = Table([[client_p, gst_info_p]], colWidths=[left_col_width, right_col_width])
            client_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), ACCENT_BG), ('PADDING', (0,0), (-1,-1), 8), ('BOX', (0,0), (-1,-1), 0.5, BORDER_CLR), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(client_table)
            story.append(Spacer(1, 10))

            if is_non_tax:
                table_data = [[Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr), Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr), Paragraph("Total (Rs.)", table_hdr)]]
                col_w = [30, printable_width - 280, 50, 100, 100]
                line_total = subtotal
                table_data.append([Paragraph("1", table_cell), Paragraph(item_desc, table_cell), Paragraph(str(item_qty), table_cell_r), Paragraph(f"Rs. {item_rate:,.2f}", table_cell_r), Paragraph(f"Rs. {line_total:,.2f}", table_cell_r)])
            elif is_intra_state:
                table_data = [[Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr), Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr), Paragraph("Amount", table_hdr), Paragraph("CGST", table_hdr), Paragraph("SGST", table_hdr), Paragraph("Total", table_hdr)]]
                col_w = [25, printable_width - 345, 35, 65, 75, 45, 45, 55]
                half_tax_pct = item_tax_rate / 2
                table_data.append([Paragraph("1", table_cell), Paragraph(item_desc, table_cell), Paragraph(str(item_qty), table_cell_r), Paragraph(f"Rs. {item_rate:,.2f}", table_cell_r), Paragraph(f"Rs. {subtotal:,.2f}", table_cell_r), Paragraph(f"{half_tax_pct:.1f}%", table_cell_r), Paragraph(f"{half_tax_pct:.1f}%", table_cell_r), Paragraph(f"Rs. {grand_total:,.2f}", table_cell_r)])
            else:
                table_data = [[Paragraph("#", table_hdr), Paragraph("Item / Service Description", table_hdr), Paragraph("Qty", table_hdr), Paragraph("Rate (Rs.)", table_hdr), Paragraph("Amount", table_hdr), Paragraph("IGST", table_hdr), Paragraph("Total", table_hdr)]]
                col_w = [25, printable_width - 330, 40, 70, 80, 50, 65]
                table_data.append([Paragraph("1", table_cell), Paragraph(item_desc, table_cell), Paragraph(str(item_qty), table_cell_r), Paragraph(f"Rs. {item_rate:,.2f}", table_cell_r), Paragraph(f"Rs. {subtotal:,.2f}", table_cell_r), Paragraph(f"{item_tax_rate}%", table_cell_r), Paragraph(f"Rs. {grand_total:,.2f}", table_cell_r)])

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

            summary_table_data = [[Paragraph(r[0], tot_label_style if r[0] != "Grand Total:" else ParagraphStyle('GTL', parent=tot_label_style, fontSize=11, textColor=PRIMARY)), Paragraph(r[1], table_cell_r if r[0] != "Grand Total:" else tot_val_style)] for r in summary_rows]
            summary_table = Table(summary_table_data, colWidths=[printable_width - 160, 160])
            summary_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'RIGHT'), ('PADDING', (0,0), (-1,-1), 4), ('LINEABOVE', (0,-1), (-1,-1), 1, PRIMARY)]))
            story.append(summary_table)
            story.append(Spacer(1, 12))

            formatted_terms = terms_str.replace('\n', '<br/>')
            terms_p = [Paragraph("<b>TERMS & CONDITIONS:</b>", ParagraphStyle('THead', parent=styles['Normal'], fontSize=8.5, textColor=PRIMARY, fontName="Helvetica-Bold")), Spacer(1, 2), Paragraph(formatted_terms, meta_label)]
            
            bank_text = f"<b>Account Holder:</b> {acc_holder_str}<br/><b>Bank:</b> {bank_name_str} | <b>Account No:</b> {acc_num_str}<br/><b>IFSC:</b> {ifsc_str} | <b>UPI ID:</b> {upi_str}"
            pay_p = [Paragraph("<b>PAYMENT REMITTANCE:</b>", ParagraphStyle('PHead', parent=styles['Normal'], fontSize=8.5, textColor=PRIMARY, fontName="Helvetica-Bold")), Spacer(1, 2), Paragraph(bank_text, meta_label)]
            
            half_footer_w = printable_width / 2.0
            footer_table = Table([[pay_p, terms_p]], colWidths=[half_footer_w, printable_width - half_footer_w])
            footer_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), ACCENT_BG), ('PADDING', (0,0), (-1,-1), 8), ('BOX', (0,0), (-1,-1), 0.5, BORDER_CLR), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(footer_table)

            doc.build(story, onFirstPage=draw_watermark, onLaterPages=draw_watermark)
            buffer.seek(0)
            return buffer

        pdf_buffer = generate_pdf()
        
        # Save record to database history
        cursor.execute("INSERT INTO documents (doc_type, doc_num, client_name, grand_total, doc_date) VALUES (?, ?, ?, ?, ?)",
                       (doc_type, doc_num, client_name, grand_total, doc_date))
        conn.commit()

        st.success(f"Document {doc_num} generated successfully using {selected_page_size_name} format!")
        st.download_button(label="📥 Download PDF Document", data=pdf_buffer, file_name=f"{doc_num}.pdf", mime="application/pdf")

# --- TAB 2: COMPANY SETTINGS ---
with tabs[1]:
    st.subheader("⚙️ Company Settings & Profile")
    with st.form("settings_form"):
        c_name = st.text_input("Company Name", value=get_setting('company_name', DEFAULT_SETTINGS['company_name']))
        c_sub = st.text_input("Company Subtitle / Tagline", value=get_setting('company_sub', DEFAULT_SETTINGS['company_sub']))
        c_addr = st.text_area("Address", value=get_setting('company_addr', DEFAULT_SETTINGS['company_addr']))
        c_state = st.text_input("State", value=get_setting('company_state', DEFAULT_SETTINGS['company_state']))
        c_phone = st.text_input("Phone", value=get_setting('company_phone', DEFAULT_SETTINGS['company_phone']))
        c_email = st.text_input("Email", value=get_setting('company_email', DEFAULT_SETTINGS['company_email']))
        c_gstin = st.text_input("GSTIN", value=get_setting('company_gstin', DEFAULT_SETTINGS['company_gstin']))
        c_terms = st.text_area("Default Terms & Conditions", value=get_setting('terms_conditions', DEFAULT_SETTINGS['terms_conditions']))
        
        save_settings = st.form_submit_button("Save Settings")
        if save_settings:
            cursor.execute("REPLACE INTO settings (key, value) VALUES ('company_name', ?)", (c_name,))
            cursor.execute("REPLACE INTO settings (key, value) VALUES ('company_sub', ?)", (c_sub,))
            cursor.execute("REPLACE INTO settings (key, value) VALUES ('company_addr', ?)", (c_addr,))
            cursor.execute("REPLACE INTO settings (key, value) VALUES ('company_state', ?)", (c_state,))
            cursor.execute("REPLACE INTO settings (key, value) VALUES ('company_phone', ?)", (c_phone,))
            cursor.execute("REPLACE INTO settings (key, value) VALUES ('company_email', ?)", (c_email,))
            cursor.execute("REPLACE INTO settings (key, value) VALUES ('company_gstin', ?)", (c_gstin,))
            cursor.execute("REPLACE INTO settings (key, value) VALUES ('terms_conditions', ?)", (c_terms,))
            conn.commit()
            st.success("Company settings updated successfully!")

# --- TAB 3: BANK ACCOUNTS ---
with tabs[2]:
    st.subheader("🏦 Bank Account Management")
    with st.form("bank_form"):
        b_name = st.text_input("Bank Name", value="HDFC Bank")
        b_holder = st.text_input("Account Holder Name", value="Nexus Center of Events")
        b_num = st.text_input("Account Number", value="50200012345678")
        b_ifsc = st.text_input("IFSC Code", value="HDFC0001234")
        b_upi = st.text_input("UPI ID", value="nexus@upi")
        
        add_bank = st.form_submit_button("Add / Update Bank Account")
        if add_bank:
            cursor.execute("INSERT INTO bank_accounts (bank_name, account_holder, account_number, ifsc_code, upi_id) VALUES (?, ?, ?, ?, ?)",
                           (b_name, b_holder, b_num, b_ifsc, b_upi))
            conn.commit()
            st.success("Bank account added successfully!")

    st.markdown("### Saved Bank Accounts")
    banks = cursor.execute("SELECT id, bank_name, account_number, ifsc_code, upi_id FROM bank_accounts").fetchall()
    for b in banks:
        st.info(f"**{b[1]}** | A/C: {b[2]} | IFSC: {b[3]} | UPI: {b[4]}")

# --- TAB 4: DOCUMENT HISTORY ---
with tabs[3]:
    st.subheader("📊 Generated Documents History")
    docs = cursor.execute("SELECT id, doc_type, doc_num, client_name, grand_total, doc_date FROM documents ORDER BY id DESC").fetchall()
    if docs:
        for d in docs:
            st.write(f"**{d[1]}** (#`{d[2]}`) | Client: **{d[3]}** | Total: **Rs. {d[4]:,.2f}** | Date: {d[5]}")
    else:
        st.write("No documents generated yet.")
