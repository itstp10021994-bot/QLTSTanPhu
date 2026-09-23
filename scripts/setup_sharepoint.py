"""Tạo sẵn các SharePoint List (và cột) mà ứng dụng cần – dùng cho chế độ "app"
(có client_secret, quản trị đã cấp quyền Sites.ReadWrite.All dạng Application).

    python scripts/setup_sharepoint.py [--seed-admin email@truong.edu.vn]

Nếu bạn dùng chế độ đăng nhập bằng tài khoản cá nhân (không có client_secret),
hãy dùng trang "Khởi tạo SharePoint" ngay trong ứng dụng thay cho script này.
"""

import argparse
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qlts import schema  # noqa: E402
from qlts.sp_setup import ensure_lists  # noqa: E402
from qlts.storage import SharePointStore, StorageError  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secrets", default=str(ROOT / ".streamlit" / "secrets.toml"))
    parser.add_argument("--seed-admin", help="Email được cấp vai trò Quản trị hệ thống")
    args = parser.parse_args()

    cfg = tomllib.loads(Path(args.secrets).read_text(encoding="utf-8"))["sharepoint"]
    if not cfg.get("client_secret"):
        sys.exit("Không có client_secret: hãy dùng trang 'Khởi tạo SharePoint' trong ứng dụng.")
    store = SharePointStore(cfg)
    for line in ensure_lists(store):
        print("-", line)

    if args.seed_admin:
        store.create(schema.PHAN_QUYEN, {"Title": args.seed_admin.lower(), "VaiTro": schema.ROLE_ADMIN,
                                         "ChucDanh": "Chuyên viên Quản lý hệ thống"})
        print(f"- Đã cấp quyền quản trị cho {args.seed_admin}")


if __name__ == "__main__":
    try:
        main()
    except StorageError as exc:
        sys.exit(f"Lỗi: {exc}")
