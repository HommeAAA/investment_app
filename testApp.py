import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import yfinance as yf
import requests
import os
import logging
import bcrypt
import hashlib
import hmac
import time
import json
import base64
import streamlit.components.v1 as components

try:
    from webauthn import (
        generate_registration_options,
        verify_registration_response,
        generate_authentication_options,
        verify_authentication_response,
        options_to_json,
    )
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )
    WEBAUTHN_AVAILABLE = True
    WEBAUTHN_IMPORT_ERROR = ""
except Exception as e:
    WEBAUTHN_AVAILABLE = False
    WEBAUTHN_IMPORT_ERROR = str(e)

# ------------------------------
# Session State 初始化（必须放在最顶部！解决刷新登出）
# ------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "pending_auth_token" not in st.session_state:
    st.session_state.pending_auth_token = None
if "clear_auth_client" not in st.session_state:
    st.session_state.clear_auth_client = False
if "passkey_pending_action" not in st.session_state:
    st.session_state.passkey_pending_action = None
if "passkey_registration_state" not in st.session_state:
    st.session_state.passkey_registration_state = None
if "passkey_auth_state" not in st.session_state:
    st.session_state.passkey_auth_state = None

# ------------------------------
# 基础设置 + 可写数据库路径
# ------------------------------
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

DB_PATH = "/tmp/testApp.db"
AUTH_SECRET = os.environ.get("APP_AUTH_SECRET", "change-me-in-production")
AUTH_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
AUTH_LOG_PATH = "/tmp/investment_app_auth.log"
CLIENT_ID_COOKIE = "investment_app_client_id"
PASSKEY_RESULT_QUERY_KEY = "passkey_result"
PASSKEY_STATE_QUERY_KEY = "passkey_state"
PASSKEY_CHALLENGE_TTL_SECONDS = 3 * 60

def get_setting(name, default=""):
    env_value = os.environ.get(name, "").strip()
    if env_value:
        return env_value
    try:
        secret_value = st.secrets.get(name, "")
        if isinstance(secret_value, str):
            secret_value = secret_value.strip()
        return secret_value or default
    except Exception:
        return default

WEBAUTHN_RP_NAME = get_setting("WEBAUTHN_RP_NAME", "Investment App")
WEBAUTHN_RP_ID = get_setting("WEBAUTHN_RP_ID", "")
WEBAUTHN_ORIGIN = get_setting("WEBAUTHN_ORIGIN", "")

auth_logger = logging.getLogger("investment_app.auth")
if not auth_logger.handlers:
    file_handler = logging.FileHandler(AUTH_LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    auth_logger.addHandler(file_handler)
auth_logger.setLevel(logging.INFO)
auth_logger.propagate = False

def auth_log(event, **kwargs):
    details = " ".join([f"{k}={repr(v)}" for k, v in kwargs.items()])
    auth_logger.info("%s %s", event, details)

st.set_page_config(page_title="全球资产管理系统 Pro Ultimate", layout="wide", page_icon="🌍")
st.title("🌍 全球资产管理系统 Pro Ultimate")

def render_app_theme():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Sans+SC:wght@400;500;600;700&display=swap');

    :root {
        --app-bg: #f3f7fb;
        --app-panel: rgba(255, 255, 255, 0.92);
        --app-border: #d5e4f0;
        --app-text: #13314e;
        --app-accent: #0f766e;
        --app-accent-2: #14b8a6;
    }

    html, body, [class*="css"] {
        font-family: "Manrope", "IBM Plex Sans SC", "PingFang SC", "Hiragino Sans GB", sans-serif;
        color: var(--app-text);
    }

    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(1200px 480px at 8% -12%, #d7ecff 0%, transparent 60%),
            radial-gradient(1000px 420px at 100% 0%, #d8f5ef 0%, transparent 55%),
            var(--app-bg);
    }

    .block-container {
        max-width: 1180px;
        padding-top: 1.1rem;
        padding-bottom: 6rem;
    }

    h1, h2, h3 {
        color: #102b45;
        letter-spacing: -0.02em;
        font-weight: 800;
    }

    [data-testid="stSidebar"] > div:first-child {
        background: linear-gradient(180deg, #eaf3ff 0%, #f7fbff 45%, #f3f7fb 100%);
    }

    [data-testid="stExpander"] {
        border: 1px solid var(--app-border);
        border-radius: 20px;
        background: var(--app-panel);
        box-shadow: 0 10px 26px rgba(20, 50, 80, 0.08);
    }

    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid var(--app-border);
        border-radius: 16px;
        padding: 0.55rem 0.75rem;
        box-shadow: 0 6px 18px rgba(18, 43, 69, 0.06);
    }

    [data-testid="stDataFrame"] {
        border-radius: 16px;
        overflow: hidden;
        border: 1px solid var(--app-border);
    }

    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div,
    div[data-baseweb="textarea"] > div {
        border-radius: 14px;
        border-color: #ceddeb;
        background: #fcfeff;
    }

    .stButton > button {
        border-radius: 14px;
        min-height: 44px;
        font-weight: 700;
        border: 1px solid #c8dced;
        color: #11355d;
        background: #f8fbff;
    }

    .stButton > button[data-testid="baseButton-primary"] {
        border: none;
        color: #ffffff;
        background: linear-gradient(120deg, var(--app-accent) 0%, var(--app-accent-2) 100%);
        box-shadow: 0 10px 22px rgba(15, 118, 110, 0.25);
    }

    [data-testid="stCaptionContainer"] {
        color: #536e88;
    }

    .hero-card {
        border-radius: 20px;
        border: 1px solid #d7e8f4;
        background: linear-gradient(120deg, #113b63 0%, #1f6f8f 65%, #2b8f8c 100%);
        color: #eff9ff;
        padding: 14px 16px;
        margin-bottom: 0.8rem;
        box-shadow: 0 14px 34px rgba(16, 54, 88, 0.26);
    }

    .hero-title {
        font-size: 0.86rem;
        opacity: 0.86;
    }

    .hero-value {
        font-size: 1.5rem;
        font-weight: 800;
        margin: 3px 0;
        letter-spacing: -0.02em;
    }

    .hero-meta {
        font-size: 0.82rem;
        opacity: 0.92;
    }

    @media (max-width: 768px) {
        .block-container {
            max-width: 100%;
            padding-top: 0.8rem;
            padding-left: 0.78rem;
            padding-right: 0.78rem;
            padding-bottom: calc(6.8rem + env(safe-area-inset-bottom));
        }

        h1 {
            font-size: 1.42rem;
            margin-bottom: 0.32rem;
        }

        h2 {
            font-size: 1.08rem;
        }

        [data-testid="stExpander"] {
            border-radius: 16px;
        }

        [data-testid="stSidebar"] {
            width: 86vw !important;
        }

        .stButton > button {
            width: 100%;
            min-height: 46px;
        }

        .hero-card {
            border-radius: 16px;
            padding: 12px 13px;
        }

        .hero-value {
            font-size: 1.36rem;
        }
    }
    </style>
    """, unsafe_allow_html=True)

render_app_theme()

# ------------------------------
# 数据库连接
# ------------------------------
@st.cache_resource
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

conn = get_db_connection()
c = conn.cursor()

# ------------------------------
# 密码函数
# ------------------------------
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def is_legacy_hash(password_hash):
    if len(password_hash) != 64:
        return False
    return all(c in '0123456789abcdefABCDEF' for c in password_hash)

def verify_password(password, stored_hash):
    if is_legacy_hash(stored_hash):
        legacy_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        if legacy_hash == stored_hash:
            return True, True
        return False, False
    else:
        try:
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')), False
        except:
            return False, False

def sign_auth_payload(payload):
    return hmac.new(AUTH_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

def make_auth_token(username):
    ts = int(time.time())
    payload = f"{username}|{ts}"
    signature = sign_auth_payload(payload)
    return f"{payload}|{signature}"

def parse_auth_token(token):
    try:
        if not token:
            auth_log("token_parse_empty")
            return None
        username, ts_str, signature = token.split("|")
        if not username or "|" in username:
            auth_log("token_parse_bad_username")
            return None
        payload = f"{username}|{ts_str}"
        expected = sign_auth_payload(payload)
        if not hmac.compare_digest(signature, expected):
            auth_log("token_parse_bad_signature")
            return None
        ts = int(ts_str)
        if int(time.time()) - ts > AUTH_MAX_AGE_SECONDS:
            auth_log("token_parse_expired", username=username, token_ts=ts)
            return None
        auth_log("token_parse_ok", username=username)
        return username
    except Exception as e:
        auth_log("token_parse_error", error=str(e))
        return None

def b64url_encode(raw_bytes):
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("utf-8")

def b64url_decode(raw_str):
    if not raw_str:
        return b""
    padded = raw_str + "=" * ((4 - len(raw_str) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))

def get_query_value(key):
    value = None
    try:
        value = st.query_params.get(key)
    except:
        pass
    if value is None:
        try:
            qp = st.experimental_get_query_params()
            value = qp.get(key)
        except:
            value = None
    if isinstance(value, list):
        return value[0] if value else None
    return value

def set_query_value(key, value):
    try:
        st.query_params[key] = value
        return
    except:
        pass
    try:
        qp = st.experimental_get_query_params()
        qp[key] = [value]
        flattened = {}
        for k, v in qp.items():
            if isinstance(v, list):
                flattened[k] = v
            else:
                flattened[k] = [v]
        st.experimental_set_query_params(**flattened)
    except:
        pass

def clear_query_value(key):
    try:
        if key in st.query_params:
            del st.query_params[key]
        return
    except:
        pass
    try:
        qp = st.experimental_get_query_params()
        qp.pop(key, None)
        cleaned = {k: v for k, v in qp.items() if v}
        st.experimental_set_query_params(**cleaned)
    except:
        pass

def get_auth_token_from_query():
    return get_query_value("auth")

def set_auth_token_to_query(token):
    set_query_value("auth", token)

def clear_auth_token_from_query():
    clear_query_value("auth")

def render_client_auth_bridge(token_to_store=None, clear_client=False):
    safe_token = token_to_store or ""
    clear_flag = "true" if clear_client else "false"
    components.html(f"""
        <script>
        (function() {{
            try {{
                const storageKey = "investment_app_auth_token";
                const clearClient = {clear_flag};
                const tokenFromServer = {safe_token!r};
                const clientCookieKey = "{CLIENT_ID_COOKIE}";
                let hostWindow = window;
                if (window.parent && window.parent !== window) {{
                    hostWindow = window.parent;
                }}
                const cookieItems = hostWindow.document.cookie ? hostWindow.document.cookie.split(";") : [];
                const hasClientCookie = cookieItems.some((item) => item.trim().startsWith(clientCookieKey + "="));
                if (!hasClientCookie) {{
                    const randomPart = Math.random().toString(36).slice(2) + Date.now().toString(36);
                    const expireTime = new Date(Date.now() + 3650 * 24 * 60 * 60 * 1000).toUTCString();
                    hostWindow.document.cookie = `${{clientCookieKey}}=${{randomPart}}; path=/; expires=${{expireTime}}; SameSite=Lax`;
                }}
                const params = new URLSearchParams(hostWindow.location.search);
                const urlToken = params.get("auth");
                let localToken = hostWindow.localStorage.getItem(storageKey);

                if (clearClient) {{
                    hostWindow.localStorage.removeItem(storageKey);
                    localToken = null;
                    if (urlToken) {{
                        params.delete("auth");
                        const newQuery = params.toString();
                        const newUrl = hostWindow.location.pathname + (newQuery ? "?" + newQuery : "");
                        hostWindow.history.replaceState({{}}, "", newUrl);
                    }}
                }}

                if (tokenFromServer) {{
                    hostWindow.localStorage.setItem(storageKey, tokenFromServer);
                    localToken = tokenFromServer;
                }}

                if (!urlToken && localToken) {{
                    params.set("auth", localToken);
                    const newQuery = params.toString();
                    hostWindow.location.replace(hostWindow.location.pathname + "?" + newQuery);
                    return;
                }}

                if (urlToken && !localToken) {{
                    hostWindow.localStorage.setItem(storageKey, urlToken);
                }}
            }} catch (e) {{}}
        }})();
        </script>
    """, height=0)

def get_request_headers():
    headers = {}
    try:
        ctx = getattr(st, "context", None)
        if ctx is not None and hasattr(ctx, "headers"):
            headers = dict(ctx.headers)
    except Exception as e:
        auth_log("headers_read_error", error=str(e))
    return headers

def parse_cookie_header(cookie_raw):
    data = {}
    if not cookie_raw:
        return data
    for part in cookie_raw.split(";"):
        segment = part.strip()
        if "=" not in segment:
            continue
        k, v = segment.split("=", 1)
        data[k.strip()] = v.strip()
    return data

def is_mobile_client():
    headers = get_request_headers()
    ua = (headers.get("User-Agent", "") or headers.get("user-agent", "")).lower()
    mobile_tokens = ["iphone", "ipad", "ipod", "android", "mobile"]
    return any(token in ua for token in mobile_tokens)

def read_auth_logs(max_lines=160):
    if not os.path.exists(AUTH_LOG_PATH):
        return f"日志文件不存在：{AUTH_LOG_PATH}"
    try:
        with open(AUTH_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:]).strip()
    except Exception as e:
        return f"读取日志失败：{e}"

def render_auth_debug_panel(panel_key):
    with st.expander("🧪 登录调试日志", expanded=False):
        st.caption(f"日志文件：{AUTH_LOG_PATH}")
        col_a, col_b = st.columns(2)
        if col_a.button("刷新日志", key=f"auth_log_refresh_{panel_key}"):
            st.rerun()
        if col_b.button("清空日志", key=f"auth_log_clear_{panel_key}"):
            try:
                with open(AUTH_LOG_PATH, "w", encoding="utf-8"):
                    pass
                auth_log("log_cleared")
            except Exception as e:
                st.error(f"清空失败：{e}")
            st.rerun()
        st.code(read_auth_logs(), language="text")

# ------------------------------
# 数据库初始化
# ------------------------------
def init_database():
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investor TEXT,
            market TEXT,
            symbol_code TEXT,
            symbol_name TEXT,
            channel TEXT,
            cost_price REAL,
            quantity REAL,
            update_time TEXT,
            user TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL,
            shared_with TEXT NOT NULL,
            permission TEXT NOT NULL DEFAULT 'read',
            created_at TEXT,
            UNIQUE(owner, shared_with)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS symbol_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            symbol_code TEXT NOT NULL,
            symbol_name TEXT NOT NULL,
            source TEXT,
            updated_at TEXT,
            UNIQUE(market, symbol_code)
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_symbol_cache_code ON symbol_cache(symbol_code)
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_symbol_cache_name ON symbol_cache(symbol_name)
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT,
            updated_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            operator TEXT NOT NULL,
            owner TEXT,
            changed_fields TEXT,
            before_data TEXT,
            after_data TEXT,
            action_time TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS login_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_key TEXT UNIQUE NOT NULL,
            username TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            updated_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_passkeys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            credential_id TEXT UNIQUE NOT NULL,
            public_key TEXT NOT NULL,
            sign_count INTEGER NOT NULL DEFAULT 0,
            transports TEXT,
            created_at TEXT,
            last_used_at TEXT
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_passkeys_username ON user_passkeys(username)
    """)
    conn.commit()

    c.execute("PRAGMA table_info(investments)")
    cols = [row[1] for row in c.fetchall()]
    if "user" not in cols:
        c.execute("ALTER TABLE investments ADD COLUMN user TEXT")
        conn.commit()

    c.execute("PRAGMA table_info(shares)")
    share_cols = [row[1] for row in c.fetchall()]
    if "permission" not in share_cols:
        c.execute("ALTER TABLE shares ADD COLUMN permission TEXT NOT NULL DEFAULT 'read'")
        conn.commit()
    c.execute("UPDATE shares SET permission='read' WHERE permission IS NULL OR TRIM(permission)=''")
    conn.commit()

    c.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if c.fetchone()[0] == 0:
        hashed = hash_password("admin123")
        c.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                  ("admin", hashed, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        st.toast("✅ 默认管理员账号已创建：**admin / admin123**", icon="🎉")

init_database()

# ------------------------------
# 持久登录会话（不依赖 URL 参数）
# ------------------------------
def get_client_keys():
    headers = get_request_headers()
    cookie_raw = headers.get("Cookie", "") or headers.get("cookie", "")
    cookie_map = parse_cookie_header(cookie_raw)
    custom_cookie = cookie_map.get(CLIENT_ID_COOKIE, "")
    ua = headers.get("User-Agent", "") or headers.get("user-agent", "")
    al = headers.get("Accept-Language", "") or headers.get("accept-language", "")
    xff = headers.get("X-Forwarded-For", "") or headers.get("x-forwarded-for", "")
    keys = []
    sources = []

    if custom_cookie:
        cid_key = hashlib.sha256(f"cid:{custom_cookie}".encode("utf-8")).hexdigest()
        keys.append(cid_key)
        sources.append("custom_cookie")

    if ua or al or xff:
        fp_key = hashlib.sha256(f"ua:{ua}|al:{al}|xff:{xff}".encode("utf-8")).hexdigest()
        if fp_key not in keys:
            keys.append(fp_key)
            sources.append("header_fingerprint")

    if not keys:
        auth_log("client_key_missing", has_headers=bool(headers), has_cookie=bool(cookie_raw))
        return []

    auth_log(
        "client_keys_ready",
        sources=",".join(sources),
        key_prefixes=",".join([k[:12] for k in keys]),
        has_custom_cookie=bool(custom_cookie),
        has_cookie=bool(cookie_raw),
        ua_len=len(ua),
        al_len=len(al),
        xff_len=len(xff),
    )
    return keys

def upsert_login_session(username):
    client_keys = get_client_keys()
    if not client_keys:
        auth_log("session_upsert_skip_no_client_key", username=username)
        return
    expires_at = int(time.time()) + AUTH_MAX_AGE_SECONDS
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for client_key in client_keys:
        c.execute("""
            INSERT INTO login_sessions (client_key, username, expires_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(client_key) DO UPDATE SET
                username=excluded.username,
                expires_at=excluded.expires_at,
                updated_at=excluded.updated_at
        """, (client_key, username, expires_at, now_str))
    conn.commit()
    auth_log("session_upsert_ok", username=username, key_prefixes=",".join([k[:12] for k in client_keys]), expires_at=expires_at)

def clear_login_session():
    client_keys = get_client_keys()
    if not client_keys:
        auth_log("session_clear_skip_no_client_key")
        return
    placeholders = ",".join(["?"] * len(client_keys))
    c.execute(f"DELETE FROM login_sessions WHERE client_key IN ({placeholders})", client_keys)
    conn.commit()
    auth_log("session_clear_ok", key_prefixes=",".join([k[:12] for k in client_keys]))

def restore_login_session():
    client_keys = get_client_keys()
    if not client_keys:
        auth_log("session_restore_no_client_key")
        return None
    now_ts = int(time.time())
    c.execute("DELETE FROM login_sessions WHERE expires_at < ?", (now_ts,))
    placeholders = ",".join(["?"] * len(client_keys))
    c.execute(
        f"SELECT username, client_key FROM login_sessions WHERE client_key IN ({placeholders}) AND expires_at>=? ORDER BY updated_at DESC LIMIT 1",
        client_keys + [now_ts]
    )
    row = c.fetchone()
    if not row:
        conn.commit()
        auth_log("session_restore_miss", key_prefixes=",".join([k[:12] for k in client_keys]))
        return None
    username, hit_key = row
    c.execute("SELECT 1 FROM users WHERE username=?", (username,))
    user_exists = c.fetchone() is not None
    if user_exists:
        new_exp = int(time.time()) + AUTH_MAX_AGE_SECONDS
        for client_key in client_keys:
            c.execute(
                "UPDATE login_sessions SET username=?, expires_at=?, updated_at=? WHERE client_key=?",
                (username, new_exp, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), client_key),
            )
    conn.commit()
    auth_log("session_restore_hit" if user_exists else "session_restore_user_missing",
             username=username, hit_key_prefix=hit_key[:12], all_key_prefixes=",".join([k[:12] for k in client_keys]))
    return username if user_exists else None

def get_webauthn_context():
    headers = get_request_headers()
    host = headers.get("Host", "") or headers.get("host", "")
    proto = headers.get("X-Forwarded-Proto", "") or headers.get("x-forwarded-proto", "")
    forwarded = headers.get("Forwarded", "") or headers.get("forwarded", "")

    if "," in host:
        host = host.split(",")[0].strip()
    if "," in proto:
        proto = proto.split(",")[0].strip()
    if not proto and forwarded:
        segments = [x.strip() for x in forwarded.split(";")]
        for segment in segments:
            if segment.lower().startswith("proto="):
                proto = segment.split("=", 1)[1].strip().strip('"').lower()
                break

    host_name = host.split(":")[0] if host else ""
    if not proto:
        if host_name.endswith(".streamlit.app"):
            proto = "https"
        elif host_name in ("localhost", "127.0.0.1"):
            proto = "http"
        else:
            proto = "https"

    rp_id = WEBAUTHN_RP_ID or host_name
    origin = WEBAUTHN_ORIGIN or (f"{proto}://{host}" if host else "")
    return rp_id, origin

def is_secure_webauthn_origin(origin):
    if not origin:
        return False
    return (
        origin.startswith("https://")
        or origin.startswith("http://localhost")
        or origin.startswith("http://127.0.0.1")
    )

def list_user_passkeys(username):
    c.execute(
        """
        SELECT id, credential_id, sign_count, transports, created_at, last_used_at
        FROM user_passkeys
        WHERE username=?
        ORDER BY id DESC
        """,
        (username,),
    )
    rows = []
    for row in c.fetchall():
        rows.append(
            {
                "id": row[0],
                "credential_id": row[1],
                "sign_count": row[2],
                "transports": row[3] or "[]",
                "created_at": row[4],
                "last_used_at": row[5],
            }
        )
    return rows

def get_passkey_by_credential_id(credential_id):
    c.execute(
        """
        SELECT id, username, credential_id, public_key, sign_count
        FROM user_passkeys
        WHERE credential_id=?
        """,
        (credential_id,),
    )
    row = c.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "username": row[1],
        "credential_id": row[2],
        "public_key": row[3],
        "sign_count": int(row[4] or 0),
    }

def upsert_user_passkey(username, credential_id, public_key, sign_count, transports):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        """
        INSERT INTO user_passkeys (username, credential_id, public_key, sign_count, transports, created_at, last_used_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(credential_id) DO UPDATE SET
            username=excluded.username,
            public_key=excluded.public_key,
            sign_count=excluded.sign_count,
            transports=excluded.transports
        """,
        (
            username,
            credential_id,
            public_key,
            int(sign_count or 0),
            json.dumps(transports or [], ensure_ascii=False),
            now_str,
            now_str,
        ),
    )
    conn.commit()

def update_passkey_sign_count(credential_id, sign_count):
    c.execute(
        """
        UPDATE user_passkeys
        SET sign_count=?, last_used_at=?
        WHERE credential_id=?
        """,
        (int(sign_count or 0), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), credential_id),
    )
    conn.commit()

def delete_user_passkey(username, passkey_id):
    c.execute("DELETE FROM user_passkeys WHERE id=? AND username=?", (passkey_id, username))
    conn.commit()

def create_login_state(username):
    token = make_auth_token(username)
    st.session_state.logged_in = True
    st.session_state.username = username
    st.session_state.pending_auth_token = token
    st.session_state.clear_auth_client = False
    set_auth_token_to_query(token)
    upsert_login_session(username)

def start_passkey_registration(username):
    if not WEBAUTHN_AVAILABLE:
        return False, f"未安装 webauthn 依赖：{WEBAUTHN_IMPORT_ERROR}"

    rp_id, origin = get_webauthn_context()
    if not rp_id or not origin:
        return False, "无法识别当前域名，请配置 WEBAUTHN_RP_ID / WEBAUTHN_ORIGIN。"
    if not is_secure_webauthn_origin(origin):
        return False, "Passkey 需要 HTTPS 域名（或 localhost）。请改用 HTTPS 访问。"

    user_id = hashlib.sha256(f"user:{username}".encode("utf-8")).digest()
    try:
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name=WEBAUTHN_RP_NAME,
            user_id=user_id,
            user_name=username,
            user_display_name=username,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
    except TypeError:
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name=WEBAUTHN_RP_NAME,
            user_id=user_id,
            user_name=username,
            user_display_name=username,
        )
    options_payload = json.loads(options_to_json(options))
    challenge = options_payload.get("challenge")
    if not challenge:
        return False, "生成 Passkey 注册挑战失败"

    st.session_state.passkey_registration_state = {
        "username": username,
        "rp_id": rp_id,
        "origin": origin,
        "challenge": challenge,
        "created_at": int(time.time()),
    }
    set_query_value(PASSKEY_STATE_QUERY_KEY, make_passkey_state_token({
        "mode": "register",
        "username": username,
        "rp_id": rp_id,
        "origin": origin,
        "challenge": challenge,
        "created_at": int(time.time()),
    }))
    st.session_state.passkey_pending_action = {
        "mode": "register",
        "options": options_payload,
    }
    auth_log("passkey_register_begin", username=username, rp_id=rp_id, origin=origin)
    return True, "请在系统弹窗中完成 Face ID 注册。"

def start_passkey_authentication():
    if not WEBAUTHN_AVAILABLE:
        return False, f"未安装 webauthn 依赖：{WEBAUTHN_IMPORT_ERROR}"

    rp_id, origin = get_webauthn_context()
    if not rp_id or not origin:
        return False, "无法识别当前域名，请配置 WEBAUTHN_RP_ID / WEBAUTHN_ORIGIN。"
    if not is_secure_webauthn_origin(origin):
        return False, "Passkey 需要 HTTPS 域名（或 localhost）。请改用 HTTPS 访问。"

    try:
        options = generate_authentication_options(
            rp_id=rp_id,
            user_verification=UserVerificationRequirement.REQUIRED,
        )
    except TypeError:
        options = generate_authentication_options(rp_id=rp_id)
    options_payload = json.loads(options_to_json(options))
    challenge = options_payload.get("challenge")
    if not challenge:
        return False, "生成 Passkey 登录挑战失败"

    st.session_state.passkey_auth_state = {
        "rp_id": rp_id,
        "origin": origin,
        "challenge": challenge,
        "created_at": int(time.time()),
    }
    set_query_value(PASSKEY_STATE_QUERY_KEY, make_passkey_state_token({
        "mode": "authenticate",
        "rp_id": rp_id,
        "origin": origin,
        "challenge": challenge,
        "created_at": int(time.time()),
    }))
    st.session_state.passkey_pending_action = {
        "mode": "authenticate",
        "options": options_payload,
    }
    auth_log("passkey_auth_begin", rp_id=rp_id, origin=origin)
    return True, "请在系统弹窗中完成 Face ID 验证。"

def consume_passkey_query_result():
    encoded = get_query_value(PASSKEY_RESULT_QUERY_KEY)
    if not encoded:
        return None
    clear_query_value(PASSKEY_RESULT_QUERY_KEY)
    try:
        raw_json = b64url_decode(encoded).decode("utf-8")
        return json.loads(raw_json)
    except Exception as e:
        auth_log("passkey_query_decode_error", error=str(e))
        st.error("Face ID 回调数据解析失败，请重试。")
        return None

def make_passkey_state_token(state_dict):
    payload_json = json.dumps(state_dict, separators=(",", ":"), ensure_ascii=False)
    payload = b64url_encode(payload_json.encode("utf-8"))
    signature = sign_auth_payload(f"passkey|{payload}")
    return f"{payload}.{signature}"

def parse_passkey_state_token(token):
    try:
        if not token or "." not in token:
            return None
        payload, signature = token.rsplit(".", 1)
        expected = sign_auth_payload(f"passkey|{payload}")
        if not hmac.compare_digest(signature, expected):
            auth_log("passkey_state_bad_signature")
            return None
        raw = b64url_decode(payload).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return data
    except Exception as e:
        auth_log("passkey_state_parse_error", error=str(e))
        return None

def get_passkey_state_for_mode(mode):
    token = get_query_value(PASSKEY_STATE_QUERY_KEY)
    state = parse_passkey_state_token(token)
    if not state:
        return None
    if state.get("mode") != mode:
        return None
    return state

def clear_passkey_state():
    clear_query_value(PASSKEY_STATE_QUERY_KEY)
    st.session_state.passkey_registration_state = None
    st.session_state.passkey_auth_state = None

def challenge_is_expired(state):
    if not state:
        return True
    created_at = int(state.get("created_at") or 0)
    return int(time.time()) - created_at > PASSKEY_CHALLENGE_TTL_SECONDS

def finalize_passkey_registration(payload):
    state = st.session_state.passkey_registration_state
    if not state:
        state = get_passkey_state_for_mode("register")
    clear_passkey_state()

    if not state:
        return False, "Face ID 注册会话不存在，请重新点击“启用 Face ID”。"
    if challenge_is_expired(state):
        return False, "Face ID 注册已超时，请重试。"

    try:
        verification = verify_registration_response(
            credential=payload,
            expected_challenge=b64url_decode(state["challenge"]),
            expected_origin=state["origin"],
            expected_rp_id=state["rp_id"],
            require_user_verification=True,
        )
        credential_id_raw = getattr(verification, "credential_id")
        public_key_raw = getattr(verification, "credential_public_key")
        sign_count = int(getattr(verification, "sign_count", 0) or 0)

        credential_id = credential_id_raw if isinstance(credential_id_raw, str) else b64url_encode(credential_id_raw)
        public_key = public_key_raw if isinstance(public_key_raw, str) else b64url_encode(public_key_raw)
        transports = payload.get("response", {}).get("transports", [])

        upsert_user_passkey(state["username"], credential_id, public_key, sign_count, transports)
        auth_log("passkey_register_ok", username=state["username"], credential_prefix=credential_id[:12])
        return True, "Face ID 已启用，下次可直接刷脸登录。"
    except Exception as e:
        auth_log("passkey_register_failed", error=str(e))
        return False, f"Face ID 注册失败：{e}"

def finalize_passkey_authentication(payload):
    state = st.session_state.passkey_auth_state
    if not state:
        state = get_passkey_state_for_mode("authenticate")
    clear_passkey_state()

    if not state:
        return False, "Face ID 登录会话不存在，请重试。", None
    if challenge_is_expired(state):
        return False, "Face ID 登录已超时，请重试。", None

    credential_id = payload.get("id") or payload.get("rawId")
    passkey = get_passkey_by_credential_id(credential_id)
    if not passkey and payload.get("rawId"):
        passkey = get_passkey_by_credential_id(payload.get("rawId"))
        credential_id = payload.get("rawId")
    if not passkey:
        return False, "未找到该设备的 Passkey，请先用密码登录并启用 Face ID。", None

    try:
        verification = verify_authentication_response(
            credential=payload,
            expected_challenge=b64url_decode(state["challenge"]),
            expected_origin=state["origin"],
            expected_rp_id=state["rp_id"],
            credential_public_key=b64url_decode(passkey["public_key"]),
            credential_current_sign_count=int(passkey["sign_count"]),
            require_user_verification=True,
        )
        new_sign_count = int(getattr(verification, "new_sign_count", passkey["sign_count"]) or 0)
        update_passkey_sign_count(credential_id, new_sign_count)
        auth_log("passkey_auth_ok", username=passkey["username"], credential_prefix=credential_id[:12])
        return True, "Face ID 登录成功。", passkey["username"]
    except Exception as e:
        auth_log("passkey_auth_failed", error=str(e))
        return False, f"Face ID 登录失败：{e}", None

def handle_passkey_query_result():
    result = consume_passkey_query_result()
    if not result:
        return

    mode = result.get("mode")
    ok = bool(result.get("ok"))
    if not ok:
        error_msg = result.get("error") or "未知错误"
        clear_passkey_state()
        auth_log("passkey_client_error", mode=mode, error=error_msg)
        st.error(f"Face ID 操作失败：{error_msg}")
        return

    payload = result.get("payload") or {}
    if mode == "register":
        success, message = finalize_passkey_registration(payload)
        if success:
            st.success(message)
        else:
            st.error(message)
        return

    if mode == "authenticate":
        success, message, username = finalize_passkey_authentication(payload)
        if not success:
            st.error(message)
            return
        create_login_state(username)
        st.toast("✅ Face ID 登录成功", icon="✅")
        st.rerun()

def render_pending_passkey_action():
    action = st.session_state.passkey_pending_action
    if not action:
        return
    st.session_state.passkey_pending_action = None

    mode = action.get("mode")
    options = action.get("options") or {}
    query_key = PASSKEY_RESULT_QUERY_KEY
    payload_json = json.dumps(options, ensure_ascii=False)

    components.html(
        f"""
        <div style="padding: 8px 0;">
          <button id="passkey-trigger-btn" style="width:100%;padding:10px 12px;border:0;border-radius:8px;background:#0f766e;color:#fff;font-weight:600;">
            继续 Face ID 验证
          </button>
          <div id="passkey-status" style="margin-top:8px;font-size:13px;color:#475569;">
            请点击上方按钮后进行 Face ID。
          </div>
        </div>
        <script>
        (function() {{
            const mode = {json.dumps(mode)};
            const options = {payload_json};
            const queryKey = {json.dumps(query_key)};
            const triggerBtn = document.getElementById("passkey-trigger-btn");
            const statusEl = document.getElementById("passkey-status");

            function setStatus(text, isError) {{
                if (!statusEl) return;
                statusEl.textContent = text;
                statusEl.style.color = isError ? "#b91c1c" : "#475569";
            }}

            function toBytes(value) {{
                if (value instanceof Uint8Array) return value;
                if (value instanceof ArrayBuffer) return new Uint8Array(value);
                if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
                return new Uint8Array();
            }}

            function encodeBase64Url(value) {{
                const bytes = toBytes(value);
                let binary = "";
                for (let i = 0; i < bytes.length; i += 1) {{
                    binary += String.fromCharCode(bytes[i]);
                }}
                return btoa(binary).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/g, "");
            }}

            function decodeBase64Url(value) {{
                const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
                const base64 = padded.replace(/-/g, "+").replace(/_/g, "/");
                const binary = atob(base64);
                const bytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i += 1) {{
                    bytes[i] = binary.charCodeAt(i);
                }}
                return bytes.buffer;
            }}

            function encodeJson(obj) {{
                return encodeBase64Url(new TextEncoder().encode(JSON.stringify(obj)));
            }}

            function normalizeCreateOptions(raw) {{
                const next = {{ ...raw }};
                next.challenge = decodeBase64Url(next.challenge);
                if (next.user && next.user.id) {{
                    next.user = {{ ...next.user, id: decodeBase64Url(next.user.id) }};
                }}
                if (Array.isArray(next.excludeCredentials)) {{
                    next.excludeCredentials = next.excludeCredentials.map((item) => ({{ ...item, id: decodeBase64Url(item.id) }}));
                }}
                return next;
            }}

            function normalizeGetOptions(raw) {{
                const next = {{ ...raw }};
                next.challenge = decodeBase64Url(next.challenge);
                if (Array.isArray(next.allowCredentials)) {{
                    next.allowCredentials = next.allowCredentials.map((item) => ({{ ...item, id: decodeBase64Url(item.id) }}));
                }}
                return next;
            }}

            function serializeRegistrationCredential(credential) {{
                const response = credential.response;
                return {{
                    id: credential.id,
                    rawId: encodeBase64Url(credential.rawId),
                    type: credential.type,
                    response: {{
                        clientDataJSON: encodeBase64Url(response.clientDataJSON),
                        attestationObject: encodeBase64Url(response.attestationObject),
                        transports: typeof response.getTransports === "function" ? response.getTransports() : [],
                    }},
                    clientExtensionResults: typeof credential.getClientExtensionResults === "function"
                        ? credential.getClientExtensionResults()
                        : {{}},
                }};
            }}

            function serializeAuthenticationCredential(credential) {{
                const response = credential.response;
                return {{
                    id: credential.id,
                    rawId: encodeBase64Url(credential.rawId),
                    type: credential.type,
                    response: {{
                        authenticatorData: encodeBase64Url(response.authenticatorData),
                        clientDataJSON: encodeBase64Url(response.clientDataJSON),
                        signature: encodeBase64Url(response.signature),
                        userHandle: response.userHandle ? encodeBase64Url(response.userHandle) : null,
                    }},
                    clientExtensionResults: typeof credential.getClientExtensionResults === "function"
                        ? credential.getClientExtensionResults()
                        : {{}},
                }};
            }}

            function sendResult(result) {{
                let hostWindow = window;
                if (window.parent && window.parent !== window) {{
                    hostWindow = window.parent;
                }}
                const url = new URL(hostWindow.location.href);
                url.searchParams.set(queryKey, encodeJson(result));
                hostWindow.location.replace(url.toString());
            }}

            async function runPasskey() {{
                if (!window.PublicKeyCredential) {{
                    sendResult({{ mode, ok: false, error: "当前浏览器不支持 Passkey/Face ID" }});
                    return;
                }}
                try {{
                    if (window.parent && window.parent !== window && typeof window.parent.focus === "function") {{
                        window.parent.focus();
                    }}
                    if (typeof window.focus === "function") {{
                        window.focus();
                    }}
                    if (!document.hasFocus()) {{
                        throw new Error("页面未获得焦点，请点一下页面后重试");
                    }}

                    if (mode === "register") {{
                        const credential = await navigator.credentials.create({{
                            publicKey: normalizeCreateOptions(options),
                        }});
                        sendResult({{
                            mode,
                            ok: true,
                            payload: serializeRegistrationCredential(credential),
                        }});
                        return;
                    }}
                    const credential = await navigator.credentials.get({{
                        publicKey: normalizeGetOptions(options),
                    }});
                    sendResult({{
                        mode,
                        ok: true,
                        payload: serializeAuthenticationCredential(credential),
                    }});
                }} catch (error) {{
                    sendResult({{
                        mode,
                        ok: false,
                        error: error && error.message ? error.message : String(error),
                    }});
                }}
            }}

            if (!triggerBtn) {{
                setStatus("无法渲染 Face ID 按钮，请刷新页面重试。", true);
                return;
            }}
            triggerBtn.addEventListener("click", () => {{
                triggerBtn.disabled = true;
                triggerBtn.style.opacity = "0.7";
                setStatus("正在请求 Face ID，请在系统弹窗中确认...", false);
                runPasskey();
            }});
            setTimeout(() => {{
                try {{
                    triggerBtn.focus();
                }} catch (e) {{}}
            }}, 50);
        }})();
        </script>
        """,
        height=120,
    )

# ------------------------------
# 刷新后自动恢复登录
# ------------------------------
auth_log("app_run", logged_in=st.session_state.logged_in, username=st.session_state.username)

render_client_auth_bridge(
    token_to_store=st.session_state.pending_auth_token,
    clear_client=st.session_state.clear_auth_client,
)
if st.session_state.pending_auth_token:
    auth_log("bridge_store_token", username=st.session_state.username)
    st.session_state.pending_auth_token = None
if st.session_state.clear_auth_client:
    auth_log("bridge_clear_client_done")
    st.session_state.clear_auth_client = False

handle_passkey_query_result()

if not st.session_state.logged_in:
    restored_user = restore_login_session()
    if not restored_user:
        auth_token = get_auth_token_from_query()
        auth_log("restore_from_query", has_auth_token=bool(auth_token))
        if auth_token:
            restored_user = parse_auth_token(auth_token)
            if restored_user:
                c.execute("SELECT 1 FROM users WHERE username=?", (restored_user,))
                if c.fetchone():
                    upsert_login_session(restored_user)
                    auth_log("restore_from_query_ok", username=restored_user)
                else:
                    auth_log("restore_from_query_user_missing", username=restored_user)
                    restored_user = None
            else:
                auth_log("restore_from_query_invalid_token")
                st.session_state.clear_auth_client = True
                clear_auth_token_from_query()
                render_client_auth_bridge(clear_client=True)
    if restored_user:
        st.session_state.logged_in = True
        st.session_state.username = restored_user
        auth_log("restore_login_ok", username=restored_user)

render_pending_passkey_action()

# ------------------------------
# 用户注册/登录
# ------------------------------
def register_user(username, password):
    try:
        hashed = hash_password(password)
        c.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                  (username, hashed, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        return True, "注册成功！"
    except sqlite3.IntegrityError:
        return False, "用户名已存在"

def login_user(username, password):
    c.execute("SELECT password_hash FROM users WHERE username=?", (username,))
    row = c.fetchone()
    if not row:
        return False
    stored_hash = row[0]
    is_valid, needs_upgrade = verify_password(password, stored_hash)
    if is_valid and needs_upgrade:
        new_hash = hash_password(password)
        c.execute("UPDATE users SET password_hash=? WHERE username=?", (new_hash, username))
        conn.commit()
        st.toast("🔒 密码已自动升级为 bcrypt 加密", icon="✅")
    return is_valid

# ------------------------------
# 共享功能
# ------------------------------
def normalize_share_permission(permission):
    return "edit" if permission == "edit" else "read"

def permission_label(permission):
    return "可编辑" if permission == "edit" else "只读"

def invite_user(owner, shared_with, permission="read"):
    if owner == shared_with:
        return False, "不能邀请自己"
    permission = normalize_share_permission(permission)
    c.execute("SELECT 1 FROM users WHERE username=?", (shared_with,))
    if not c.fetchone():
        return False, "用户不存在"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("SELECT permission FROM shares WHERE owner=? AND shared_with=?", (owner, shared_with))
    existed = c.fetchone()
    c.execute("""
        INSERT INTO shares (owner, shared_with, permission, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(owner, shared_with) DO UPDATE SET
            permission=excluded.permission,
            created_at=excluded.created_at
    """, (owner, shared_with, permission, now_str))
    conn.commit()
    if existed:
        return True, f"✅ 已更新 {shared_with} 权限为「{permission_label(permission)}」"
    return True, f"✅ 已邀请 {shared_with}（{permission_label(permission)}）"

def revoke_share(owner, shared_with):
    c.execute("DELETE FROM shares WHERE owner=? AND shared_with=?", (owner, shared_with))
    conn.commit()

def update_share_permission(owner, shared_with, permission):
    permission = normalize_share_permission(permission)
    c.execute("""
        UPDATE shares
        SET permission=?
        WHERE owner=? AND shared_with=?
    """, (permission, owner, shared_with))
    conn.commit()

def get_share_permission_map(shared_with):
    c.execute("SELECT owner, permission FROM shares WHERE shared_with=?", (shared_with,))
    data = {}
    for owner, permission in c.fetchall():
        data[owner] = normalize_share_permission(permission)
    return data

def can_edit_owner_data(owner, actor):
    if owner == actor:
        return True
    if not owner:
        return False
    c.execute("SELECT permission FROM shares WHERE owner=? AND shared_with=?", (owner, actor))
    row = c.fetchone()
    if not row:
        return False
    return normalize_share_permission(row[0]) == "edit"

def get_shared_owners(current_user):
    return list(get_share_permission_map(current_user).keys())

def get_my_invited_users(owner):
    c.execute("SELECT shared_with, permission FROM shares WHERE owner=? ORDER BY shared_with", (owner,))
    return [{"shared_with": row[0], "permission": normalize_share_permission(row[1])} for row in c.fetchall()]

# ------------------------------
# 登录/注册页面 或 主界面
# ------------------------------
is_mobile_view = is_mobile_client()

if not st.session_state.logged_in:
    if is_mobile_view:
        st.markdown("""
        <div class="hero-card">
          <div class="hero-title">欢迎回来</div>
          <div class="hero-value">资产掌控</div>
          <div class="hero-meta">支持密码登录与 Face ID 快速验证</div>
        </div>
        """, unsafe_allow_html=True)
        st.caption("📱 iPhone 触控优化模式已启用")
    st.subheader("🔐 请先登录或注册")
    tab1, tab2 = st.tabs(["📥 登录", "📝 注册"])

    with tab1:
        with st.form("login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            if st.form_submit_button("🚀 登录", type="primary"):
                if login_user(username, password):
                    create_login_state(username)
                    auth_log("login_ok", username=username)
                    st.success(f"欢迎回来，{username}！")
                    st.rerun()
                else:
                    auth_log("login_failed", username=username)
                    st.error("用户名或密码错误")

        st.divider()
        st.caption("📱 iPhone 可直接用 Face ID 登录（先用密码登录一次后启用）")
        if st.button("使用 Face ID 登录", key="passkey_auth_button", type="primary"):
            ok, msg = start_passkey_authentication()
            if ok:
                st.info(msg)
                st.rerun()
            else:
                st.error(msg)

    with tab2:
        with st.form("register_form"):
            new_username = st.text_input("新用户名")
            new_password = st.text_input("新密码", type="password")
            if st.form_submit_button("注册账号", type="primary"):
                if new_username and new_password:
                    success, msg = register_user(new_username, new_password)
                    if success:
                        st.success(msg + " 请立即登录")
                    else:
                        st.error(msg)
                else:
                    st.warning("请填写完整信息")

    render_auth_debug_panel("login_page")

else:
    current_user = st.session_state.username

    # ------------------------------
    # 侧边栏
    # ------------------------------
    with st.sidebar:
        st.success(f"👤 当前用户：**{current_user}**")
        if st.button("🚪 登出"):
            auth_log("logout", username=current_user)
            st.session_state.logged_in = False
            st.session_state.username = None
            st.session_state.pending_auth_token = None
            st.session_state.clear_auth_client = True
            st.session_state.passkey_pending_action = None
            clear_passkey_state()
            clear_auth_token_from_query()
            clear_login_session()
            st.rerun()

        st.divider()
        with st.expander("🔐 Face ID 登录", expanded=False):
            if WEBAUTHN_AVAILABLE:
                st.caption("在这台设备启用后，可在登录页直接刷脸进入。")
                if st.button("在当前设备启用 Face ID", key="passkey_register_btn", type="primary"):
                    ok, msg = start_passkey_registration(current_user)
                    if ok:
                        st.info(msg)
                        st.rerun()
                    else:
                        st.error(msg)

                passkeys = list_user_passkeys(current_user)
                st.caption(f"已绑定 Passkey 数量：{len(passkeys)}")
                for item in passkeys:
                    short_id = item["credential_id"][:16] + "..."
                    st.write(f"设备凭证：`{short_id}`")
                    created_at = item["created_at"] or "-"
                    last_used_at = item["last_used_at"] or "-"
                    st.caption(f"创建时间：{created_at} | 最近使用：{last_used_at}")
                    if st.button("删除此凭证", key=f"delete_passkey_{item['id']}"):
                        delete_user_passkey(current_user, item["id"])
                        st.success("已删除该 Face ID 凭证")
                        st.rerun()
                    st.divider()
            else:
                st.error(f"缺少 webauthn 依赖：{WEBAUTHN_IMPORT_ERROR}")
                st.caption("先安装依赖后即可启用 Face ID：`pip install webauthn`")

        st.subheader("🔗 共享管理")
        invited = get_my_invited_users(current_user)
        if invited:
            st.caption("我邀请的用户：")
            for item in invited:
                invited_user = item["shared_with"]
                current_perm = item["permission"]
                col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                col1.write(f"• {invited_user}")
                new_perm = col2.selectbox(
                    "权限",
                    ["read", "edit"],
                    index=0 if current_perm == "read" else 1,
                    format_func=permission_label,
                    key=f"share_perm_{invited_user}",
                    label_visibility="collapsed"
                )
                if col3.button("保存", key=f"save_perm_{invited_user}"):
                    update_share_permission(current_user, invited_user, new_perm)
                    st.success(f"已更新 {invited_user} 为「{permission_label(new_perm)}」")
                    st.rerun()
                if col4.button("撤销", key=f"revoke_{invited_user}"):
                    revoke_share(current_user, invited_user)
                    st.rerun()
        else:
            st.caption("暂无邀请用户")

        with st.expander("邀请新用户"):
            invite_username = st.text_input("对方用户名", key="invite_input")
            invite_permission = st.selectbox(
                "授权权限",
                ["read", "edit"],
                format_func=permission_label,
                key="invite_permission"
            )
            if st.button("发送邀请", type="primary", key="invite_btn"):
                if invite_username:
                    success, msg = invite_user(current_user, invite_username, invite_permission)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("请输入用户名")

        shared_permission_map = get_share_permission_map(current_user)
        if shared_permission_map:
            st.caption("共享给我的人：")
            shared_text = [f"{owner}（{permission_label(shared_permission_map[owner])}）" for owner in sorted(shared_permission_map.keys())]
            st.write("，".join(shared_text))

        render_auth_debug_panel("sidebar")

    # ------------------------------
    # 市场识别 & 行情函数（完整保留）
    # ------------------------------
    def identify_market(code):
        code = str(code).upper()
        if "USDT" in code or code in ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]:
            return "Crypto"
        if code.isdigit() and len(code) == 6:
            return "A股"
        return "美股"

    @st.cache_data(ttl=3600)
    def get_a_stock_name(code):
        try:
            secid = ("1." if code.startswith(("6", "5", "9")) else "0.") + code
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            r = requests.get(url, params={"secid": secid, "fields": "f58"}, timeout=3)
            return r.json()["data"]["f58"]
        except:
            return code

    @st.cache_data(ttl=3600)
    def get_fund_name(code):
        try:
            url = f"https://fundgz.1234567.com.cn/js/{code}.js"
            r = requests.get(url, timeout=3)
            text = r.text
            if "jsonpgz" in text:
                json_str = text[text.find("{"):text.rfind("}") + 1]
                data = eval(json_str)
                return data["name"]
        except:
            return code

    @st.cache_data(ttl=3600)
    def get_us_stock_name(code):
        try:
            ticker = yf.Ticker(code)
            return ticker.info.get("shortName", code)
        except:
            return code

    def get_symbol_name(market, code):
        cached_name = get_cached_symbol_name(market, code)
        if cached_name:
            return cached_name

        if market == "A股":
            name = get_a_stock_name(code)
            if name == code:
                name = get_fund_name(code)
            if name and name != code:
                upsert_symbol_cache([(market, code, name)], source="realtime_a_share")
            return name
        if market == "美股":
            name = get_us_stock_name(code)
            if name and name != code:
                upsert_symbol_cache([(market, code, name)], source="realtime_us")
            return name
        if market == "Crypto":
            upsert_symbol_cache([(market, code, code)], source="realtime_crypto")
        return code

    @st.cache_data(ttl=30)
    def get_a_stock_price(code):
        try:
            secid = ("1." if code.startswith(("6", "5", "9")) else "0.") + code
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            r = requests.get(url, params={"secid": secid, "fields": "f43"}, timeout=3)
            return r.json()["data"]["f43"] / 100
        except:
            return 0

    @st.cache_data(ttl=60)
    def get_fund_nav(code):
        try:
            url = f"https://fundgz.1234567.com.cn/js/{code}.js"
            r = requests.get(url, timeout=3)
            text = r.text
            if "jsonpgz" in text:
                json_str = text[text.find("{"):text.rfind("}") + 1]
                data = eval(json_str)
                return float(data["gsz"])
        except:
            pass
        return 0

    @st.cache_data(ttl=30)
    def get_us_stock_batch_prices(codes):
        if not codes:
            return {}
        prices = {}
        try:
            data = yf.download(tickers=codes, period="1d", interval="1m", auto_adjust=False, progress=False)
            if len(codes) == 1:
                code = codes[0]
                prices[code] = data["Close"].dropna().iloc[-1].item()
            else:
                for code in codes:
                    try:
                        prices[code] = data["Close"][code].dropna().iloc[-1].item()
                    except:
                        prices[code] = 0
        except:
            pass
        for code in codes:
            if code not in prices or prices[code] == 0:
                try:
                    ticker = yf.Ticker(code)
                    info = ticker.fast_info
                    prices[code] = info.get("lastPrice") or info.get("regularMarketPrice") or 0
                except:
                    prices[code] = 0
        return prices

    @st.cache_data(ttl=20)
    def get_crypto_batch_prices(codes):
        prices = {}
        try:
            r = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=5)
            all_data = r.json()
            data_dict = {x["symbol"]: float(x["price"]) for x in all_data}
            for code in codes:
                symbol = code.upper()
                if not symbol.endswith("USDT"):
                    symbol += "USDT"
                prices[code] = data_dict.get(symbol, 0)
        except:
            for code in codes:
                prices[code] = 0
        return prices

    def get_meta_value(meta_key, default_value=""):
        c.execute("SELECT meta_value FROM app_meta WHERE meta_key=?", (meta_key,))
        row = c.fetchone()
        return row[0] if row else default_value

    def set_meta_value(meta_key, meta_value):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO app_meta (meta_key, meta_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(meta_key) DO UPDATE SET
                meta_value=excluded.meta_value,
                updated_at=excluded.updated_at
        """, (meta_key, str(meta_value), now_str))
        conn.commit()

    def is_sync_due(meta_key, hours):
        last_sync = get_meta_value(meta_key, "")
        if not last_sync:
            return True
        try:
            last_time = datetime.strptime(last_sync, "%Y-%m-%d %H:%M:%S")
            return (datetime.now() - last_time).total_seconds() >= hours * 3600
        except Exception:
            return True

    def upsert_symbol_cache(rows, source="manual"):
        if not rows:
            return 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = []
        for market, code, name in rows:
            clean_market = str(market).strip()
            clean_code = str(code).strip().upper()
            clean_name = str(name).strip()
            if not clean_market or not clean_code or not clean_name:
                continue
            payload.append((clean_market, clean_code, clean_name, source, now_str))
        if not payload:
            return 0
        c.executemany("""
            INSERT INTO symbol_cache (market, symbol_code, symbol_name, source, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(market, symbol_code) DO UPDATE SET
                symbol_name=excluded.symbol_name,
                source=excluded.source,
                updated_at=excluded.updated_at
        """, payload)
        conn.commit()
        return len(payload)

    def cache_symbols_from_existing_investments():
        c.execute("""
            SELECT DISTINCT market, symbol_code, COALESCE(symbol_name, symbol_code)
            FROM investments
            WHERE symbol_code IS NOT NULL AND TRIM(symbol_code) != ''
        """)
        rows = c.fetchall()
        return upsert_symbol_cache(rows, source="investments")

    def seed_us_symbol_cache():
        us_seeds = [
            ("美股", "AAPL", "Apple Inc."),
            ("美股", "MSFT", "Microsoft Corporation"),
            ("美股", "GOOGL", "Alphabet Inc."),
            ("美股", "AMZN", "Amazon.com, Inc."),
            ("美股", "META", "Meta Platforms, Inc."),
            ("美股", "TSLA", "Tesla, Inc."),
            ("美股", "NVDA", "NVIDIA Corporation"),
            ("美股", "AMD", "Advanced Micro Devices, Inc."),
            ("美股", "NFLX", "Netflix, Inc."),
            ("美股", "BABA", "Alibaba Group Holding Limited"),
        ]
        upsert_symbol_cache(us_seeds, source="seed")

    def fetch_a_stock_symbols():
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        rows = []
        page_size = 500
        fs_value = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
        for page_no in range(1, 31):
            params = {
                "pn": page_no,
                "pz": page_size,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": fs_value,
                "fields": "f12,f14",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            }
            try:
                response = requests.get(url, params=params, timeout=8)
                payload = response.json().get("data", {})
                diff = payload.get("diff", [])
                if isinstance(diff, dict):
                    records = list(diff.values())
                else:
                    records = list(diff)
            except Exception:
                break
            if not records:
                break
            for item in records:
                code = str(item.get("f12", "")).strip().upper()
                name = str(item.get("f14", "")).strip()
                if code and name:
                    rows.append(("A股", code, name))
            if len(records) < page_size:
                break
        return rows

    def fetch_fund_symbols():
        try:
            response = requests.get("https://fund.eastmoney.com/js/fundcode_search.js", timeout=10)
            text = response.text
            start = text.find("[")
            end = text.rfind("]")
            if start == -1 or end == -1 or end <= start:
                return []
            raw_json = text[start:end + 1]
            items = json.loads(raw_json)
            rows = []
            for item in items:
                if not isinstance(item, list) or len(item) < 3:
                    continue
                code = str(item[0]).strip().upper()
                name = str(item[2]).strip() if item[2] else str(item[1]).strip()
                if code and name:
                    rows.append(("A股", code, name))
            return rows
        except Exception:
            return []

    def fetch_crypto_symbols():
        try:
            response = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=8)
            items = response.json()
            rows = []
            for item in items:
                symbol = str(item.get("symbol", "")).strip().upper()
                if not symbol.endswith("USDT"):
                    continue
                base = symbol[:-4]
                if base:
                    rows.append(("Crypto", base, base))
            return rows
        except Exception:
            return []

    def refresh_us_symbol_cache_by_keyword(keyword):
        clean_keyword = str(keyword).strip().upper()
        if len(clean_keyword) < 2 or clean_keyword.isdigit():
            return
        cache_key = f"symbol_kw_synced_{clean_keyword}"
        if st.session_state.get(cache_key):
            return
        try:
            response = requests.get(
                "https://query1.finance.yahoo.com/v1/finance/search",
                params={"q": clean_keyword, "quotesCount": 20, "newsCount": 0},
                timeout=8,
            )
            payload = response.json()
            quotes = payload.get("quotes", [])
            rows = []
            for quote in quotes:
                code = str(quote.get("symbol", "")).strip().upper()
                if not code or "=" in code:
                    continue
                name = (
                    str(quote.get("shortname", "")).strip()
                    or str(quote.get("longname", "")).strip()
                    or code
                )
                rows.append(("美股", code, name))
            upsert_symbol_cache(rows, source="yahoo_search")
            st.session_state[cache_key] = True
        except Exception:
            st.session_state[cache_key] = True

    def ensure_symbol_cache_ready():
        if st.session_state.get("symbol_cache_ready"):
            return
        seed_us_symbol_cache()
        cache_symbols_from_existing_investments()

        if is_sync_due("symbol_sync_a_stock", 24):
            inserted = upsert_symbol_cache(fetch_a_stock_symbols(), source="eastmoney_a_stock")
            if inserted > 0:
                set_meta_value("symbol_sync_a_stock", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        if is_sync_due("symbol_sync_fund", 24):
            inserted = upsert_symbol_cache(fetch_fund_symbols(), source="eastmoney_fund")
            if inserted > 0:
                set_meta_value("symbol_sync_fund", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        if is_sync_due("symbol_sync_crypto", 24):
            inserted = upsert_symbol_cache(fetch_crypto_symbols(), source="binance")
            if inserted > 0:
                set_meta_value("symbol_sync_crypto", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        st.session_state.symbol_cache_ready = True

    def search_symbol_cache(keyword, limit=30):
        clean_keyword = str(keyword).strip()
        if not clean_keyword:
            return []
        code_kw = clean_keyword.upper()
        code_like = f"%{code_kw}%"
        name_like = f"%{clean_keyword}%"
        c.execute("""
            SELECT market, symbol_code, symbol_name
            FROM symbol_cache
            WHERE UPPER(symbol_code) LIKE ? OR symbol_name LIKE ?
            ORDER BY
                CASE
                    WHEN UPPER(symbol_code) = ? THEN 0
                    WHEN UPPER(symbol_code) LIKE ? THEN 1
                    WHEN symbol_name LIKE ? THEN 2
                    ELSE 3
                END,
                updated_at DESC,
                symbol_code ASC
            LIMIT ?
        """, (code_like, name_like, code_kw, f"{code_kw}%", f"{clean_keyword}%", int(limit)))
        return [
            {"market": row[0], "symbol_code": row[1], "symbol_name": row[2]}
            for row in c.fetchall()
        ]

    def get_cached_symbol_name(market, code):
        clean_code = str(code).strip().upper()
        clean_market = str(market).strip()
        c.execute("""
            SELECT symbol_name
            FROM symbol_cache
            WHERE market=? AND symbol_code=?
            LIMIT 1
        """, (clean_market, clean_code))
        row = c.fetchone()
        if row and row[0]:
            return row[0]
        c.execute("""
            SELECT symbol_name
            FROM symbol_cache
            WHERE symbol_code=?
            ORDER BY updated_at DESC
            LIMIT 1
        """, (clean_code,))
        row = c.fetchone()
        return row[0] if row and row[0] else ""

    # ------------------------------
    # 数据操作（支持共享）
    # ------------------------------
    def is_fund_code(code):
        clean_code = str(code).strip().upper()
        if not clean_code or not clean_code.isdigit() or len(clean_code) != 6:
            return False
        c.execute("""
            SELECT source
            FROM symbol_cache
            WHERE market='A股' AND symbol_code=?
            LIMIT 1
        """, (clean_code,))
        row = c.fetchone()
        if row and row[0]:
            source = str(row[0]).lower()
            if "fund" in source:
                return True
            if "a_stock" in source:
                return False
        return get_fund_name(clean_code) != clean_code

    def is_fund_investment(market, symbol_code):
        return market == "A股" and is_fund_code(str(symbol_code))

    def serialize_log_payload(data):
        if data is None:
            return None
        return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)

    def record_operation_log(entity_type, entity_id, action, operator, owner=None, before_data=None, after_data=None):
        changed_fields = None
        if isinstance(before_data, dict) and isinstance(after_data, dict):
            keys = sorted(set(before_data.keys()) | set(after_data.keys()))
            changed = [k for k in keys if before_data.get(k) != after_data.get(k)]
            changed_fields = ",".join(changed)
        c.execute("""
            INSERT INTO operation_logs
            (entity_type, entity_id, action, operator, owner, changed_fields, before_data, after_data, action_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entity_type,
            int(entity_id),
            action,
            operator,
            owner,
            changed_fields,
            serialize_log_payload(before_data),
            serialize_log_payload(after_data),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()

    def read_operation_logs(limit=200):
        query = """
            SELECT id, entity_type, entity_id, action, operator, owner, changed_fields, before_data, after_data, action_time
            FROM operation_logs
            ORDER BY id DESC
            LIMIT ?
        """
        return pd.read_sql_query(query, conn, params=(limit,))

    def parse_json_payload(raw):
        if not raw or not isinstance(raw, str):
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_display_target(log_row):
        before = parse_json_payload(log_row.get("before_data"))
        after = parse_json_payload(log_row.get("after_data"))
        source = after if after else before
        investor = source.get("investor", "")
        symbol_name = source.get("symbol_name", "")
        symbol_code = source.get("symbol_code", "")
        if symbol_name or symbol_code:
            return f"{investor} / {symbol_name}({symbol_code})".strip(" /")
        return f"{log_row.get('entity_type', 'unknown')}#{log_row.get('entity_id', '')}"

    def build_change_summary(log_row):
        field_alias = {
            "investor": "投资人",
            "market": "市场",
            "symbol_code": "代码",
            "symbol_name": "名称",
            "channel": "渠道",
            "cost_price": "成本价",
            "quantity": "数量",
            "update_time": "更新时间",
            "user": "归属人",
        }
        action = str(log_row.get("action", ""))
        before = parse_json_payload(log_row.get("before_data"))
        after = parse_json_payload(log_row.get("after_data"))

        if action == "create":
            return "新增记录"
        if action == "delete":
            return "删除记录"
        if action != "update":
            return "-"

        changed = []
        keys = sorted(set(before.keys()) | set(after.keys()))
        for key in keys:
            if key == "update_time":
                continue
            old_val = before.get(key)
            new_val = after.get(key)
            if old_val == new_val:
                continue
            label = field_alias.get(key, key)
            changed.append(f"{label}: {old_val} -> {new_val}")
        return "；".join(changed) if changed else "无关键字段变化"

    def get_friendly_logs_df(limit=200):
        raw_df = read_operation_logs(limit=limit)
        if raw_df.empty:
            return raw_df
        action_alias = {"create": "新增", "update": "修改", "delete": "删除"}
        entity_alias = {"investment": "投资记录"}
        rows = []
        for _, row in raw_df.iterrows():
            row_dict = row.to_dict()
            before = parse_json_payload(row_dict.get("before_data"))
            after = parse_json_payload(row_dict.get("after_data"))
            owner = row_dict.get("owner") or after.get("user") or before.get("user") or ""
            rows.append({
                "时间": row_dict.get("action_time", ""),
                "操作人": row_dict.get("operator", ""),
                "动作": action_alias.get(row_dict.get("action"), row_dict.get("action")),
                "对象": entity_alias.get(row_dict.get("entity_type"), row_dict.get("entity_type")),
                "标的": get_display_target(row_dict),
                "归属人": owner,
                "变更摘要": build_change_summary(row_dict),
            })
        return pd.DataFrame(rows)

    def read_data(current_user):
        shared_owners = list(get_share_permission_map(current_user).keys())
        accessible = list(set([current_user] + shared_owners))
        if not accessible:
            return pd.DataFrame()
        placeholders = ','.join(['?'] * len(accessible))
        query = f"SELECT * FROM investments WHERE user IN ({placeholders}) OR user IS NULL"
        return pd.read_sql_query(query, conn, params=accessible)

    def get_investor_list():
        df = read_data(current_user)
        return sorted(df["investor"].dropna().unique().tolist()) if not df.empty else []

    def add_data(investor, market, symbol_code, symbol_name, channel, cost_price, quantity):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        upsert_symbol_cache([(market, symbol_code, symbol_name)], source="user_submit")
        c.execute("""
            INSERT INTO investments 
            (investor, market, symbol_code, symbol_name, channel, cost_price, quantity, update_time, user)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (investor, market, symbol_code, symbol_name, channel, cost_price, quantity, now_str, current_user))
        record_id = c.lastrowid
        conn.commit()
        record_operation_log(
            entity_type="investment",
            entity_id=record_id,
            action="create",
            operator=current_user,
            owner=current_user,
            after_data={
                "investor": investor,
                "market": market,
                "symbol_code": symbol_code,
                "symbol_name": symbol_name,
                "channel": channel,
                "cost_price": float(cost_price),
                "quantity": float(quantity),
                "update_time": now_str,
                "user": current_user,
            }
        )

    def delete_data(record_id):
        c.execute("""
            SELECT investor, market, symbol_code, symbol_name, channel, cost_price, quantity, update_time, user
            FROM investments WHERE id=?
        """, (record_id,))
        old_row = c.fetchone()
        if not old_row:
            return False
        owner_from_record = old_row[8]
        if not can_edit_owner_data(owner_from_record, current_user):
            return False
        record_owner = owner_from_record or current_user

        before_data = {
            "investor": old_row[0],
            "market": old_row[1],
            "symbol_code": old_row[2],
            "symbol_name": old_row[3],
            "channel": old_row[4],
            "cost_price": float(old_row[5]),
            "quantity": float(old_row[6]),
            "update_time": old_row[7],
            "user": old_row[8],
        }
        c.execute("DELETE FROM investments WHERE id=?", (record_id,))
        conn.commit()
        record_operation_log(
            entity_type="investment",
            entity_id=record_id,
            action="delete",
            operator=current_user,
            owner=record_owner,
            before_data=before_data
        )
        return True

    def update_data(record_id, cost_price, quantity):
        c.execute("""
            SELECT investor, market, symbol_code, symbol_name, channel, cost_price, quantity, update_time, user
            FROM investments WHERE id=?
        """, (record_id,))
        old_row = c.fetchone()
        if not old_row:
            return False
        owner_from_record = old_row[8]
        if not can_edit_owner_data(owner_from_record, current_user):
            return False
        record_owner = owner_from_record or current_user

        before_data = {
            "investor": old_row[0],
            "market": old_row[1],
            "symbol_code": old_row[2],
            "symbol_name": old_row[3],
            "channel": old_row[4],
            "cost_price": float(old_row[5]),
            "quantity": float(old_row[6]),
            "update_time": old_row[7],
            "user": old_row[8],
        }
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            UPDATE investments
            SET cost_price=?, quantity=?, update_time=?
            WHERE id = ?
        """, (cost_price, quantity, now_str, record_id))
        conn.commit()
        after_data = {
            **before_data,
            "cost_price": float(cost_price),
            "quantity": float(quantity),
            "update_time": now_str,
        }
        record_operation_log(
            entity_type="investment",
            entity_id=record_id,
            action="update",
            operator=current_user,
            owner=record_owner,
            before_data=before_data,
            after_data=after_data
        )
        return True

    # ------------------------------
    # 添加投资
    # ------------------------------
    def render_symbol_search_section():
        raw_symbol = st.text_input("标的代码（支持模糊查询：代码/名称）", key="add_symbol_query")
        raw_symbol = raw_symbol.strip().upper()
        symbol_code_local = raw_symbol
        preview_market_local = identify_market(symbol_code_local) if symbol_code_local else ""
        selected_name_local = ""

        if raw_symbol:
            refresh_us_symbol_cache_by_keyword(raw_symbol)
            candidates = search_symbol_cache(raw_symbol, limit=20)
        else:
            candidates = []

        if candidates:
            option_map = {}
            option_list = ["保持手动输入"]
            for item in candidates:
                label = f"{item['symbol_code']} | {item['symbol_name']} | {item['market']}"
                option_map[label] = item
                option_list.append(label)
            pick_label = st.selectbox("匹配结果", option_list, key="symbol_match_choice")
            if pick_label != "保持手动输入":
                picked = option_map[pick_label]
                symbol_code_local = picked["symbol_code"]
                preview_market_local = picked["market"]
                selected_name_local = picked["symbol_name"]
                st.caption(f"已选择：{selected_name_local}（{preview_market_local}）")
            else:
                st.caption("未选择匹配项，将按输入代码提交")

        return symbol_code_local, preview_market_local, selected_name_local

    with st.expander("➕ 添加投资", expanded=True):
        ensure_symbol_cache_ready()
        investor_list = get_investor_list()
        selected_symbol_name = ""
        symbol_code = ""
        preview_market = ""

        if is_mobile_view:
            if investor_list:
                investor = st.selectbox("选择投资人", investor_list + ["新增投资人"], key="add_investor_select_mobile")
                if investor == "新增投资人":
                    investor = st.text_input("输入新投资人", value=current_user, key="add_investor_new_mobile")
            else:
                investor = st.text_input("投资人", value=current_user, key="add_investor_mobile")

            symbol_code, preview_market, selected_symbol_name = render_symbol_search_section()
            is_fund_for_input = is_fund_investment(preview_market, symbol_code) if symbol_code else False
            channel = st.text_input("渠道", key="add_channel_mobile")
            cost_price = st.number_input(
                "成本价",
                min_value=0.0,
                step=0.0001 if is_fund_for_input else 0.01,
                format="%.4f" if is_fund_for_input else "%.2f",
                key="add_cost_mobile"
            )
            quantity = st.number_input("数量", min_value=0.0, key="add_qty_mobile")
        else:
            col1, col2 = st.columns(2)
            with col1:
                if investor_list:
                    investor = st.selectbox("选择投资人", investor_list + ["新增投资人"], key="add_investor_select_desktop")
                    if investor == "新增投资人":
                        investor = st.text_input("输入新投资人", value=current_user, key="add_investor_new_desktop")
                else:
                    investor = st.text_input("投资人", value=current_user, key="add_investor_desktop")
                symbol_code, preview_market, selected_symbol_name = render_symbol_search_section()
                is_fund_for_input = is_fund_investment(preview_market, symbol_code) if symbol_code else False
            with col2:
                channel = st.text_input("渠道", key="add_channel_desktop")
                cost_price = st.number_input(
                    "成本价",
                    min_value=0.0,
                    step=0.0001 if is_fund_for_input else 0.01,
                    format="%.4f" if is_fund_for_input else "%.2f",
                    key="add_cost_desktop"
                )
                quantity = st.number_input("数量", min_value=0.0, key="add_qty_desktop")

        if st.button("提交", type="primary"):
            if symbol_code and quantity > 0:
                market = preview_market or identify_market(symbol_code)
                name = selected_symbol_name or get_symbol_name(market, symbol_code)
                add_data(investor, market, symbol_code, name, channel, cost_price, quantity)
                st.success("✅ 添加成功")
                st.rerun()

    # ------------------------------
    # 刷新按钮
    # ------------------------------
    def refresh_prices():
        st.cache_data.clear()
        st.rerun()

    st.button("🔄 刷新行情", on_click=refresh_prices)

    with st.expander("🧭 操作日志（审计）", expanded=False):
        log_limit = st.selectbox("显示条数", [50, 100, 200, 500], index=2)
        logs_df = get_friendly_logs_df(limit=log_limit)
        if logs_df.empty:
            st.caption("暂无日志记录")
        else:
            st.dataframe(logs_df, use_container_width=True, hide_index=True)

    # ------------------------------
    # 投资明细 & 汇总
    # ------------------------------
    st.subheader("📈 资产面板")
    df = read_data(current_user)
    if not df.empty:
        us_stock_list = df[df["market"] == "美股"]["symbol_code"].unique().tolist()
        crypto_list = df[df["market"] == "Crypto"]["symbol_code"].unique().tolist()

        price_dict = {}
        price_dict.update(get_us_stock_batch_prices(us_stock_list))
        price_dict.update(get_crypto_batch_prices(crypto_list))

        df["current_price"] = 0.0
        for index, row in df.iterrows():
            if row["market"] == "A股":
                price = get_a_stock_price(row["symbol_code"])
                if price == 0:
                    price = get_fund_nav(row["symbol_code"])
            else:
                price = price_dict.get(row["symbol_code"], 0)
            df.at[index, "current_price"] = float(price)

        df["total_cost"] = df["cost_price"] * df["quantity"]
        df["current_market_value"] = df["current_price"] * df["quantity"]
        df["profit"] = df["current_market_value"] - df["total_cost"]
        df["yield_pct"] = ((df["profit"] / df["total_cost"]) * 100).round(2).fillna(0)

        total_cost = df["total_cost"].sum()
        total_mv = df["current_market_value"].sum()
        total_profit = total_mv - total_cost
        total_yield = round((total_profit / total_cost * 100), 2) if total_cost > 0 else 0

        if is_mobile_view:
            st.markdown(
                f"""
                <div class="hero-card">
                  <div class="hero-title">资产总览</div>
                  <div class="hero-value">¥{total_mv:,.2f}</div>
                  <div class="hero-meta">总收益 ¥{total_profit:,.2f} · 收益率 {total_yield}%</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            m1, m2 = st.columns(2)
            m1.metric("总成本", f"¥{total_cost:,.2f}")
            m2.metric("当前市值", f"¥{total_mv:,.2f}")
            m3, m4 = st.columns(2)
            m3.metric("总收益", f"¥{total_profit:,.2f}")
            m4.metric("总收益率", f"{total_yield}%")
        else:
            st.subheader("📊 资产汇总（含共享）")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("总成本", f"¥{total_cost:,.2f}")
            c2.metric("当前市值", f"¥{total_mv:,.2f}")
            c3.metric("总收益", f"¥{total_profit:,.2f}")
            c4.metric("总收益率", f"{total_yield}%")

        st.subheader("📋 投资明细")

        for _, row in df.iterrows():
            owner_raw = row.get("user", "")
            owner = owner_raw.strip() if isinstance(owner_raw, str) else ""
            owner_display = owner if owner else "未知"
            with st.expander(f"{row['investor']} - {row['symbol_name']} ({row['symbol_code']})"):
                can_edit_row = can_edit_owner_data(owner, current_user)
                if owner == current_user:
                    st.caption("✅ 你是所有者 • 可编辑")
                elif can_edit_row:
                    st.caption(f"🔗 由 **{owner_display}** 共享给你 • 你有编辑权限")
                else:
                    st.caption(f"🔗 由 **{owner_display}** 共享给你 • 只读")

                row_is_fund = is_fund_investment(row["market"], row["symbol_code"])
                if is_mobile_view:
                    in_col1, in_col2 = st.columns(2)
                    new_cost = in_col1.number_input(
                        "成本",
                        value=float(row["cost_price"]),
                        step=0.0001 if row_is_fund else 0.01,
                        format="%.4f" if row_is_fund else "%.2f",
                        key=f"cost{row['id']}"
                    )
                    new_qty = in_col2.number_input("数量", value=float(row["quantity"]), key=f"qty{row['id']}")
                    if can_edit_row:
                        act_col1, act_col2 = st.columns(2)
                        if act_col1.button("💾 保存", key=f"save{row['id']}"):
                            if update_data(row["id"], new_cost, new_qty):
                                st.rerun()
                        if act_col2.button("🗑️ 删除", key=f"del{row['id']}"):
                            if delete_data(row["id"]):
                                st.rerun()
                    else:
                        st.info("只读")
                else:
                    col1, col2, col3 = st.columns([1, 1, 1])
                    new_cost = col1.number_input(
                        "成本",
                        value=float(row["cost_price"]),
                        step=0.0001 if row_is_fund else 0.01,
                        format="%.4f" if row_is_fund else "%.2f",
                        key=f"cost{row['id']}"
                    )
                    new_qty = col2.number_input("数量", value=float(row["quantity"]), key=f"qty{row['id']}")

                    if can_edit_row:
                        if col3.button("💾 保存", key=f"save{row['id']}"):
                            if update_data(row["id"], new_cost, new_qty):
                                st.rerun()
                        if col3.button("🗑️ 删除", key=f"del{row['id']}"):
                            if delete_data(row["id"]):
                                st.rerun()
                    else:
                        col3.info("只读")

                st.write(f"**当前价**：{row['current_price']:.4f}")
                st.write(f"**当前市值**：¥{row['current_market_value']:,.2f}")
                st.write(f"**收益率**：{row['yield_pct']}%")
    else:
        st.info("暂无数据，快去添加吧！")

    st.caption("全球资产管理系统 Pro Ultimate v2.7 | iPhone 视觉与交互优化")
