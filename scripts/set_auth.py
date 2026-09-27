#!/usr/bin/env python3
"""Kelola autentikasi Kuntum Insight dari CLI.

Backend memakai token JWT HS256 + password PBKDF2-SHA256; konfigurasi
disimpan di backend_seed/auth.json (GITIGNORED — jangan di-commit).

Fungsi:
  add-user    <username> [--password <p>]   tambah user (default pass = username)
  remove-user <username>                     hapus user
  set-pass    <username> --password <p>      ganti password
  rotate-secret                              rotasi server_secret (cabut semua token)
  list                                       tampilkan user tanpa hash
  ttl <detik>                                ubah session_ttl_seconds

Contoh (sesuai HANDOFF §13 / main.py):
  python scripts/set_auth.py add-user operator --password rahas123
  python scripts/set_auth.py remove-user operator
  python scripts/set_auth.py rotate-secret   # setelah ini semua sesi lama mati
"""
import argparse
import hashlib
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTH_CONFIG_PATH = ROOT / "backend_seed" / "auth.json"
DEFAULT_ITERATIONS = 100_000
DEFAULT_TTL = 86_400


def _pbkdf2_hex(password, salt_hex, iterations):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), iterations
    ).hex()


def load_cfg():
    if not AUTH_CONFIG_PATH.exists():
        raise SystemExit(
            "auth.json belum ada. Jalankan backend dulu sekali (auto-buat admin/admin) "
            "atau buat manual sebelum memakai set_auth.py."
        )
    return json.loads(AUTH_CONFIG_PATH.read_text(encoding="utf-8"))


def save_cfg(cfg):
    AUTH_CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def add_user(cfg, username, password):
    if any(u["username"] == username for u in cfg["users"]):
        raise SystemExit(f"User '{username}' sudah ada.")
    salt = secrets.token_hex(16)
    cfg["users"].append({
        "username": username,
        "salt": salt,
        "password_hash": _pbkdf2_hex(password, salt, cfg["iterations"]),
    })


def remove_user(cfg, username):
    before = len(cfg["users"])
    cfg["users"] = [u for u in cfg["users"] if u["username"] != username]
    if len(cfg["users"]) == before:
        raise SystemExit(f"User '{username}' tidak ditemukan.")
    if not cfg["users"]:
        raise SystemExit("Dilarang menghapus user terakhir: akun kosong = lockout total.")


def set_pass(cfg, username, password):
    for u in cfg["users"]:
        if u["username"] == username:
            u["salt"] = secrets.token_hex(16)
            u["password_hash"] = _pbkdf2_hex(password, u["salt"], cfg["iterations"])
            return
    raise SystemExit(f"User '{username}' tidak ditemukan.")


def rotate_secret(cfg):
    cfg["server_secret"] = secrets.token_hex(32)


def main():
    p = argparse.ArgumentParser(description="Kelola auth.json Kuntum Insight")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, **kw):
        return sub.add_parser(name, **kw)

    sp = add("add-user")
    sp.add_argument("username")
    sp.add_argument("--password", default=None)
    sp = add("remove-user")
    sp.add_argument("username")
    sp = add("set-pass")
    sp.add_argument("username")
    sp.add_argument("--password", required=True)
    sub.add_parser("rotate-secret")
    add("ttl").add_argument("detik", type=int)
    sub.add_parser("list")

    args = p.parse_args()
    cfg = load_cfg()

    if args.cmd == "add-user":
        pw = args.password if args.password is not None else args.username
        add_user(cfg, args.username, pw)
        save_cfg(cfg)
        print(f"OK: user '{args.username}' ditambahkan.")
    elif args.cmd == "remove-user":
        remove_user(cfg, args.username)
        save_cfg(cfg)
        print(f"OK: user '{args.username}' dihapus.")
    elif args.cmd == "set-pass":
        set_pass(cfg, args.username, args.password)
        save_cfg(cfg)
        print(f"OK: password '{args.username}' diganti.")
    elif args.cmd == "rotate-secret":
        rotate_secret(cfg)
        save_cfg(cfg)
        print("OK: server_secret dirotasi. Semua token lama kini TIDAK BERLAKU.")
    elif args.cmd == "ttl":
        if args.detik <= 0:
            raise SystemExit("TTL harus > 0 detik.")
        cfg["session_ttl_seconds"] = args.detik
        save_cfg(cfg)
        print(f"OK: session_ttl_seconds = {args.detik} detik.")
    elif args.cmd == "list":
        for u in cfg["users"]:
            print(f"  - {u['username']}  (salt={u['salt'][:8]}…)")


if __name__ == "__main__":
    main()
