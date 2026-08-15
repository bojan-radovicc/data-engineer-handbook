"""
Databricks App: a small support-ticket system backed by Lakebase.

All data comes from the tables created by sql/01_schema.sql and seeded by
sql/02_seed.sql:

    support.tickets(ticket_id, title, status, priority, category,
                    created_by, created_at, updated_at)
    support.ticket_messages(message_id, ticket_id, message_text,
                            author, created_at)

The Lakebase connection lives in lakebase.py (a single LAKEBASE_URL secret).

Run locally:
    python app.py
Deploy as a Databricks App using app.yaml.
"""

import logging
import os

from flask import Flask, jsonify, render_template_string, request

import lakebase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("support-app")

app = Flask(__name__)

SCHEMA = os.environ.get("SUPPORT_SCHEMA", "support")

STATUSES = ("open", "in_progress", "resolved")
PRIORITIES = ("low", "medium", "high", "urgent")


def _current_user() -> str:
    """Databricks Apps forwards the signed-in user's email on every request."""
    return request.headers.get("X-Forwarded-Email") or "anonymous@local"


def _body() -> dict:
    return request.get_json(silent=True) or request.form.to_dict()


def _write_returning(sql: str, params: tuple) -> dict:
    """Run an INSERT/UPDATE ... RETURNING and return the resulting row."""
    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            conn.commit()
            return row


@app.errorhandler(Exception)
def handle_exception(err):
    """Always answer with JSON so the frontend's resp.json() never sees HTML."""
    logger.exception("Unhandled exception while processing request")
    code = getattr(err, "code", 500)
    return jsonify({"error": str(err)}), code if isinstance(code, int) else 500


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/tickets")
def list_tickets():
    """All tickets, newest first, with a message count. Optional ?status= filter."""
    status = request.args.get("status")
    if status and status not in STATUSES:
        return jsonify({"error": f"Unknown status: {status}"}), 400

    sql = f"""
        SELECT t.ticket_id, t.title, t.status, t.priority, t.category,
               t.created_by, t.created_at, t.updated_at,
               COUNT(m.message_id) AS message_count
        FROM {SCHEMA}.tickets t
        LEFT JOIN {SCHEMA}.ticket_messages m ON m.ticket_id = t.ticket_id
        {"WHERE t.status = %s" if status else ""}
        GROUP BY t.ticket_id
        ORDER BY t.updated_at DESC
    """
    return jsonify(lakebase.run_query(sql, (status,) if status else None))


@app.route("/tickets/<int:ticket_id>")
def get_ticket(ticket_id):
    """One ticket plus its messages, oldest first."""
    tickets = lakebase.run_query(
        f"SELECT * FROM {SCHEMA}.tickets WHERE ticket_id = %s", (ticket_id,)
    )
    if not tickets:
        return jsonify({"error": f"No ticket with id {ticket_id}"}), 404

    messages = lakebase.run_query(
        f"""SELECT message_id, message_text, author, created_at
            FROM {SCHEMA}.ticket_messages
            WHERE ticket_id = %s
            ORDER BY created_at ASC""",
        (ticket_id,),
    )
    return jsonify({"ticket": tickets[0], "messages": messages})


@app.route("/tickets", methods=["POST"])
def create_ticket():
    """Create a ticket. Only `title` is required."""
    body = _body()
    title = (body.get("title") or "").strip()
    priority = (body.get("priority") or "medium").strip()

    if not title:
        return jsonify({"error": "Title is required"}), 400
    if priority not in PRIORITIES:
        return jsonify({"error": f"Priority must be one of {list(PRIORITIES)}"}), 400

    ticket = _write_returning(
        f"""INSERT INTO {SCHEMA}.tickets (title, priority, category, created_by)
            VALUES (%s, %s, %s, %s)
            RETURNING *""",
        (title, priority, (body.get("category") or "").strip() or None, _current_user()),
    )
    return jsonify(ticket), 201


@app.route("/tickets/<int:ticket_id>/messages", methods=["POST"])
def add_message(ticket_id):
    """Add a message to an existing ticket."""
    text = (_body().get("message_text") or "").strip()
    if not text:
        return jsonify({"error": "Message text is required"}), 400

    ticket = _write_returning(
        f"UPDATE {SCHEMA}.tickets SET updated_at = now() WHERE ticket_id = %s RETURNING ticket_id",
        (ticket_id,),
    )
    if not ticket:
        return jsonify({"error": f"No ticket with id {ticket_id}"}), 404

    message = _write_returning(
        f"""INSERT INTO {SCHEMA}.ticket_messages (ticket_id, message_text, author)
            VALUES (%s, %s, %s)
            RETURNING *""",
        (ticket_id, text, _current_user()),
    )
    return jsonify(message), 201


@app.route("/tickets/<int:ticket_id>/status", methods=["POST"])
def update_status(ticket_id):
    """Move a ticket between open / in_progress / resolved."""
    status = (_body().get("status") or "").strip()
    if status not in STATUSES:
        return jsonify({"error": f"Status must be one of {list(STATUSES)}"}), 400

    ticket = _write_returning(
        f"""UPDATE {SCHEMA}.tickets
            SET status = %s, updated_at = now()
            WHERE ticket_id = %s
            RETURNING *""",
        (status, ticket_id),
    )
    if not ticket:
        return jsonify({"error": f"No ticket with id {ticket_id}"}), 404
    return jsonify(ticket)


@app.route("/tickets/<int:ticket_id>", methods=["DELETE"])
def delete_ticket(ticket_id):
    """Delete a ticket; its messages cascade via the foreign key."""
    deleted = lakebase.run_write(
        f"DELETE FROM {SCHEMA}.tickets WHERE ticket_id = %s", (ticket_id,)
    )
    if not deleted:
        return jsonify({"error": f"No ticket with id {ticket_id}"}), 404
    return jsonify({"deleted": ticket_id})


@app.route("/stats")
def stats():
    """Ticket counts by status, plus the total message count."""
    rows = lakebase.run_query(
        f"""SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'open')        AS open,
                   COUNT(*) FILTER (WHERE status = 'in_progress') AS in_progress,
                   COUNT(*) FILTER (WHERE status = 'resolved')    AS resolved,
                   (SELECT COUNT(*) FROM {SCHEMA}.ticket_messages) AS messages
            FROM {SCHEMA}.tickets"""
    )
    return jsonify(rows[0])


INDEX_HTML = """
<!doctype html>
<title>Lakebase Support</title>
<style>
  body { font: 15px system-ui, sans-serif; margin: 0; background: #f6f7f9; color: #1b1f24; }
  header { background: #fff; border-bottom: 1px solid #e3e6ea; padding: 16px 24px; }
  header h1 { margin: 0; font-size: 18px; }
  #stats { color: #5b6572; font-size: 13px; margin-top: 4px; }
  main { display: grid; grid-template-columns: 380px 1fr; gap: 20px; padding: 20px 24px; align-items: start; }
  .card { background: #fff; border: 1px solid #e3e6ea; border-radius: 8px; padding: 16px; }
  .ticket { padding: 10px; border-radius: 6px; cursor: pointer; border: 1px solid transparent; }
  .ticket:hover, .ticket.active { background: #f0f4ff; border-color: #c7d6ff; }
  .ticket h3 { margin: 0 0 4px; font-size: 14px; }
  .meta { color: #5b6572; font-size: 12px; }
  .badge { display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: 11px; background: #e8ebef; }
  .open { background: #dcefff; } .in_progress { background: #fff0cc; } .resolved { background: #d9f5e3; }
  .msg { border-top: 1px solid #eef0f3; padding: 10px 0; }
  input, select, textarea, button { font: inherit; padding: 7px; border: 1px solid #ccd2da; border-radius: 6px; }
  button { background: #1b64f2; color: #fff; border-color: #1b64f2; cursor: pointer; }
  form { display: grid; gap: 8px; margin-top: 12px; }
  .row { display: flex; gap: 8px; align-items: center; }
  #error { color: #b3261e; font-size: 13px; }
</style>
<header>
  <h1>Lakebase Support</h1>
  <div id="stats"></div>
</header>
<main>
  <div class="card">
    <div class="row">
      <strong style="flex:1">Tickets</strong>
      <select id="filter" onchange="loadTickets()">
        <option value="">all statuses</option>
        <option>open</option><option>in_progress</option><option>resolved</option>
      </select>
    </div>
    <div id="tickets"></div>
    <form onsubmit="createTicket(event)">
      <strong>New ticket</strong>
      <input id="title" placeholder="Title" required>
      <div class="row">
        <select id="priority"><option>low</option><option selected>medium</option><option>high</option><option>urgent</option></select>
        <input id="category" placeholder="Category (optional)" style="flex:1">
      </div>
      <button>Create ticket</button>
    </form>
    <div id="error"></div>
  </div>
  <div class="card" id="detail">Select a ticket to see its messages.</div>
</main>
<script>
let current = null;

async function api(url, method, body) {
  const res = await fetch(url, method ? {
    method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  } : undefined);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

const fail = (e) => document.getElementById('error').textContent = e.message;

async function loadStats() {
  const s = await api('/stats');
  document.getElementById('stats').textContent =
    `${s.total} tickets — ${s.open} open, ${s.in_progress} in progress, ${s.resolved} resolved, ${s.messages} messages`;
}

async function loadTickets() {
  const status = document.getElementById('filter').value;
  const tickets = await api('/tickets' + (status ? '?status=' + status : ''));
  document.getElementById('tickets').innerHTML = tickets.map(t => `
    <div class="ticket ${t.ticket_id === current ? 'active' : ''}" onclick="openTicket(${t.ticket_id})">
      <h3>${t.title}</h3>
      <div class="meta">
        <span class="badge ${t.status}">${t.status}</span>
        <span class="badge">${t.priority}</span>
        ${t.message_count} msg · ${t.created_by}
      </div>
    </div>`).join('') || '<p class="meta">No tickets.</p>';
  loadStats();
}

async function openTicket(id) {
  current = id;
  const {ticket, messages} = await api('/tickets/' + id);
  document.getElementById('detail').innerHTML = `
    <h2 style="margin-top:0">${ticket.title}</h2>
    <div class="row meta">
      <select id="status" onchange="setStatus()">
        ${['open','in_progress','resolved'].map(s =>
          `<option ${s === ticket.status ? 'selected' : ''}>${s}</option>`).join('')}
      </select>
      <span>${ticket.priority}${ticket.category ? ' · ' + ticket.category : ''} · opened by ${ticket.created_by}</span>
      <button style="margin-left:auto;background:#b3261e;border-color:#b3261e" onclick="removeTicket()">Delete</button>
    </div>
    ${messages.map(m => `<div class="msg"><strong>${m.author}</strong>
        <span class="meta">${new Date(m.created_at).toLocaleString()}</span>
        <div>${m.message_text}</div></div>`).join('')}
    <form onsubmit="postMessage_(event)">
      <textarea id="message_text" rows="3" placeholder="Write a reply..." required></textarea>
      <button>Add message</button>
    </form>`;
  loadTickets();
}

async function createTicket(e) {
  e.preventDefault();
  try {
    const t = await api('/tickets', 'POST', {
      title: document.getElementById('title').value,
      priority: document.getElementById('priority').value,
      category: document.getElementById('category').value,
    });
    e.target.reset();
    document.getElementById('error').textContent = '';
    await loadTickets();
    openTicket(t.ticket_id);
  } catch (err) { fail(err); }
}

async function postMessage_(e) {
  e.preventDefault();
  try {
    await api(`/tickets/${current}/messages`, 'POST',
              {message_text: document.getElementById('message_text').value});
    openTicket(current);
  } catch (err) { fail(err); }
}

async function setStatus() {
  try {
    await api(`/tickets/${current}/status`, 'POST',
              {status: document.getElementById('status').value});
    openTicket(current);
  } catch (err) { fail(err); }
}

async function removeTicket() {
  if (!confirm('Delete this ticket and all of its messages?')) return;
  try {
    await api('/tickets/' + current, 'DELETE');
    current = null;
    document.getElementById('detail').textContent = 'Select a ticket to see its messages.';
    loadTickets();
  } catch (err) { fail(err); }
}

loadTickets();
</script>
"""


@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_RUN_PORT", 8000))
    app.run(debug=True, host=host, port=port)
