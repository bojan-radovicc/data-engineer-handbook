- **Databricks App URL:** `https://lakebase-app-bojan-2162472151945123.aws.databricksapps.com`

## Reflection (3–5 sentences — DRAFT, edit to your own experience)

**What was the most difficult part?**
Getting the app to authenticate to Lakebase without a hard-coded password —
understanding that the attached database resource injects connection env vars
and that credentials are short-lived tokens rather than a static secret.

**How is Lakebase different from a traditional analytics table?**
Lakebase is a transactional (OLTP) Postgres database built for low-latency,
row-level reads and writes with primary keys, foreign keys, and constraints —
exactly what an app needs. A traditional analytics table (e.g. a Delta table
in the lakehouse) is columnar and optimized for large scans and batch
analytics, not for single-row inserts/updates on every user click.

**What feature would you add next?**
Authentication tied to the logged-in Databricks user so `created_by`/`author`
are filled automatically, plus full-text search across ticket messages — a
natural lead-in to the Day 2 vector-search work.
