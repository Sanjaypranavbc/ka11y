#!/usr/bin/env python3
"""
Set (or reset) a user's password for the e-mail + password sign-in.

    DATABASE_URL=postgresql://... poetry run python scripts/set_password.py someone@kao.com
    DATABASE_URL=postgresql://... poetry run python scripts/set_password.py someone@kao.com --create

Prompts for the password twice (never takes it on the command line, so it
does not land in shell history). --create makes the account when it does not
exist yet; the address must still pass KA11Y_ALLOWED_EMAILS / _DOMAINS.
Inside the compose stack:

    docker compose exec python python scripts/set_password.py someone@kao.com --create
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("email")
    ap.add_argument("--create", action="store_true", help="create the user if it does not exist")
    args = ap.parse_args()

    from ka11y.auth.service import AuthError, set_password
    from ka11y.db.engine import is_configured

    if not is_configured():
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2

    pw1 = getpass.getpass("New password: ")
    pw2 = getpass.getpass("Repeat password: ")
    if pw1 != pw2:
        print("Passwords do not match.", file=sys.stderr)
        return 2
    try:
        user = asyncio.run(set_password(email=args.email, password=pw1, create=args.create))
    except AuthError as exc:
        print(f"Failed: {exc.code} — {exc}", file=sys.stderr)
        return 1
    print(f"Password set for {user.email} ({user.id}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
