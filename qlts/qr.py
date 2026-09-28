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
      <button class="qs-start" style="padding:9px 16px;border-radius:10px;border:0;background:#1d4ed8;color:#fff;font-weight:600;cursor:pointer">📷 Bật camera quét QR</button>
      <button class="qs-stop" style="display:none;padding:8px 14px;border-radius:10px;border:1px solid #cbd5e1;background:#fff;cursor:pointer">Tắt camera</button>
      <button class="qs-torch" style="display:none;padding:8px 14px;border-radius:10px;border:1px solid #cbd5e1;background:#fff;cursor:pointer">🔦 Đèn</button>
      <label class="qs-zoomwrap" style="display:none;align-items:center;gap:6px;font-size:13px">🔍 Zoom <input class="qs-zoom" type="range" style="width:120px"></label>
      <span class="qs-msg" style="font-size:14px;color:#475569"></span>
    </div>
    <div class="qs-box" style="display:none;position:relative;width:100%;max-width:460px">
      <video class="qs-video" playsinline muted style="width:100%;border-radius:12px;border:3px solid #1d4ed8;display:block"></video>
      <div style="position:absolute;left:20%;top:20%;width:60%;height:60%;border:3px dashed rgba(255,255,255,.85);border-radius:12px;box-shadow:0 0 0 2000px rgba(0,0,0,.18);pointer-events:none"></div>
    </div>`;
  parentElement.appendChild(root);
  const $ = (s) => root.querySelector(s);
  const video = $(".qs-video"), box = $(".qs-box"), msg = $(".qs-msg");
  const startBtn = $(".qs-start"), stopBtn = $(".qs-stop"), torchBtn = $(".qs-torch");
  const zoomWrap = $(".qs-zoomwrap"), zoom = $(".qs-zoom");
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  let stream = null, track = null, timer = null, last = "", lastAt = 0, torchOn = false, detector = null, turn = 0;

  function loadLib() {
    if (!window.jsQR) {  // thư viện jsQR đóng gói kèm app (không cần CDN)
      const s = document.createElement("script");
      s.textContent = JSQR_SOURCE;
      document.head.appendChild(s);
    }
  }
  async function makeDetector() {
    // Bộ đọc mã có sẵn của trình duyệt (Android Chrome, một số máy iOS/macOS) – nhanh và nhạy hơn nhiều
    try {
      if ("BarcodeDetector" in window) {
        const formats = await window.BarcodeDetector.getSupportedFormats();
        if (formats.includes("qr_code")) return new window.BarcodeDetector({ formats: ["qr_code"] });
      }
    } catch (e) {}
    return null;
  }
  function found(text) {
    const now = Date.now();
    if (!text || (text === last && now - lastAt < 2500)) return;
    last = text; lastAt = now;
    setTriggerValue("code", text + "\u0001" + now);
    msg.textContent = "✔ " + text.slice(0, 40);
    video.style.borderColor = "#16a34a";
    setTimeout(() => { video.style.borderColor = "#1d4ed8"; }, 500);
    if (navigator.vibrate) navigator.vibrate(80);
  }
  function jsqrRegion(sx, sy, sw, sh, maxSide) {
    const scale = Math.min(1, maxSide / Math.max(sw, sh));
    canvas.width = Math.max(1, Math.round(sw * scale));
    canvas.height = Math.max(1, Math.round(sh * scale));
    ctx.drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const r = window.jsQR(img.data, img.width, img.height, { inversionAttempts: "attemptBoth" });
    return r && r.data;
  }
  async function scan() {
    if (!stream) return;
    const w = video.videoWidth, h = video.videoHeight;
    if (w && h) {
      try {
        if (detector) {
          const codes = await detector.detect(video);
          if (codes.length) found(codes[0].rawValue);
        } else if (window.jsQR) {
          // Luân phiên: vùng giữa ở độ phân giải gốc (tem nhỏ/xa) và cả khung hình thu nhỏ (tem to/lệch)
          turn = (turn + 1) % 3;
          let text = null;
          if (turn < 2) {
            const side = Math.min(w, h) * (turn === 0 ? 0.6 : 0.85);
            text = jsqrRegion((w - side) / 2, (h - side) / 2, side, side, 900);
          } else {
            text = jsqrRegion(0, 0, w, h, 1000);
          }
          if (text) found(text);
        }
      } catch (e) {}
    }
    timer = setTimeout(scan, detector ? 120 : 60);
  }
  async function start() {
    msg.textContent = "Đang mở camera...";
    try {
      loadLib();
      detector = await makeDetector();
      stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: {
        facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 },
        advanced: [{ focusMode: "continuous" }] } });
      track = stream.getVideoTracks()[0];
      video.srcObject = stream;
      await video.play();
      box.style.display = "block"; startBtn.style.display = "none"; stopBtn.style.display = "inline-block";
      const caps = track.getCapabilities ? track.getCapabilities() : {};
      if (caps.focusMode && caps.focusMode.includes("continuous")) {
        track.applyConstraints({ advanced: [{ focusMode: "continuous" }] }).catch(() => {});
      }
      if (caps.torch) torchBtn.style.display = "inline-block";
      if (caps.zoom) {
        zoom.min = caps.zoom.min; zoom.max = caps.zoom.max; zoom.step = caps.zoom.step || 0.1;
        zoom.value = Math.min(caps.zoom.max, Math.max(caps.zoom.min, 1.5));
        track.applyConstraints({ advanced: [{ zoom: Number(zoom.value) }] }).catch(() => {});
        zoomWrap.style.display = "inline-flex";
      }
      msg.textContent = (detector ? "Bộ đọc nhanh · " : "") + "Đưa tem QR vào khung giữa";
      scan();
    } catch (e) {
      msg.textContent = "Không mở được camera: " + e.message + " (cho phép quyền camera, hoặc nhập mã ở ô bên dưới)";
      stop();
    }
  }
  function stop() {
    if (timer) clearTimeout(timer);
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null; track = null; timer = null; torchOn = false;
    box.style.display = "none"; startBtn.style.display = "inline-block";
    stopBtn.style.display = "none"; torchBtn.style.display = "none"; zoomWrap.style.display = "none";
  }
  startBtn.onclick = start;
  stopBtn.onclick = () => { stop(); msg.textContent = ""; };
  torchBtn.onclick = () => {
    if (!track) return;
    torchOn = !torchOn;
    track.applyConstraints({ advanced: [{ torch: torchOn }] }).catch(() => {});
  };
  zoom.oninput = () => { if (track) track.applyConstraints({ advanced: [{ zoom: Number(zoom.value) }] }).catch(() => {}); };
  video.onclick = () => {  // chạm vào khung hình để lấy nét lại
    if (track) track.applyConstraints({ advanced: [{ focusMode: "single-shot" }] })
      .then(() => track.applyConstraints({ advanced: [{ focusMode: "continuous" }] })).catch(() => {});
  };
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
