"""Tạo sẵn các SharePoint List (và cột) mà ứng dụng cần.

Chạy một lần sau khi đã điền mục [sharepoint] trong .streamlit/secrets.toml:

    python scripts/setup_sharepoint.py

List đã tồn tại sẽ được bỏ qua; cột còn thiếu sẽ được bổ sung.
Có thể thêm --seed-admin email@truong.edu.vn để tạo sẵn tài khoản quản trị.
"""

import argparse
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qlts import schema  # noqa: E402
from qlts.storage import SharePointStore, StorageError  # noqa: E402


def column_def(name: str, spec: dict) -> dict:
    kind = spec["type"]
    col = {"name": name, "displayName": name}
    if kind == "text":
        col["text"] = {}
    elif kind == "note":
        col["text"] = {"allowMultipleLines": True}
    elif kind == "number":
        col["number"] = {}
    elif kind == "date":
        col["dateTime"] = {"format": "dateOnly"}
    elif kind == "choice":
        col["choice"] = {"choices": spec["choices"], "allowTextEntry": True}
    return col


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secrets", default=str(ROOT / ".streamlit" / "secrets.toml"))
    parser.add_argument("--seed-admin", help="Email được cấp vai trò Quản trị hệ thống")
    args = parser.parse_args()

    cfg = tomllib.loads(Path(args.secrets).read_text(encoding="utf-8"))["sharepoint"]
    store = SharePointStore(cfg)
    site = store.site_id
    print(f"Site: {site}")

    existing = {lst["displayName"]: lst["id"] for lst in store._request("GET", f"/sites/{site}/lists?$top=999")["value"]}
    for key, spec in schema.LISTS.items():
        name = store.list_names.get(key, key)
        cols = [column_def(c, s) for c, s in spec["columns"].items()]
        if name not in existing:
            store._request("POST", f"/sites/{site}/lists", json={
                "displayName": name, "columns": cols, "list": {"template": "genericList"},
            })
            print(f"[+] Đã tạo list {name}")
            continue
        have = {c["name"] for c in store._request("GET", f"/sites/{site}/lists/{existing[name]}/columns")["value"]}
        for col in cols:
            if col["name"] not in have:
                store._request("POST", f"/sites/{site}/lists/{existing[name]}/columns", json=col)
                print(f"[+] {name}: thêm cột {col['name']}")
        print(f"[=] List {name} đã tồn tại")

    if args.seed_admin:
        store.create(schema.PHAN_QUYEN, {"Title": args.seed_admin.lower(), "VaiTro": schema.ROLE_ADMIN,
                                         "ChucDanh": "Chuyên viên Quản lý hệ thống"})
        print(f"[+] Đã cấp quyền quản trị cho {args.seed_admin}")


if __name__ == "__main__":
    try:
        main()
    except StorageError as exc:
        sys.exit(f"Lỗi: {exc}")
