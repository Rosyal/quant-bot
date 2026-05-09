"""
纸面实盘 Web 看板: 资金曲线、持仓、成交记录

启动: python main.py web
或: python -m web.app

PyInstaller 打包后模板/静态资源在 sys._MEIPASS 下。
"""
from __future__ import annotations

import json
import os
import sys

from flask import Flask, Response, jsonify, render_template, request

from config import INITIAL_BALANCE, PAPER_LIVE_STATE_PATH
from db.database import Database


def _apply_security_headers(response):
    """基础安全头; 开关见 config.WEB_SECURITY_HEADERS_ENABLED。"""
    from config import WEB_SECURITY_HEADERS_ENABLED

    if not WEB_SECURITY_HEADERS_ENABLED:
        return response
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "geolocation=(), microphone=(), camera=()",
    )
    # 纸面看板需内联 script/style; 生产若挂 CDN 需收紧 CSP
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self';"
    )
    response.headers.setdefault("Content-Security-Policy", csp)
    return response


def _project_base() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_BASE = _project_base()
app = Flask(
    __name__,
    template_folder=os.path.join(_BASE, "web", "templates"),
    static_folder=os.path.join(_BASE, "web", "static"),
    static_url_path="/static",
)

app.after_request(_apply_security_headers)

# main.py cmd_web 写入, 驱动看板前端轮询间隔
DASH_REFRESH_SEC = 8

# 状态文件 mtime 缓存, 降低高频轮询读盘
_state_cache: dict = {"path": "", "mtime": None, "data": None}


def _load_state() -> dict:
    path = os.path.abspath(PAPER_LIVE_STATE_PATH)
    if not os.path.isfile(path):
        _state_cache.update({"path": path, "mtime": None, "data": None})
        return {
            "usdt": INITIAL_BALANCE,
            "positions": {},
            "trades": [],
            "equity_curve": [],
            "last_signals": {},
            "updated_at": 0,
        }
    try:
        mtime = os.path.getmtime(path)
        if (
            _state_cache["path"] == path
            and _state_cache["mtime"] == mtime
            and _state_cache["data"] is not None
        ):
            return _state_cache["data"]
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _state_cache.update({"path": path, "mtime": mtime, "data": data})
        return data
    except (json.JSONDecodeError, OSError):
        return {"error": "state unreadable"}


def _state_etag() -> str:
    path = os.path.abspath(PAPER_LIVE_STATE_PATH)
    if not os.path.isfile(path):
        return '"empty"'
    return f'"st-{int(os.path.getmtime(path) * 1000)}"'


@app.route("/")
def index():
    return render_template(
        "index.html",
        state_path=PAPER_LIVE_STATE_PATH,
        refresh_sec=max(3, int(DASH_REFRESH_SEC)),
    )


@app.route("/manifest.webmanifest")
def manifest():
    """PWA 清单 (添加到主屏幕 / 类 App 体验)"""
    return Response(
        json.dumps(
            {
                "name": "Quant 纸面实盘",
                "short_name": "纸面实盘",
                "description": "量化纸面模拟资金与持仓看板",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "background_color": "#0f1419",
                "theme_color": "#0f1419",
                "lang": "zh-CN",
            },
            ensure_ascii=False,
        ),
        mimetype="application/manifest+json",
    )


@app.route("/sw.js")
def service_worker():
    """离线壳: 首页与静态资源; API 仍走网络"""
    sw_path = os.path.join(app.static_folder or "", "sw.js")
    if os.path.isfile(sw_path):
        with open(sw_path, encoding="utf-8") as f:
            body = f.read()
        return Response(body, mimetype="application/javascript")
    return Response("// sw missing", mimetype="application/javascript")


@app.route("/api/portfolio")
def api_portfolio():
    tag = _state_etag()
    if request.headers.get("If-None-Match") == tag:
        return Response(status=304)
    st = _load_state()
    if st.get("error"):
        return jsonify(st), 500
    resp = jsonify(
        {
            "usdt": st.get("usdt", 0),
            "positions": st.get("positions", {}),
            "updated_at": st.get("updated_at", 0),
            "initial_balance": INITIAL_BALANCE,
        }
    )
    resp.headers["ETag"] = tag
    resp.headers["Cache-Control"] = "private, max-age=2"
    return resp


@app.route("/api/equity")
def api_equity():
    tag = _state_etag()
    if request.headers.get("If-None-Match") == tag:
        return Response(status=304)
    st = _load_state()
    if st.get("error"):
        return jsonify(st), 500
    curve = st.get("equity_curve") or []
    resp = jsonify({"points": curve})
    resp.headers["ETag"] = tag
    resp.headers["Cache-Control"] = "private, max-age=2"
    return resp


@app.route("/api/trades")
def api_trades():
    tag = _state_etag()
    if request.headers.get("If-None-Match") == tag:
        return Response(status=304)
    st = _load_state()
    if st.get("error"):
        return jsonify(st), 500
    trades = list(st.get("trades") or [])
    trades.reverse()
    resp = jsonify({"trades": trades[:500]})
    resp.headers["ETag"] = tag
    resp.headers["Cache-Control"] = "private, max-age=2"
    return resp


@app.route("/health")
def health():
    return Response("ok", mimetype="text/plain")


@app.route("/api/news")
def api_news():
    """消息池最近条目 (需先 python main.py news-sync)"""
    try:
        limit = min(100, max(1, int(request.args.get("limit", 30))))
        hours = max(1, int(request.args.get("hours", 168)))
    except (TypeError, ValueError):
        limit, hours = 30, 168
    cat = request.args.get("category")
    category = (cat.strip().lower() if isinstance(cat, str) and cat.strip() else None)
    import time

    since = int(time.time()) - hours * 3600
    db = Database()
    try:
        rows = db.list_news_items(limit=limit, since_ts=since, category=category)
    finally:
        db.close()
    return jsonify({"items": rows, "since_ts": since, "category": category})


@app.route("/api/audit")
def api_audit():
    """审计事件只读: 须设置环境变量 QUANT_BOT_AUDIT_API_KEY 且请求 ?key= 一致。"""
    secret = os.environ.get("QUANT_BOT_AUDIT_API_KEY", "").strip()
    if not secret or request.args.get("key") != secret:
        return jsonify({"error": "forbidden_or_audit_api_disabled"}), 403
    try:
        limit = min(200, max(1, int(request.args.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    db = Database()
    try:
        rows = db.list_audit_events(limit)
    finally:
        db.close()
    return jsonify({"events": rows})


def _brief_api_key_ok() -> bool:
    secret = os.environ.get("QUANT_BOT_BRIEF_API_KEY", "").strip()
    return bool(secret) and request.args.get("key") == secret


@app.route("/api/product-brief")
def api_product_brief():
    """
    官网/CRM 拉取完整证据包 JSON（与 CLI product-brief --json 同 schema）。
    须设置 QUANT_BOT_BRIEF_API_KEY 且 ?key= 一致。
    """
    if not _brief_api_key_ok():
        return jsonify({"error": "forbidden_or_brief_api_disabled"}), 403
    from deliverables.dossier import dossier_to_json
    from deliverables.runner import build_dossier_pipeline

    use_mock = request.args.get("mock", "0").lower() in ("1", "true", "yes")
    try:
        days = request.args.get("days", type=int)
        train_bars = int(request.args.get("train_bars", 500))
        test_bars = int(request.args.get("test_bars", 200))
    except (TypeError, ValueError):
        return jsonify({"error": "bad_integer_param"}), 400
    step = request.args.get("step", type=int)
    walk_forward = request.args.get("walk_forward", "0").lower() in ("1", "true", "yes")
    dossier = build_dossier_pipeline(
        use_mock=use_mock,
        days=days,
        strategy=request.args.get("strategy"),
        profile=request.args.get("profile"),
        strategies_csv=request.args.get("strategies"),
        walk_forward=walk_forward,
        train_bars=train_bars,
        test_bars=test_bars,
        step=step,
    )
    if dossier.get("error"):
        return jsonify(dossier), 400
    return Response(dossier_to_json(dossier), mimetype="application/json; charset=utf-8")


@app.route("/api/product-brief.pdf")
def api_product_brief_pdf():
    """同上，返回单页 PDF（需 fpdf2）。"""
    if not _brief_api_key_ok():
        return jsonify({"error": "forbidden_or_brief_api_disabled"}), 403
    from deliverables.pdf_export import render_dossier_pdf_bytes
    from deliverables.runner import build_dossier_pipeline

    use_mock = request.args.get("mock", "0").lower() in ("1", "true", "yes")
    try:
        days = request.args.get("days", type=int)
        train_bars = int(request.args.get("train_bars", 500))
        test_bars = int(request.args.get("test_bars", 200))
    except (TypeError, ValueError):
        return jsonify({"error": "bad_integer_param"}), 400
    step = request.args.get("step", type=int)
    walk_forward = request.args.get("walk_forward", "0").lower() in ("1", "true", "yes")
    dossier = build_dossier_pipeline(
        use_mock=use_mock,
        days=days,
        strategy=request.args.get("strategy"),
        profile=request.args.get("profile"),
        strategies_csv=request.args.get("strategies"),
        walk_forward=walk_forward,
        train_bars=train_bars,
        test_bars=test_bars,
        step=step,
    )
    if dossier.get("error"):
        return jsonify(dossier), 400
    try:
        raw = render_dossier_pdf_bytes(dossier)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    return Response(raw, mimetype="application/pdf")


def main(host: str = "127.0.0.1", port: int = 5050, debug: bool = False) -> None:
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    main()
