"""Create the schema and seed sample data in Lakebase.

Run once after configuring your database environment variables:

"""

import pathlib

import lakebase

SQL_DIR = pathlib.Path(__file__).parent / "sql"


def run_file(path: pathlib.Path) -> None:
    text = path.read_text()
    # Split on statement boundaries. Our SQL contains no semicolons inside
    # string literals, so a simple split is sufficient here.
    statements = [s.strip() for s in text.split(";") if s.strip()]
    conn = lakebase.get_connection()
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    print(f"  applied {len(statements)} statement(s) from {path.name}")


def main() -> None:
    for name in ("01_schema.sql", "02_seed.sql"):
        print(f"Applying {name} ...")
        run_file(SQL_DIR / name)
    print("Done. Schema created and sample data seeded.")


if __name__ == "__main__":
    main()
