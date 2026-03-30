"""
export_to_gslides.py
====================
Exports Dashboard, Portfolio Analytics, Security Analytics, and Attribution
to a new Google Slides presentation.

What gets created (one section per slide group)
-----------------------------------------------
  Cover          — title + as-of date
  Dashboard      — KPI summary table, sector donut, YTD bar, health radar
  Portfolio      — portfolio summary table, EVE stress table, income projection
  Securities     — universe summary, top-10 holdings with rate-shock sensitivity
  Attribution    — OAS / OAD / Yield / EVE waterfall charts + driver tables

Setup (one-time)
----------------
  1. Go to https://console.cloud.google.com/ → enable Slides API + Drive API.
  2. Create OAuth 2.0 credentials (Desktop app) → download as credentials.json.
  3. Place credentials.json in the project root, OR pass --credentials.
  4. Install extra dependencies:
       pip install google-api-python-client google-auth-httplib2
                   google-auth-oauthlib kaleido

Usage
-----
  python scripts/export_to_gslides.py
  python scripts/export_to_gslides.py --title "Q1 2026 Portfolio Report"
  python scripts/export_to_gslides.py --credentials path/to/credentials.json
  python scripts/export_to_gslides.py --pool CC30_POOL_042  # specific pool in Security section
  python scripts/export_to_gslides.py --no-cleanup           # keep temp Drive images after run
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

# ── Project root on sys.path ──────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))


# ═════════════════════════════════════════════════════════════════════════════
# 1.  Google API auth
# ═════════════════════════════════════════════════════════════════════════════

_SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive.file",
]
_TOKEN_FILE = _ROOT / "data" / "gslides_token.json"


def _get_credentials(credentials_path: str) -> Any:
    """Return valid Google OAuth2 credentials, refreshing / prompting as needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(credentials_path).exists():
                raise FileNotFoundError(
                    f"credentials.json not found at: {credentials_path}\n"
                    "Download it from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, _SCOPES)
            creds = flow.run_local_server(port=0)
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(creds.to_json())

    return creds


def _build_services(credentials_path: str):
    creds = _get_credentials(credentials_path)
    from googleapiclient.discovery import build
    slides_svc = build("slides", "v1", credentials=creds)
    drive_svc  = build("drive",  "v3", credentials=creds)
    return slides_svc, drive_svc


# ═════════════════════════════════════════════════════════════════════════════
# 2.  Data fetching  (uses the project's own tool layer)
# ═════════════════════════════════════════════════════════════════════════════

def _tool(name: str, args: dict = None) -> dict:
    """Call a registered tool and parse the JSON result."""
    from tool.registry import handle_tool_call
    raw = handle_tool_call(name, args or {})
    return json.loads(raw) if isinstance(raw, str) else raw


def _fetch_all_data(pool_id: str | None) -> dict:
    """Fetch every piece of data needed for the presentation."""
    print("  Fetching portfolio summary …")
    summary    = _tool("get_portfolio_summary")

    print("  Fetching portfolio positions …")
    positions  = _tool("get_portfolio_positions")

    print("  Fetching EVE profile …")
    eve        = _tool("compute_eve_profile")

    print("  Fetching attribution …")
    attr_oas   = _tool("get_attribution", {"metric": "oas"})
    attr_oad   = _tool("get_attribution", {"metric": "oad"})
    attr_yield = _tool("get_attribution", {"metric": "yield"})
    attr_eve   = _tool("get_attribution", {"metric": "eve"})

    print("  Fetching sector allocation …")
    sectors    = _tool("get_sector_allocation")

    print("  Fetching top performers …")
    performers = _tool("get_top_performers")

    print("  Fetching portfolio health …")
    health     = _tool("get_portfolio_health")

    print("  Fetching market data …")
    mkt        = _tool("get_market_data")

    print("  Fetching universe summary …")
    universe   = _tool("get_universe_summary")

    # Security: use provided pool or pick first position
    sec_pool = pool_id
    if not sec_pool:
        pos_list = positions.get("positions", [])
        sec_pool = pos_list[0]["pool_id"] if pos_list else None

    pool_details = None
    shock_table  = None
    if sec_pool:
        print(f"  Fetching pool details for {sec_pool} …")
        pool_details = _tool("get_pool_details", {"pool_id": sec_pool})
        print(f"  Running rate shocks for {sec_pool} …")
        shock_table  = _tool("run_scenario_analysis", {"pool_ids": [sec_pool]})

    return {
        "summary":    summary,
        "positions":  positions,
        "eve":        eve,
        "attr_oas":   attr_oas,
        "attr_oad":   attr_oad,
        "attr_yield": attr_yield,
        "attr_eve":   attr_eve,
        "sectors":    sectors,
        "performers": performers,
        "health":     health,
        "mkt":        mkt,
        "universe":   universe,
        "sec_pool":   sec_pool,
        "pool_details": pool_details,
        "shock_table":  shock_table,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 3.  Chart builders  (return PNG bytes)
# ═════════════════════════════════════════════════════════════════════════════

_CHART_W, _CHART_H = 900, 500   # px for exported PNGs

def _to_png(fig) -> bytes:
    import plotly.io as pio
    return pio.to_image(fig, format="png", width=_CHART_W, height=_CHART_H, scale=1.5)


def _chart_sector_donut(sectors_data: dict) -> bytes:
    import plotly.graph_objects as go
    items   = sectors_data.get("sectors", [])
    labels  = [s["label"] for s in items]
    values  = [s["mv"] for s in items]
    colors  = ["#3B6FD4", "#059669", "#D97706", "#a371f7",
               "#e11d48", "#0ea5e9", "#84cc16", "#f97316"]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.45,
        marker_colors=colors[:len(labels)],
        textinfo="label+percent", hovertemplate="%{label}: $%{value:.1f}M<extra></extra>",
    ))
    fig.update_layout(
        title="Sector Allocation by Market Value",
        paper_bgcolor="#0d1117", font_color="#e6edf3",
        showlegend=True, legend=dict(font_color="#e6edf3"),
        margin=dict(t=60, b=20, l=20, r=20),
    )
    return _to_png(fig)


def _chart_ytd_bar(performers_data: dict) -> bytes:
    import plotly.graph_objects as go
    top    = performers_data.get("top", [])
    bottom = performers_data.get("bottom", [])
    items  = top + bottom
    ids    = [p["pool_id"] for p in items]
    rets   = [p.get("ret_pct", 0) for p in items]
    colors = ["#22c55e" if r >= 0 else "#ef4444" for r in rets]
    fig = go.Figure(go.Bar(
        y=ids, x=rets, orientation="h",
        marker_color=colors, text=[f"{r:+.2f}%" for r in rets],
        textposition="outside",
    ))
    fig.update_layout(
        title="YTD Return — Top & Bottom Performers",
        xaxis_title="YTD Return (%)", yaxis_title="",
        paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
        font_color="#e6edf3",
        margin=dict(t=60, b=40, l=120, r=60),
    )
    fig.update_xaxes(gridcolor="#30363d", zerolinecolor="#58a6ff")
    return _to_png(fig)


def _chart_health_radar(health_data: dict) -> bytes:
    import plotly.graph_objects as go
    dims = health_data.get("sub_metrics", {})
    cats = list(dims.keys())
    vals = [dims[c]["score"] for c in cats]
    cats_closed = cats + [cats[0]]
    vals_closed  = vals  + [vals[0]]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals_closed, theta=cats_closed, fill="toself",
        fillcolor="rgba(59,111,212,0.3)", line_color="#3B6FD4",
        name="Portfolio",
    ))
    fig.add_trace(go.Scatterpolar(
        r=[5] * len(cats_closed), theta=cats_closed,
        line=dict(color="#58a6ff", dash="dash"), name="Reference (5)",
    ))
    fig.update_layout(
        title=f"Portfolio Health — Score: {health_data.get('health_score', 'N/A')}",
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 10], gridcolor="#30363d"),
            angularaxis=dict(gridcolor="#30363d"),
            bgcolor="#0d1117",
        ),
        paper_bgcolor="#0d1117", font_color="#e6edf3",
        legend=dict(font_color="#e6edf3"),
        margin=dict(t=60, b=30, l=40, r=40),
    )
    return _to_png(fig)


def _chart_eve_profile(eve_data: dict) -> bytes:
    import plotly.graph_objects as go
    profile = eve_data.get("eve_profile", {})
    shocks  = sorted(profile.keys(), key=lambda s: int(s.replace("bps", "").replace("+", "").replace("m", "-")))
    pct_chg = [profile[s].get("pct_change", 0) for s in shocks]
    colors  = ["#ef4444" if v < -5 else "#f97316" if v < 0 else "#22c55e" for v in pct_chg]
    limit   = eve_data.get("eve_limit_pct", -5)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=shocks, y=pct_chg, marker_color=colors,
                         text=[f"{v:.1f}%" for v in pct_chg], textposition="outside"))
    fig.add_hline(y=limit, line_dash="dash", line_color="#ff6b6b",
                  annotation_text=f"EVE Limit ({limit:.0f}%)", annotation_font_color="#ff6b6b")
    fig.update_layout(
        title="EVE Sensitivity — Rate Shock Scenarios",
        xaxis_title="Rate Shock", yaxis_title="EVE Change (%)",
        paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", font_color="#e6edf3",
        margin=dict(t=60, b=40, l=60, r=40),
    )
    fig.update_xaxes(gridcolor="#30363d")
    fig.update_yaxes(gridcolor="#30363d", zerolinecolor="#58a6ff")
    return _to_png(fig)


def _chart_attribution_waterfall(attr_data: dict, title: str, unit: str, color: str) -> bytes:
    import plotly.graph_objects as go
    drivers = attr_data.get("attribution", {})
    if not drivers:
        return None
    labels = [d.replace("_", " ").title() for d in drivers]
    values = list(drivers.values())
    total  = sum(values)
    measure = ["relative"] * len(values) + ["total"]
    labels.append("Total")
    values.append(total)
    pos_color = color
    neg_color = "#ef4444"
    tot_color = "#58a6ff"
    fig = go.Figure(go.Waterfall(
        orientation="v", measure=measure,
        x=labels, y=values,
        connector={"line": {"color": "#30363d"}},
        increasing={"marker": {"color": pos_color}},
        decreasing={"marker": {"color": neg_color}},
        totals={"marker": {"color": tot_color}},
        text=[f"{v:+.2f}" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        title=f"{title} ({unit})",
        yaxis_title=unit,
        paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", font_color="#e6edf3",
        margin=dict(t=60, b=80, l=60, r=40),
    )
    fig.update_xaxes(gridcolor="#30363d")
    fig.update_yaxes(gridcolor="#30363d", zerolinecolor="#58a6ff")
    return _to_png(fig)


# ═════════════════════════════════════════════════════════════════════════════
# 4.  Google Drive image upload
# ═════════════════════════════════════════════════════════════════════════════

def _upload_image(drive_svc, png_bytes: bytes, name: str) -> str:
    """Upload PNG bytes to Drive, grant public read, return accessible URL."""
    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(io.BytesIO(png_bytes), mimetype="image/png", resumable=False)
    f = drive_svc.files().create(
        body={"name": name, "mimeType": "image/png"},
        media_body=media,
        fields="id",
    ).execute()
    fid = f["id"]
    drive_svc.permissions().create(
        fileId=fid,
        body={"type": "anyone", "role": "reader"},
    ).execute()
    return fid, f"https://drive.google.com/uc?id={fid}"


def _delete_drive_files(drive_svc, file_ids: list[str]) -> None:
    for fid in file_ids:
        try:
            drive_svc.files().delete(fileId=fid).execute()
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════════════
# 5.  Google Slides builder helpers
# ═════════════════════════════════════════════════════════════════════════════

# Slide dimensions (widescreen 16:9, Google default)
_W_PT  = 720.0    # width  in points
_H_PT  = 405.0    # height in points
_W_EMU = 9144000  # width  in EMU
_H_EMU = 5143500  # height in EMU

def _pt(val: float) -> dict:
    return {"magnitude": val, "unit": "PT"}

def _emu(val: int) -> dict:
    return {"magnitude": val, "unit": "EMU"}

def _rgb(r: float, g: float, b: float) -> dict:
    return {"rgbColor": {"red": r, "green": g, "blue": b}}

def _transform(x_pt: float, y_pt: float, w_pt: float, h_pt: float) -> dict:
    return {
        "scaleX": 1, "scaleY": 1,
        "translateX": x_pt * 12700,   # 1 pt = 12700 EMU
        "translateY": y_pt * 12700,
        "unit": "EMU",
    }

def _size(w_pt: float, h_pt: float) -> dict:
    return {
        "width":  _pt(w_pt),
        "height": _pt(h_pt),
    }

def _element_props(slide_id: str, x: float, y: float, w: float, h: float) -> dict:
    return {
        "pageObjectId": slide_id,
        "size": _size(w, h),
        "transform": _transform(x, y, w, h),
    }

# ── Colour palette ────────────────────────────────────────────────────────────
_BG      = (0.051, 0.067, 0.090)   # #0d1117
_ACCENT  = (0.227, 0.435, 0.820)   # #3A6FD1 (blue)
_TEXT_LT = (0.902, 0.929, 0.953)   # #e6edf3
_TEXT_DK = (0.133, 0.153, 0.188)   # #222731
_HEADER  = (0.086, 0.110, 0.149)   # #16_1C26 (slightly lighter than bg)
_GREEN   = (0.133, 0.769, 0.369)
_RED     = (0.937, 0.267, 0.267)

def _solid_fill(r, g, b):
    return {"solidFill": {"color": _rgb(r, g, b)}}


def _mk_id() -> str:
    return f"obj_{uuid.uuid4().hex[:12]}"


class SlideBuilder:
    """
    Accumulates batchUpdate requests for a single presentation.
    Call .flush() to send all pending requests.
    """

    def __init__(self, slides_svc, presentation_id: str):
        self.svc   = slides_svc
        self.pid   = presentation_id
        self._reqs: list[dict] = []

    def flush(self) -> None:
        if not self._reqs:
            return
        self.svc.presentations().batchUpdate(
            presentationId=self.pid,
            body={"requests": self._reqs},
        ).execute()
        self._reqs = []

    # ── Slide creation ────────────────────────────────────────────────────────

    def add_blank_slide(self) -> str:
        """Add a blank slide and return its object ID."""
        sid = _mk_id()
        self._reqs.append({
            "createSlide": {
                "objectId": sid,
                "slideLayoutReference": {"predefinedLayout": "BLANK"},
            }
        })
        self.flush()
        # Set slide background
        self._reqs.append({
            "updatePageProperties": {
                "objectId": sid,
                "pageProperties": {
                    "pageBackgroundFill": _solid_fill(*_BG),
                },
                "fields": "pageBackgroundFill",
            }
        })
        self.flush()
        return sid

    # ── Element helpers ───────────────────────────────────────────────────────

    def add_textbox(
        self, slide_id: str, text: str,
        x: float, y: float, w: float, h: float,
        font_size: float = 11, bold: bool = False, italic: bool = False,
        color=(0.902, 0.929, 0.953),
        align: str = "LEFT",
        bg: tuple | None = None,
    ) -> str:
        oid = _mk_id()
        reqs = [
            {
                "createShape": {
                    "objectId": oid,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": _element_props(slide_id, x, y, w, h),
                }
            },
            {
                "insertText": {
                    "objectId": oid,
                    "insertionIndex": 0,
                    "text": text,
                }
            },
            {
                "updateTextStyle": {
                    "objectId": oid,
                    "style": {
                        "fontSize": _pt(font_size),
                        "bold": bold,
                        "italic": italic,
                        "foregroundColor": {"opaqueColor": _rgb(*color)},
                        "fontFamily": "Arial",
                    },
                    "fields": "fontSize,bold,italic,foregroundColor,fontFamily",
                }
            },
            {
                "updateParagraphStyle": {
                    "objectId": oid,
                    "style": {"alignment": align},
                    "fields": "alignment",
                }
            },
        ]
        if bg:
            reqs.append({
                "updateShapeProperties": {
                    "objectId": oid,
                    "shapeProperties": {
                        "shapeBackgroundFill": _solid_fill(*bg),
                    },
                    "fields": "shapeBackgroundFill",
                }
            })
        self._reqs.extend(reqs)
        return oid

    def add_image(self, slide_id: str, url: str,
                  x: float, y: float, w: float, h: float) -> str:
        oid = _mk_id()
        self._reqs.append({
            "createImage": {
                "objectId": oid,
                "url": url,
                "elementProperties": _element_props(slide_id, x, y, w, h),
            }
        })
        return oid

    def add_rect(self, slide_id: str, x: float, y: float, w: float, h: float,
                 fill: tuple = _ACCENT) -> str:
        oid = _mk_id()
        self._reqs.extend([
            {
                "createShape": {
                    "objectId": oid,
                    "shapeType": "RECTANGLE",
                    "elementProperties": _element_props(slide_id, x, y, w, h),
                }
            },
            {
                "updateShapeProperties": {
                    "objectId": oid,
                    "shapeProperties": {
                        "shapeBackgroundFill": _solid_fill(*fill),
                        "outline": {"outlineFill": {"solidFill": {"color": _rgb(*fill)}}},
                    },
                    "fields": "shapeBackgroundFill,outline",
                }
            },
        ])
        return oid

    # ── Table helper ──────────────────────────────────────────────────────────

    def add_table(
        self,
        slide_id: str,
        headers: list[str],
        rows: list[list[str]],
        x: float, y: float, w: float, h: float,
        font_size: float = 8,
    ) -> str:
        n_rows = len(rows) + 1   # +1 for header
        n_cols = len(headers)
        tid    = _mk_id()

        reqs = [
            {
                "createTable": {
                    "objectId": tid,
                    "elementProperties": _element_props(slide_id, x, y, w, h),
                    "rows": n_rows,
                    "columns": n_cols,
                }
            }
        ]
        self._reqs.extend(reqs)
        self.flush()

        # Fill header row
        for ci, hdr in enumerate(headers):
            self._reqs.extend([
                {
                    "insertText": {
                        "objectId": tid,
                        "cellLocation": {"rowIndex": 0, "columnIndex": ci},
                        "text": str(hdr),
                    }
                },
                {
                    "updateTextStyle": {
                        "objectId": tid,
                        "cellLocation": {"rowIndex": 0, "columnIndex": ci},
                        "style": {
                            "bold": True,
                            "fontSize": _pt(font_size),
                            "foregroundColor": {"opaqueColor": _rgb(*_TEXT_LT)},
                            "fontFamily": "Arial",
                        },
                        "fields": "bold,fontSize,foregroundColor,fontFamily",
                    }
                },
                {
                    "updateTableCellProperties": {
                        "objectId": tid,
                        "tableRange": {
                            "location": {"rowIndex": 0, "columnIndex": ci},
                            "rowSpan": 1, "columnSpan": 1,
                        },
                        "tableCellProperties": {
                            "tableCellBackgroundFill": _solid_fill(*_ACCENT),
                        },
                        "fields": "tableCellBackgroundFill",
                    }
                },
            ])

        # Fill data rows
        for ri, row in enumerate(rows):
            bg = _HEADER if ri % 2 == 0 else _BG
            for ci, cell in enumerate(row):
                self._reqs.extend([
                    {
                        "insertText": {
                            "objectId": tid,
                            "cellLocation": {"rowIndex": ri + 1, "columnIndex": ci},
                            "text": str(cell),
                        }
                    },
                    {
                        "updateTextStyle": {
                            "objectId": tid,
                            "cellLocation": {"rowIndex": ri + 1, "columnIndex": ci},
                            "style": {
                                "fontSize": _pt(font_size),
                                "foregroundColor": {"opaqueColor": _rgb(*_TEXT_LT)},
                                "fontFamily": "Arial",
                            },
                            "fields": "fontSize,foregroundColor,fontFamily",
                        }
                    },
                    {
                        "updateTableCellProperties": {
                            "objectId": tid,
                            "tableRange": {
                                "location": {"rowIndex": ri + 1, "columnIndex": ci},
                                "rowSpan": 1, "columnSpan": 1,
                            },
                            "tableCellProperties": {
                                "tableCellBackgroundFill": _solid_fill(*bg),
                            },
                            "fields": "tableCellBackgroundFill",
                        }
                    },
                ])

        self.flush()
        return tid

    # ── Convenience slide layouts ─────────────────────────────────────────────

    def title_slide(self, title: str, subtitle: str) -> str:
        sid = self.add_blank_slide()
        # Accent bar
        self.add_rect(sid, 0, 0, _W_PT, 8, fill=_ACCENT)
        self.add_rect(sid, 0, _H_PT - 8, _W_PT, 8, fill=_ACCENT)
        # Title
        self.add_textbox(sid, title, 60, 130, 600, 60,
                         font_size=32, bold=True, color=_TEXT_LT, align="CENTER")
        # Subtitle
        self.add_textbox(sid, subtitle, 60, 200, 600, 30,
                         font_size=14, italic=True, color=(0.6, 0.7, 0.8), align="CENTER")
        self.flush()
        return sid

    def section_header(self, title: str, icon: str = "") -> str:
        sid = self.add_blank_slide()
        self.add_rect(sid, 0, 0, 8, _H_PT, fill=_ACCENT)
        self.add_textbox(sid, f"{icon}  {title}".strip(), 30, 160, 660, 60,
                         font_size=28, bold=True, color=_TEXT_LT, align="LEFT")
        self.flush()
        return sid

    def slide_with_title(self, title: str) -> str:
        """Add a blank slide with a styled title bar. Returns slide ID."""
        sid = self.add_blank_slide()
        self.add_rect(sid, 0, 0, _W_PT, 38, fill=(0.086, 0.110, 0.149))
        self.add_textbox(sid, title, 12, 6, _W_PT - 24, 26,
                         font_size=14, bold=True, color=_TEXT_LT)
        self.flush()
        return sid


# ═════════════════════════════════════════════════════════════════════════════
# 6.  Slide content builders  (one function per slide)
# ═════════════════════════════════════════════════════════════════════════════

def _safe(val, fmt=None, fallback="N/A"):
    if val is None:
        return fallback
    try:
        return fmt.format(val) if fmt else str(val)
    except Exception:
        return str(val)


def build_cover(sb: SlideBuilder, title: str, as_of: str) -> None:
    sb.title_slide(title, f"As of {as_of}  •  Oasia MBS Analytics Platform")


def build_dashboard_kpis(sb: SlideBuilder, data: dict) -> None:
    s   = data["summary"]
    sid = sb.slide_with_title("Dashboard — Portfolio KPIs")

    kpis = [
        ("Market Value",   _safe(s.get("total_market_value"), "${:.1f}M")),
        ("Book Value",     _safe(s.get("total_book_value"),   "${:.1f}M")),
        ("Positions",      _safe(s.get("position_count"),     "{:,}")),
        ("OAS",            _safe(s.get("weighted_oas_bps"),   "{:.1f} bps")),
        ("OAD",            _safe(s.get("weighted_oad_years"), "{:.2f} yr")),
        ("Book Yield",     _safe(s.get("book_yield_pct"),     "{:.2f}%")),
        ("Unrealized P&L", _safe(s.get("unrealized_pnl"),     "${:.0f}K")),
        ("EVE +200bp",     _safe(s.get("eve_up200_change_pct"), "{:.1f}%")),
    ]
    breach = s.get("eve_breach", False)

    card_w, card_h = 82, 60
    margin_x, start_y = 14, 50
    for i, (label, value) in enumerate(kpis):
        col = i % 4
        row = i // 4
        cx  = margin_x + col * (card_w + 10)
        cy  = start_y  + row * (card_h + 10)
        is_eve = "EVE" in label
        fill   = (0.55, 0.1, 0.1) if (is_eve and breach) else (0.086, 0.110, 0.149)
        sb.add_rect(sid, cx, cy, card_w, card_h, fill=fill)
        sb.add_textbox(sid, label, cx + 4, cy + 5,  card_w - 8, 14, font_size=7, color=(0.6, 0.7, 0.8))
        sb.add_textbox(sid, value, cx + 4, cy + 22, card_w - 8, 24, font_size=16, bold=True, color=_TEXT_LT)

    # Note if EVE breach
    if breach:
        sb.add_textbox(sid, "⚠ EVE BREACH — review required", 14, 195, 450, 16,
                       font_size=9, bold=True, color=_RED)
    sb.flush()


def build_sector_chart(sb: SlideBuilder, drive_svc, data: dict,
                       uploaded_ids: list) -> None:
    png = _chart_sector_donut(data["sectors"])
    fid, url = _upload_image(drive_svc, png, "chart_sector.png")
    uploaded_ids.append(fid)
    sid = sb.slide_with_title("Dashboard — Sector Allocation")
    sb.add_image(sid, url, 60, 45, 600, 340)
    sb.flush()


def build_ytd_chart(sb: SlideBuilder, drive_svc, data: dict,
                    uploaded_ids: list) -> None:
    png = _chart_ytd_bar(data["performers"])
    fid, url = _upload_image(drive_svc, png, "chart_ytd.png")
    uploaded_ids.append(fid)
    sid = sb.slide_with_title("Dashboard — YTD Performance")
    sb.add_image(sid, url, 20, 45, 680, 340)
    sb.flush()


def build_health_radar(sb: SlideBuilder, drive_svc, data: dict,
                       uploaded_ids: list) -> None:
    png = _chart_health_radar(data["health"])
    fid, url = _upload_image(drive_svc, png, "chart_health.png")
    uploaded_ids.append(fid)
    sid = sb.slide_with_title("Dashboard — Portfolio Health")

    # Health table on the right
    dims = data["health"].get("sub_metrics", {})
    rows = [[k, f"{v['score']:.1f}/10", v.get("desc", "")] for k, v in dims.items()]
    sb.add_image(sid, url, 10, 45, 390, 330)
    if rows:
        sb.add_table(sid, ["Dimension", "Score", "Comment"],
                     rows, 410, 50, 295, min(len(rows) * 28 + 28, 320), font_size=8)
    sb.flush()


def build_portfolio_summary(sb: SlideBuilder, data: dict) -> None:
    s   = data["summary"]
    sid = sb.slide_with_title("Portfolio Analytics — Summary")
    summary_rows = [
        ["Total Market Value",   _safe(s.get("total_market_value"),     "${:.2f}M")],
        ["Total Book Value",     _safe(s.get("total_book_value"),       "${:.2f}M")],
        ["Unrealized P&L",       _safe(s.get("unrealized_pnl"),         "${:.0f}K")],
        ["# Positions",          _safe(s.get("position_count"),         "{:,}")],
        ["Weighted OAS",         _safe(s.get("weighted_oas_bps"),       "{:.1f} bps")],
        ["Weighted OAD",         _safe(s.get("weighted_oad_years"),     "{:.2f} yr")],
        ["Weighted Convexity",   _safe(s.get("weighted_convexity"),     "{:.3f}")],
        ["Book Yield",           _safe(s.get("book_yield_pct"),         "{:.2f}%")],
        ["Annual Income (est.)", _safe(s.get("annual_income"),          "${:.0f}K")],
        ["Base EVE",             _safe(s.get("eve_base"),               "${:.0f}K")],
        ["EVE Δ +200bp",         _safe(s.get("eve_up200_change_pct"),   "{:.1f}%")],
        ["EVE Limit",            _safe(s.get("eve_limit_pct"),          "{:.1f}%")],
    ]
    sb.add_table(sid, ["Metric", "Value"], summary_rows, 20, 48, 340, 330, font_size=9)

    # Top-5 positions on the right
    pos_list = data["positions"].get("positions", [])[:5]
    if pos_list:
        pos_rows = [
            [p.get("pool_id", ""),
             p.get("product_type", ""),
             _safe(p.get("market_value"), "${:.1f}M"),
             _safe(p.get("oas_bps"), "{:.0f}"),
             _safe(p.get("oad_years"), "{:.2f}")]
            for p in pos_list
        ]
        sb.add_table(sid, ["Pool", "Type", "MV", "OAS", "OAD"],
                     pos_rows, 380, 48, 325, 200, font_size=8)
    sb.flush()


def build_eve_chart(sb: SlideBuilder, drive_svc, data: dict,
                    uploaded_ids: list) -> None:
    png = _chart_eve_profile(data["eve"])
    fid, url = _upload_image(drive_svc, png, "chart_eve.png")
    uploaded_ids.append(fid)
    sid = sb.slide_with_title("Portfolio Analytics — EVE Stress Test")

    # EVE table on the right
    profile = data["eve"].get("eve_profile", {})
    shocks  = sorted(profile.keys(), key=lambda s: int(
        s.replace("bps", "").replace("+", "").replace("m", "-")))
    rows = [
        [s,
         _safe(profile[s].get("pct_change"), "{:+.1f}%"),
         "⚠ BREACH" if profile[s].get("breach") else "OK"]
        for s in shocks
    ]
    sb.add_image(sid, url, 10, 45, 440, 330)
    sb.add_table(sid, ["Shock", "EVE Δ%", "Status"], rows,
                 465, 50, 240, min(len(rows) * 28 + 28, 320), font_size=9)
    sb.flush()


def build_holdings_table(sb: SlideBuilder, data: dict) -> None:
    pos_list = data["positions"].get("positions", [])[:12]
    sid = sb.slide_with_title("Portfolio Analytics — Holdings")
    if not pos_list:
        sb.add_textbox(sid, "No positions available.", 20, 60, 680, 30, font_size=11)
        sb.flush()
        return
    rows = [
        [p.get("pool_id", ""),
         p.get("product_type", ""),
         _safe(p.get("coupon_pct"), "{:.2f}%"),
         _safe(p.get("par_value"), "${:.1f}M"),
         _safe(p.get("market_value"), "${:.1f}M"),
         _safe(p.get("oas_bps"), "{:.0f}"),
         _safe(p.get("oad_years"), "{:.2f}"),
         _safe(p.get("unrealized_pnl_pct"), "{:+.2f}%")]
        for p in pos_list
    ]
    sb.add_table(sid, ["Pool ID", "Type", "Cpn", "Par ($M)", "MV ($M)", "OAS", "OAD", "P&L%"],
                 rows, 12, 48, 696, min(len(rows) * 24 + 28, 340), font_size=8)
    sb.flush()


def build_security_overview(sb: SlideBuilder, data: dict) -> None:
    univ = data["universe"]
    sid  = sb.slide_with_title("Security Analytics — Universe Overview")

    by_prod = univ.get("by_product", [])
    if by_prod:
        rows = [
            [p.get("product_type", ""),
             str(p.get("count", "")),
             _safe(p.get("total_balance_bn"), "{:.2f}B"),
             _safe(p.get("avg_coupon_pct"), "{:.2f}%"),
             _safe(p.get("avg_oas_bps"), "{:.0f}"),
             _safe(p.get("avg_oad_years"), "{:.2f}"),
             _safe(p.get("avg_cpr_pct"), "{:.1f}%"),
             _safe(p.get("avg_fico"), "{:.0f}")]
            for p in by_prod
        ]
        sb.add_table(
            sid,
            ["Product", "Count", "Balance", "Avg Cpn", "Avg OAS", "Avg OAD", "Avg CPR", "Avg FICO"],
            rows, 12, 48, 696, min(len(rows) * 32 + 36, 330), font_size=9,
        )

    # Summary stats
    sb.add_textbox(
        sid,
        f"Total pools: {univ.get('total_pools', 'N/A')}   |   "
        f"Total balance: {_safe(univ.get('total_balance_bn'), '{:.2f}B')}",
        12, 370, 696, 20,
        font_size=9, italic=True, color=(0.6, 0.7, 0.8),
    )
    sb.flush()


def build_security_detail(sb: SlideBuilder, data: dict) -> None:
    pool_id = data["sec_pool"]
    details = data["pool_details"]
    shocks  = data["shock_table"]
    if not pool_id or not details:
        return

    sid = sb.slide_with_title(f"Security Analytics — {pool_id}")
    static = details.get("static", {})

    info_rows = [
        ["Pool ID",       static.get("pool_id", pool_id)],
        ["Product",       static.get("product_type", "")],
        ["Coupon",        _safe(static.get("coupon_pct"), "{:.2f}%")],
        ["WAC",           _safe(static.get("wac_pct"), "{:.2f}%")],
        ["WALA",          _safe(static.get("wala_at_issue"), "{:.0f} mo")],
        ["WAM",           _safe(static.get("original_wam"), "{:.0f} mo")],
        ["FICO",          _safe(static.get("fico"), "{:.0f}")],
        ["LTV",           _safe(static.get("ltv"), "{:.1f}%")],
        ["Orig. Balance", _safe(static.get("original_balance"), "${:.1f}M")],
    ]
    sb.add_table(sid, ["Characteristic", "Value"], info_rows, 12, 48, 260, 270, font_size=9)

    # Rate shock table from scenario tool
    if shocks and isinstance(shocks, dict):
        scenarios = shocks.get("scenarios", shocks.get("results", []))
        if scenarios:
            shock_rows = [
                [str(sc.get("shock_bps", sc.get("scenario", ""))),
                 _safe(sc.get("oas_bps"), "{:.0f}"),
                 _safe(sc.get("oad_years"), "{:.2f}"),
                 _safe(sc.get("convexity"), "{:.3f}"),
                 _safe(sc.get("yield_pct"), "{:.2f}%"),
                 _safe(sc.get("cpr_pct"), "{:.1f}%")]
                for sc in scenarios[:9]
            ]
            sb.add_table(
                sid, ["Shock (bps)", "OAS", "OAD", "Convexity", "Yield", "CPR"],
                shock_rows, 290, 48, 415, min(len(shock_rows) * 28 + 28, 320),
                font_size=8,
            )
    sb.flush()


def build_attribution_slide(sb: SlideBuilder, drive_svc,
                             attr_data: dict, title: str, unit: str,
                             color: str, uploaded_ids: list) -> None:
    color_map = {
        "cyan":  (0.086, 0.667, 0.769),
        "green": (0.133, 0.769, 0.369),
        "amber": (0.855, 0.604, 0.133),
    }
    rgb = color_map.get(color, (0.086, 0.667, 0.769))
    png = _chart_attribution_waterfall(attr_data, title, unit, f"rgb({int(rgb[0]*255)},{int(rgb[1]*255)},{int(rgb[2]*255)})")
    if png is None:
        return

    fid, url = _upload_image(drive_svc, png, f"chart_attr_{title[:6].lower()}.png")
    uploaded_ids.append(fid)

    sid = sb.slide_with_title(f"Attribution — {title}")
    sb.add_image(sid, url, 10, 45, 430, 320)

    # Driver table on the right
    drivers = attr_data.get("attribution", {})
    if drivers:
        rows = [[d.replace("_", " ").title(), f"{v:+.2f} {unit}"] for d, v in drivers.items()]
        total = sum(drivers.values())
        rows.append(["Total", f"{total:+.2f} {unit}"])
        sb.add_table(sid, ["Driver", "Value"], rows,
                     455, 50, 250, min(len(rows) * 26 + 28, 330), font_size=9)
    sb.flush()


# ═════════════════════════════════════════════════════════════════════════════
# 7.  Main orchestrator
# ═════════════════════════════════════════════════════════════════════════════

def build_presentation(
    title:            str,
    credentials_path: str,
    pool_id:          str | None,
    cleanup:          bool,
) -> str:
    """Build the full presentation and return its URL."""

    print("\n[1/4] Authenticating with Google …")
    slides_svc, drive_svc = _build_services(credentials_path)

    print("[2/4] Fetching data from Oasia …")
    data   = _fetch_all_data(pool_id)
    as_of  = data["summary"].get("as_of_date", str(date.today()))

    print("[3/4] Building presentation …")
    prs = slides_svc.presentations().create(
        body={"title": title}
    ).execute()
    prs_id = prs["presentationId"]

    # Delete the default blank slide Google inserts
    default_slide = prs["slides"][0]["objectId"]
    slides_svc.presentations().batchUpdate(
        presentationId=prs_id,
        body={"requests": [{"deleteObject": {"objectId": default_slide}}]},
    ).execute()

    sb = SlideBuilder(slides_svc, prs_id)
    uploaded_ids: list[str] = []

    # ── Cover ────────────────────────────────────────────────────────────────
    print("  Slide: Cover")
    build_cover(sb, title, as_of)

    # ── Dashboard ────────────────────────────────────────────────────────────
    print("  Section: Dashboard")
    sb.section_header("Dashboard", "📊")
    build_dashboard_kpis(sb, data)
    print("  Uploading sector chart …")
    build_sector_chart(sb, drive_svc, data, uploaded_ids)
    print("  Uploading YTD chart …")
    build_ytd_chart(sb, drive_svc, data, uploaded_ids)
    print("  Uploading health radar …")
    build_health_radar(sb, drive_svc, data, uploaded_ids)

    # ── Portfolio Analytics ──────────────────────────────────────────────────
    print("  Section: Portfolio Analytics")
    sb.section_header("Portfolio Analytics", "📈")
    build_portfolio_summary(sb, data)
    print("  Uploading EVE chart …")
    build_eve_chart(sb, drive_svc, data, uploaded_ids)
    build_holdings_table(sb, data)

    # ── Security Analytics ───────────────────────────────────────────────────
    print("  Section: Security Analytics")
    sb.section_header("Security Analytics", "🔍")
    build_security_overview(sb, data)
    build_security_detail(sb, data)

    # ── Attribution ──────────────────────────────────────────────────────────
    print("  Section: Attribution")
    sb.section_header("Attribution Analysis", "⚖️")
    for attr, title_str, unit, color in [
        ("attr_oas",   "OAS Attribution",   "bps",  "cyan"),
        ("attr_oad",   "OAD Attribution",   "yrs",  "green"),
        ("attr_yield", "Yield Attribution", "%",    "amber"),
        ("attr_eve",   "EVE Attribution",   "$K",   "cyan"),
    ]:
        print(f"  Uploading {title_str} chart …")
        build_attribution_slide(sb, drive_svc, data[attr],
                                title_str, unit, color, uploaded_ids)

    sb.flush()

    # ── Cleanup temp Drive files ─────────────────────────────────────────────
    if cleanup and uploaded_ids:
        print(f"[4/4] Cleaning up {len(uploaded_ids)} temp Drive files …")
        _delete_drive_files(drive_svc, uploaded_ids)
    else:
        print(f"[4/4] Keeping {len(uploaded_ids)} chart images in Google Drive.")

    url = f"https://docs.google.com/presentation/d/{prs_id}/edit"
    print(f"\n✓ Presentation ready: {url}\n")
    return url


# ═════════════════════════════════════════════════════════════════════════════
# 8.  CLI entry point
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Oasia analytics to a Google Slides presentation."
    )
    parser.add_argument(
        "--title",
        default=f"Oasia Portfolio Report — {date.today().strftime('%B %d, %Y')}",
        help="Presentation title (default: 'Oasia Portfolio Report — <today>')",
    )
    parser.add_argument(
        "--credentials",
        default=str(_ROOT / "credentials.json"),
        help="Path to Google OAuth2 credentials.json (default: <project_root>/credentials.json)",
    )
    parser.add_argument(
        "--pool",
        default=None,
        help="Pool ID to feature in the Security Analytics section (default: first position)",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Keep temporary chart PNG files in Google Drive after the run",
    )
    args = parser.parse_args()

    try:
        url = build_presentation(
            title=args.title,
            credentials_path=args.credentials,
            pool_id=args.pool,
            cleanup=not args.no_cleanup,
        )
        print(url)
    except FileNotFoundError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        import traceback
        print(f"\nERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
