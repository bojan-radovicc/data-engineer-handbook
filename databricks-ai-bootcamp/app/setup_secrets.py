"""One-time setup: store the Lakebase connection URL in a Databricks secret.

Run this locally with the Databricks CLI configured (or from a notebook).
Never commit the secret value anywhere.

Usage:
    python setup_secrets.py

The value you paste should be a full Postgres connection URL, e.g.:
    postgresql://<user>:<password>@<host>:5432/databricks_postgres?sslmode=require

The app reads it via the LAKEBASE_URL environment variable, which you wire up
by attaching this secret as an app resource (see app.yaml / README).
"""

import getpass

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace

SCOPE = "database"
KEY = "lakebase-url"

w = WorkspaceClient()

# create_scope fails if the scope already exists; ignore that case.
try:
    w.secrets.create_scope(scope=SCOPE)
    print(f"Created secret scope '{SCOPE}'.")
except Exception as exc:  # already-exists or insufficient perms
    print(f"Scope '{SCOPE}' not created ({exc}); continuing.")

w.secrets.put_secret(
    scope=SCOPE,
    key=KEY,
    string_value=getpass.getpass("Paste your Lakebase connection URL: "),
)
print(f"Stored secret {SCOPE}/{KEY}.")

# Let the workspace users read it. If your app runs as a service principal that
# is not in the 'users' group, also grant that principal explicitly (replace
# the principal below with the app's application/client id).
w.secrets.put_acl(
    scope=SCOPE,
    principal="users",
    permission=workspace.AclPermission.READ,
)
print("Granted READ on the scope to 'users'.")
