"""Tạo các SharePoint List (và cột còn thiếu) mà ứng dụng cần.

Dùng chung cho ``scripts/setup_sharepoint.py`` và trang "Khởi tạo SharePoint".
Người thực hiện cần quyền Owner (hoặc Edit với quyền tạo list) trên site.
"""

from __future__ import annotations

from . import schema
from .storage import SharePointStore


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


def ensure_lists(store: SharePointStore) -> list[str]:
    """Tạo list/cột còn thiếu; trả về nhật ký các việc đã làm."""
    site = store.site_id
    log = []
    existing = {
        lst["displayName"]: lst["id"]
        for lst in store._request("GET", f"/sites/{site}/lists?$select=id,displayName&$top=999")["value"]
    }
    for key, spec in schema.LISTS.items():
        name = store.list_names.get(key, key)
        mapping = store.column_map.get(key, {})
        cols = [column_def(mapping.get(c, c), s) for c, s in spec["columns"].items()]
        if name not in existing:
            store._request("POST", f"/sites/{site}/lists", json={
                "displayName": name, "columns": cols, "list": {"template": "genericList"},
            })
            log.append(f"Đã tạo list {name}")
            continue
        have = {c["name"] for c in store._request("GET", f"/sites/{site}/lists/{existing[name]}/columns")["value"]}
        added = []
        for col in cols:
            if col["name"] not in have:
                store._request("POST", f"/sites/{site}/lists/{existing[name]}/columns", json=col)
                added.append(col["name"])
        log.append(f"List {name} đã có" + (f", thêm cột: {', '.join(added)}" if added else ", đủ cột"))
    return log
