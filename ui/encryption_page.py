# ui/encryption_page.py
from __future__ import annotations
import json
import streamlit as st
import streamlit.components.v1 as components

from core.encryption_utils import (
    build_charsets,
    generate_one,
    entropy_bits,
    strength_label,
)

def render():
    st.subheader("🔐 Encryption — Password Generator")

    colL, colR = st.columns([3, 2])
    with colL:
        length = st.slider("Password length", 8, 128, 16, 1)
        count  = st.number_input("Quantity", min_value=1, max_value=50, value=5, step=1)
        show_plain = st.checkbox("Show characters (unmasked)", value=False)
    with colR:
        st.markdown("**Character sets**")
        use_lower  = st.checkbox("a–z", value=True)
        use_upper  = st.checkbox("A–Z", value=True)
        use_digits = st.checkbox("0–9", value=True)
        use_symbols = st.checkbox("Symbols", value=False)

        st.markdown("**Filters**")
        exclude_similar   = st.checkbox("Exclude look-alike (I l 1 O 0 …)", value=True)
        exclude_ambiguous = st.checkbox("Exclude ambiguous symbols ({ } [ ] …)", value=False)

    gen = st.button("🎲 Generate", type="primary", use_container_width=True)

    if gen:
        try:
            groups, combined = build_charsets(
                use_lower, use_upper, use_digits, use_symbols,
                exclude_similar, exclude_ambiguous
            )
            if not combined:
                st.error("Select at least one character set.")
                return
            if length < len(groups):
                st.error(f"Length ({length}) is too short for {len(groups)} required groups.")
                return

            bits = entropy_bits(length, len(combined))
            st.caption(
                f"Estimated entropy: **{bits:.1f} bits** — {strength_label(bits)} "
                f"(alphabet ~{len(combined)} chars)"
            )

            passwords = [generate_one(int(length), groups, combined) for _ in range(int(count))]

            # Dữ liệu cho iframe
            pw_data = [{"plain": p, "masked": ("•" * len(p))} for p in passwords]
            frame_height = min(720, 160 + 36 * len(pw_data))

            components.html(
                f"""
<style>
  :root {{ color-scheme: light dark; }}
  /* Mặc định (light) */
  .pw-shown {{
    color: #111827; /* gray-900 */
  }}
  /* Chỉ khi dark + đang hiển thị plain (không áp cho chế độ masked) */
  @media (prefers-color-scheme: dark) {{
    .pw-shown.pw-plain {{
      color: #ef4444; /* red-500 */
    }}
  }}
  /* Bảng */
  table#pwtable {{ border-collapse: collapse; width: 100%; border: 1px solid #e5e7eb; }}
  thead tr {{ background: #f8fafc; }}
  td, th {{ padding: 6px 10px; }}
  @media (prefers-color-scheme: dark) {{
    table#pwtable {{ border-color: #374151; }}
    thead tr {{ background: #111827; color: #e5e7eb; }}
  }}
  /* Nút copy */
  button.cpy {{
    background:#2563eb; border:none; color:#fff; padding:6px 10px; border-radius:6px; cursor:pointer;
  }}
  /* Nút toggle */
  #toggle {{
    padding:6px 10px; border:1px solid #d1d5db; border-radius:8px; cursor:pointer; background:#fff;
  }}
  @media (prefers-color-scheme: dark) {{
    #toggle {{ background:#0b0f19; border-color:#374151; color:#e5e7eb; }}
  }}
</style>

<div style="font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;">
  <div style="display:flex;gap:8px;align-items:center;margin:6px 0 10px;">
    <button id="toggle">{("🙈 Hide" if show_plain else "👁 Show")}</button>
    <span id="hint" style="color:#6b7280;">Click để show/hide mật khẩu. (Dark theme: chữ sẽ chuyển đỏ khi hiển thị)</span>
  </div>

  <table id="pwtable">
    <thead>
      <tr>
        <th style="text-align:left;width:60px;">#</th>
        <th style="text-align:left;">Password</th>
        <th style="text-align:right;width:110px;"></th>
      </tr>
    </thead>
    <tbody id="pwbody"></tbody>
  </table>
</div>

<script>
const data = {json.dumps(pw_data)};
let showPlain = {str(bool(show_plain)).lower()};

const tbody = document.getElementById("pwbody");
const toggleBtn = document.getElementById("toggle");

function makeRow(idx, item) {{
  const tr = document.createElement("tr");

  const tdIdx = document.createElement("td");
  tdIdx.style.whiteSpace = "nowrap";
  tdIdx.textContent = String(idx + 1);

  const tdPwd = document.createElement("td");
  tdPwd.style.fontFamily = "ui-monospace,Consolas,Monaco,monospace";

  const spanShown = document.createElement("span");
  spanShown.className = "pw-shown" + (showPlain ? " pw-plain" : "");
  spanShown.textContent = showPlain ? item.plain : item.masked;

  // giữ plain trong DOM nhưng ẩn
  const spanPlain = document.createElement("span");
  spanPlain.className = "pw-plain-hidden";
  spanPlain.style.display = "none";
  spanPlain.textContent = item.plain;

  tdPwd.appendChild(spanShown);
  tdPwd.appendChild(spanPlain);

  const tdBtn = document.createElement("td");
  tdBtn.style.textAlign = "right";

  const btn = document.createElement("button");
  btn.className = "cpy";
  btn.textContent = "Copy";
  // gắn plain vào dataset để tránh lỗi escape
  btn.dataset.pw = item.plain;

  tdBtn.appendChild(btn);

  tr.appendChild(tdIdx);
  tr.appendChild(tdPwd);
  tr.appendChild(tdBtn);
  return tr;
}}

function renderRows() {{
  tbody.innerHTML = "";
  data.forEach((it, i) => tbody.appendChild(makeRow(i, it)));
  toggleBtn.textContent = showPlain ? "🙈 Hide" : "👁 Show";
}}
renderRows();

// Copy với fallback
function copyText(text) {{
  if (navigator.clipboard && window.isSecureContext) {{
    return navigator.clipboard.writeText(text);
  }} else {{
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {{ document.execCommand('copy'); }}
    finally {{ document.body.removeChild(ta); }}
    return Promise.resolve();
  }}
}}

document.getElementById("pwtable").addEventListener("click", (e) => {{
  const btn = e.target.closest("button.cpy");
  if (!btn) return;
  const pw = btn.dataset.pw || "";
  copyText(pw).then(() => {{
    const old = btn.textContent;
    btn.textContent = "Copied";
    setTimeout(() => btn.textContent = old, 900);
  }}).catch(() => {{
    alert("Clipboard blocked by browser");
  }});
}});

// Toggle show/hide + set class để dark mode tô đỏ chỉ khi đang hiển thị plain
toggleBtn.addEventListener("click", () => {{
  showPlain = !showPlain;
  [...tbody.querySelectorAll("tr")].forEach((tr) => {{
    const shown = tr.querySelector(".pw-shown");
    const hidden = tr.querySelector(".pw-plain-hidden").textContent;
    shown.textContent = showPlain ? hidden : "•".repeat(hidden.length);
    shown.classList.toggle("pw-plain", showPlain);
  }});
  toggleBtn.textContent = showPlain ? "🙈 Hide" : "👁 Show";
}});
</script>
                """,
                height=frame_height,
            )

        except Exception as e:
            st.error(f"Generation error: {e}")
