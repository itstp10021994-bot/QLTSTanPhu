"""Kiểm kê bằng mã QR: máy quét camera (trình duyệt) và in tem QR cho thiết bị.

Nội dung mã QR = Mã chi tiết (vd ``111028-00001``). Tem cũ có nội dung khác (URL, nhiều dòng...) vẫn đọc được
nếu trong đó có Mã chi tiết.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from .bienban import FONTS

CODE_RE = re.compile(r"\d{6}-\d{2,6}")

_SCANNER_JS = """
export default function({ parentElement, setTriggerValue }) {
  const root = document.createElement("div");
  root.innerHTML = `
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
      <button class="qs-start" style="padding:8px 14px;border-radius:8px;border:1px solid #2a78d6;background:#2a78d6;color:#fff;cursor:pointer">📷 Bật camera quét QR</button>
      <button class="qs-stop" style="display:none;padding:8px 14px;border-radius:8px;border:1px solid #999;background:#fff;cursor:pointer">Tắt camera</button>
      <span class="qs-msg" style="font-size:14px;color:#52514e"></span>
    </div>
    <video class="qs-video" playsinline muted style="display:none;width:100%;max-width:420px;border-radius:10px;border:3px solid #2a78d6"></video>`;
  parentElement.appendChild(root);
  const $ = (s) => root.querySelector(s);
  const video = $(".qs-video"), msg = $(".qs-msg"), startBtn = $(".qs-start"), stopBtn = $(".qs-stop");
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  let stream = null, raf = null, last = "", lastAt = 0;

  function loadLib() {
    if (!window.jsQR) {  // thư viện jsQR đóng gói kèm app (không cần CDN)
      const s = document.createElement("script");
      s.textContent = JSQR_SOURCE;
      document.head.appendChild(s);
    }
    return window.jsQR ? Promise.resolve() : Promise.reject(new Error("không nạp được thư viện đọc QR"));
  }
  function tick() {
    if (!stream) return;
    if (video.readyState >= 2 && video.videoWidth) {
      const scale = Math.min(1, 720 / video.videoWidth);
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const found = window.jsQR(img.data, img.width, img.height, { inversionAttempts: "attemptBoth" });
      if (found && found.data) {
        const now = Date.now();
        if (found.data !== last || now - lastAt > 3000) {
          last = found.data; lastAt = now;
          setTriggerValue("code", found.data + "\\u0001" + now);
          msg.textContent = "✔ " + found.data.slice(0, 40);
          video.style.borderColor = "#1baf7a";
          setTimeout(() => { video.style.borderColor = "#2a78d6"; }, 600);
          if (navigator.vibrate) navigator.vibrate(80);
        }
      }
    }
    raf = requestAnimationFrame(tick);
  }
  async function start() {
    msg.textContent = "Đang mở camera...";
    try {
      await loadLib();
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      video.srcObject = stream;
      await video.play();
      video.style.display = "block"; startBtn.style.display = "none"; stopBtn.style.display = "inline-block";
      msg.textContent = "Đưa mã QR vào khung hình";
      tick();
    } catch (e) {
      msg.textContent = "Không mở được camera: " + e.message + " (cho phép quyền camera, hoặc nhập mã ở ô bên dưới)";
      stop();
    }
  }
  function stop() {
    if (raf) cancelAnimationFrame(raf);
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null; raf = null;
    video.style.display = "none"; startBtn.style.display = "inline-block"; stopBtn.style.display = "none";
  }
  startBtn.onclick = start;
  stopBtn.onclick = () => { stop(); msg.textContent = ""; };
  return () => stop();
}
"""
_JSQR = (Path(__file__).parent / "static" / "jsQR.js").read_text(encoding="utf-8")
_scanner = st.components.v2.component(
    "qlts_qr_scanner", js=f"const JSQR_SOURCE = {json.dumps(_JSQR)};\n" + _SCANNER_JS, isolate_styles=False)


def scanner(key: str) -> str | None:
    """Máy quét QR bằng camera; trả về nội dung mã vừa quét (chỉ ở lần chạy ngay sau khi quét)."""
    res = _scanner(key=key, on_code_change=lambda: None)
    raw = getattr(res, "code", None)
    return raw.split("\u0001", 1)[0] if raw else None


def resolve(text: str, codes: dict[str, str]) -> str | None:
    """Nội dung quét được -> Mã chi tiết có trong hệ thống (``codes``: chữ thường -> mã gốc)."""
    text = (text or "").strip()
    if not text:
        return None
    if text.lower() in codes:
        return codes[text.lower()]
    for m in CODE_RE.findall(text):
        if m.lower() in codes:
            return codes[m.lower()]
    return None


# ---------------------------------------------------------------------------
# In tem QR (PDF A4, 3 cột x 8 hàng)
# ---------------------------------------------------------------------------
def labels_pdf(items: pd.DataFrame, room_label: str = "") -> bytes:
    import qrcode
    from fpdf import FPDF

    pdf = FPDF(format="A4", unit="mm")
    pdf.add_font("TNR", "", str(FONTS / "LiberationSerif-Regular.ttf"))
    pdf.add_font("TNR", "B", str(FONTS / "LiberationSerif-Bold.ttf"))
    pdf.set_auto_page_break(False)
    cols, rows, mx, my = 3, 8, 8, 10
    w, h = (210 - 2 * mx) / cols, (297 - 2 * my) / rows
    for n, r in enumerate(items.itertuples()):
        if n % (cols * rows) == 0:
            pdf.add_page()
        i = n % (cols * rows)
        x, y = mx + (i % cols) * w, my + (i // cols) * h
        pdf.set_draw_color(180, 180, 180)
        pdf.rect(x + 1, y + 1, w - 2, h - 2)
        img = qrcode.make(r.MaChiTiet, box_size=6, border=1)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        q = h - 6
        pdf.image(buf, x=x + 3, y=y + 3, w=q, h=q)
        tx = x + q + 5
        tw = w - q - 7
        pdf.set_xy(tx, y + 4)
        pdf.set_font("TNR", "B", 10)
        pdf.multi_cell(tw, 4.5, r.MaChiTiet)
        pdf.set_x(tx)
        pdf.set_font("TNR", "", 8.5)
        name = (r.TenThietBi or r.ChiTiet or "")[:60]
        pdf.multi_cell(tw, 3.8, name, align="L")
        pdf.set_x(tx)
        pdf.multi_cell(tw, 3.8, (room_label or r.NoiSuDung)[:40], align="L")
    return bytes(pdf.output())
