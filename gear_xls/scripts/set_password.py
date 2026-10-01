import json
import os
import sys

import bcrypt


def main():
    args = sys.argv[1:]
    if len(args) != 2:
        print("Usage: python gear_xls/scripts/set_password.py <login> <password>")
        return 1

    login, password = args
    config_path = os.path.abspath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "config", "users.json"
        )
    )

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for user in data.get("users", []):
        if user.get("login") == login:
            user["password_hash"] = bcrypt.hashpw(
                password.encode(), bcrypt.gensalt(rounds=12)
            ).decode()
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            print(f"Password updated for {login}")
            return 0

    print(f"User not found: {login}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
