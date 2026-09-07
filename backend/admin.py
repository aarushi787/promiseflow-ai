"""Local administrator command; never expose user provisioning as an anonymous API."""

import argparse
from getpass import getpass
from .store import Store, password_hash


def main():
    parser = argparse.ArgumentParser(
        description="Create a named PromiseFlow user in the configured database"
    )
    parser.add_argument("username")
    parser.add_argument(
        "--role",
        required=True,
        choices=[
            "admin",
            "manager",
            "planner",
            "sales",
            "supervisor",
            "purchase",
            "maintenance",
            "management",
        ],
    )
    args = parser.parse_args()
    password = getpass("New user password (minimum 16 characters): ")
    if len(password) < 16:
        raise SystemExit("Password must be at least 16 characters")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    store = Store()
    with store.connect() as db:
        if db.execute(
            "SELECT 1 FROM users WHERE username=?", (args.username,)
        ).fetchone():
            raise SystemExit("User already exists; no changes made")
        db.execute(
            "INSERT INTO users VALUES (?,?,?)",
            (args.username, args.role, password_hash(password)),
        )
        store.audit(
            db,
            "local administrator",
            "Provisioned user",
            {"username": args.username, "role": args.role},
        )
    print("User created.")


if __name__ == "__main__":
    main()
