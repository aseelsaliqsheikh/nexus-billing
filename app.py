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
