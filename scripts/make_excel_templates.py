"""Ghi các file Excel biểu mẫu vào thư mục templates/ (dùng "Microsoft Lists → Từ Excel").

    python scripts/make_excel_templates.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qlts.excel_io import FILES, template_workbook  # noqa: E402

OUT = ROOT / "templates"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for key, (filename, list_name) in FILES.items():
        (OUT / filename).write_bytes(template_workbook(key, list_name))
        print("Đã tạo", OUT / filename)


if __name__ == "__main__":
    main()
