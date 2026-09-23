"""Kiểm tra / tạo các SharePoint List mà ứng dụng cần.

Dùng chung cho ``scripts/setup_sharepoint.py`` và trang "Khởi tạo SharePoint".
Người thực hiện cần quyền Owner (hoặc quyền tạo list) trên site.
"""

from __future__ import annotations

import pandas as pd

from . import schema
from .storage import SharePointStore, StorageError


def column_def(name: str, spec: dict) -> dict:
    kind = spec["type"]
    col = {"name": name, "displayName": spec["label"] if name != "Title" else name}
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


def existing_lists(store: SharePointStore) -> dict[str, str]:
    data = store._request("GET", f"/sites/{store.site_id}/lists?$select=id,displayName&$top=999")
    return {lst["displayName"]: lst["id"] for lst in data["value"]}


def column_report(store: SharePointStore, list_name: str) -> pd.DataFrame:
    """Bảng đối chiếu: cột trong app -> cột tìm thấy trên SharePoint."""
    store._columns.pop(list_name, None)  # dò lại
    found = store.columns(list_name)
    rows = []
    for key, spec in schema.LISTS[list_name]["columns"].items():
        col = found.get(key)
        rows.append({
            "Cột trong app": spec["label"],
            "Tên nội bộ SharePoint": col["name"] if col else "",
            "Kiểu SharePoint": col["kind"] if col else "",
            "Trạng thái": ("⚠️ chỉ đọc" if col["readonly"] else "✅ OK") if col else "❌ không tìm thấy",
        })
    return pd.DataFrame(rows)


def ensure_lists(store: SharePointStore, add_columns_to: set[str] | None = None) -> list[str]:
    """Tạo list còn thiếu. Với list đã có, chỉ thêm cột thiếu nếu list nằm trong ``add_columns_to``."""
    site = store.site_id
    log = []
    existing = existing_lists(store)
    for key, spec in schema.LISTS.items():
        name = store.real_list_name(key)
        cols = [column_def(c, s) for c, s in spec["columns"].items() if c != "Title"]
        if name not in existing:
            created = store._request("POST", f"/sites/{site}/lists", json={
                "displayName": name, "columns": cols, "list": {"template": "genericList"},
            })
            if "Title" in spec["columns"]:
                try:  # đặt tên hiển thị cho cột Title (không bắt buộc)
                    base = f"/sites/{site}/lists/{created['id']}/columns"
                    title_col = next(c for c in store._request("GET", base)["value"] if c["name"] == "Title")
                    store._request("PATCH", f"{base}/{title_col['id']}",
                                   json={"displayName": spec["columns"]["Title"]["label"]})
                except (StorageError, StopIteration, KeyError):
                    pass
            log.append(f"Đã tạo list {name}")
            continue
        store._columns.pop(key, None)
        found = store.columns(key)
        missing = [c for c in cols if c["name"] not in found]
        if missing and add_columns_to and key in add_columns_to:
            for col in missing:
                store._request("POST", f"/sites/{site}/lists/{existing[name]}/columns", json=col)
            store._columns.pop(key, None)
            log.append(f"List {name} đã có, thêm cột: {', '.join(c['displayName'] for c in missing)}")
        elif missing:
            log.append(f"List {name} đã có, còn thiếu cột: {', '.join(c['displayName'] for c in missing)}")
        else:
            log.append(f"List {name} đã có, đủ cột")
    return log


__all__ = ["column_report", "ensure_lists", "StorageError"]
