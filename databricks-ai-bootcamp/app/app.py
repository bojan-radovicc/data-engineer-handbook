"""Lakebase-powered support app (Day 1 homework).

A Streamlit Databricks App that reads from and writes to Lakebase. It lets a
user browse tickets, read a ticket's messages, create tickets, post messages,
change status, and delete tickets. All data lives in Lakebase — nothing is
hard-coded.
"""

import streamlit as st

import db

STATUSES = ["open", "in_progress", "resolved"]
PRIORITIES = ["low", "medium", "high", "urgent"]
STATUS_LABEL = {"open": "🟢 Open", "in_progress": "🟡 In progress", "resolved": "✅ Resolved"}
PRIORITY_LABEL = {"low": "Low", "medium": "Medium", "high": "High", "urgent": "🔴 Urgent"}

st.set_page_config(page_title="Lakebase Support", page_icon="🎫", layout="wide")


def show_stats() -> None:
    try:
        s = db.stats()
    except Exception as exc:  # surface connection issues clearly
        import os
        st.error(f"Could not reach Lakebase: {exc}")
        present = sorted(
            k for k in os.environ
            if k.startswith(("PG", "POSTGRES", "DATABRICKS", "DB_", "LAKEBASE"))
        )
        st.info("Connection-related env vars the app can see: "
                + (", ".join(present) if present else "(none)"))
        st.info(
            "If PGHOST is missing, the attached database resource isn't exposing "
            "standard PG* vars — map them in app.yaml with `valueFrom` pointing "
            "at the resource, or set LAKEBASE_INSTANCE_NAME so the app mints a token."
        )
        st.stop()
        return  # st.stop() is a no-op without a ScriptRunContext; return anyway
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Tickets", s["total"])
    c2.metric("Open", s["open"])
    c3.metric("In progress", s["in_progress"])
    c4.metric("Resolved", s["resolved"])
    c5.metric("Messages", s["messages"])


def create_ticket_form() -> None:
    with st.sidebar:
        st.header("➕ New ticket")
        with st.form("create_ticket", clear_on_submit=True):
            title = st.text_input("Title")
            created_by = st.text_input("Created by (email)")
            priority = st.selectbox("Priority", PRIORITIES, index=1)
            category = st.text_input("Category (optional)")
            submitted = st.form_submit_button("Create ticket", use_container_width=True)
        if submitted:
            # Input validation with helpful messages (bonus).
            if not title.strip():
                st.sidebar.error("Title is required.")
                return
            if "@" not in created_by:
                st.sidebar.error("Please enter a valid email for 'Created by'.")
                return
            ticket_id = db.create_ticket(
                title.strip(),
                created_by.strip(),
                priority=priority,
                category=category.strip() or None,
            )
            st.session_state.selected = ticket_id
            st.sidebar.success(f"Created ticket #{ticket_id}.")
            st.rerun()


def ticket_detail(ticket_id: int) -> None:
    ticket = db.get_ticket(ticket_id)
    if ticket is None:
        st.warning("That ticket no longer exists.")
        st.session_state.selected = None
        return

    st.subheader(f"#{ticket['ticket_id']} — {ticket['title']}")
    meta = f"{STATUS_LABEL.get(ticket['status'], ticket['status'])} · " \
           f"{PRIORITY_LABEL.get(ticket['priority'], ticket['priority'])}"
    if ticket["category"]:
        meta += f" · {ticket['category']}"
    st.caption(f"{meta} · opened by {ticket['created_by']} on "
               f"{ticket['created_at']:%Y-%m-%d %H:%M}")

    # Update status (bonus-friendly inline control).
    left, right = st.columns([3, 1])
    with left:
        new_status = st.selectbox(
            "Status", STATUSES, index=STATUSES.index(ticket["status"]),
            key=f"status_{ticket_id}",
        )
    with right:
        st.write("")
        st.write("")
        if st.button("Update status", key=f"upd_{ticket_id}", use_container_width=True):
            db.update_status(ticket_id, new_status)
            st.success("Status updated.")
            st.rerun()

    st.divider()
    st.markdown("#### Messages")
    messages = db.list_messages(ticket_id)
    if not messages:
        st.info("No messages yet.")
    for m in messages:
        with st.chat_message("user"):
            st.markdown(f"**{m['author']}** · {m['created_at']:%Y-%m-%d %H:%M}")
            st.write(m["message_text"])

    with st.form(f"add_message_{ticket_id}", clear_on_submit=True):
        author = st.text_input("Your email", key=f"author_{ticket_id}")
        text = st.text_area("Message", key=f"text_{ticket_id}")
        sent = st.form_submit_button("Add message")
    if sent:
        if "@" not in author:
            st.error("Please enter a valid email.")
        elif not text.strip():
            st.error("Message cannot be empty.")
        else:
            db.add_message(ticket_id, text.strip(), author.strip())
            st.rerun()

    st.divider()
    # Delete with confirmation (bonus).
    with st.expander("🗑️ Delete this ticket"):
        st.warning("This permanently deletes the ticket and all its messages.")
        confirm = st.checkbox("Yes, I understand", key=f"confirm_{ticket_id}")
        if st.button("Delete permanently", key=f"del_{ticket_id}", disabled=not confirm):
            db.delete_ticket(ticket_id)
            st.session_state.selected = None
            st.success("Ticket deleted.")
            st.rerun()


def main() -> None:
    st.title("🎫 Lakebase Support")
    st.caption("An internal support system. All data is stored in Lakebase.")

    show_stats()
    create_ticket_form()

    if "selected" not in st.session_state:
        st.session_state.selected = None

    list_col, detail_col = st.columns([1, 2], gap="large")

    with list_col:
        st.markdown("### Tickets")
        # Filter by status (bonus).
        options = ["all", *STATUSES]
        choice = st.radio(
            "Filter", options, horizontal=True,
            format_func=lambda s: "All" if s == "all" else STATUS_LABEL[s],
        )
        tickets = db.list_tickets(None if choice == "all" else choice)
        if not tickets:
            st.info("No tickets match this filter.")
        for t in tickets:
            label = f"#{t['ticket_id']} · {t['title']}"
            sub = f"{STATUS_LABEL.get(t['status'], t['status'])} · " \
                  f"{t['message_count']} msg · {PRIORITY_LABEL.get(t['priority'])}"
            if st.button(label, key=f"open_{t['ticket_id']}", use_container_width=True):
                st.session_state.selected = t["ticket_id"]
                st.rerun()
            st.caption(sub)

    with detail_col:
        if st.session_state.selected is None:
            st.info("Select a ticket on the left, or create one from the sidebar.")
        else:
            ticket_detail(st.session_state.selected)


if __name__ == "__main__":
    main()
