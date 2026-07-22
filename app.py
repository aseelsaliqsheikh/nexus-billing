# --- 📦 LINE ITEMS ---
    if "item_list" not in st.session_state:
        # Pre-load 5 default line items for Nexus Center of Events
        st.session_state.item_list = [
            {"desc": "Event Conceptualization & Theme Design", "qty": 1, "rate": 15000.0, "tax_rate": 18.0},
            {"desc": "Stage Setup & Production Management", "qty": 2, "rate": 25000.0, "tax_rate": 18.0},
            {"desc": "Professional Sound & Lighting System", "qty": 1, "rate": 18000.0, "tax_rate": 18.0},
            {"desc": "On-Ground Operations Supervision & Crew", "qty": 3, "rate": 5000.0, "tax_rate": 18.0},
            {"desc": "Digital Media Coverage & Reel Editing", "qty": 1, "rate": 10000.0, "tax_rate": 18.0}
        ]
