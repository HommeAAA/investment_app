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
import streamlit.components.v1 as components

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

def get_auth_token_from_query():
    token = None
    try:
        token = st.query_params.get("auth")
    except:
        pass
    if token is None:
        try:
            qp = st.experimental_get_query_params()
            token = qp.get("auth")
        except:
            token = None
    if isinstance(token, list):
        return token[0] if token else None
    return token

def set_auth_token_to_query(token):
    try:
        st.query_params["auth"] = token
        return
    except:
        pass
    try:
        st.experimental_set_query_params(auth=token)
    except:
        pass

def clear_auth_token_from_query():
    try:
        if "auth" in st.query_params:
            del st.query_params["auth"]
        return
    except:
        pass
    try:
        qp = st.experimental_get_query_params()
        qp.pop("auth", None)
        cleaned = {k: v for k, v in qp.items() if v}
        st.experimental_set_query_params(**cleaned)
    except:
        pass

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
            created_at TEXT,
            UNIQUE(owner, shared_with)
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
    conn.commit()

    c.execute("PRAGMA table_info(investments)")
    cols = [row[1] for row in c.fetchall()]
    if "user" not in cols:
        c.execute("ALTER TABLE investments ADD COLUMN user TEXT")
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
def invite_user(owner, shared_with):
    if owner == shared_with:
        return False, "不能邀请自己"
    c.execute("SELECT 1 FROM users WHERE username=?", (shared_with,))
    if not c.fetchone():
        return False, "用户不存在"
    try:
        c.execute("INSERT INTO shares (owner, shared_with, created_at) VALUES (?, ?, ?)",
                  (owner, shared_with, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        return True, f"✅ 已邀请 {shared_with}"
    except sqlite3.IntegrityError:
        return False, "已邀请过该用户"

def revoke_share(owner, shared_with):
    c.execute("DELETE FROM shares WHERE owner=? AND shared_with=?", (owner, shared_with))
    conn.commit()

def get_shared_owners(current_user):
    c.execute("SELECT DISTINCT owner FROM shares WHERE shared_with=?", (current_user,))
    return [row[0] for row in c.fetchall()]

def get_my_invited_users(owner):
    c.execute("SELECT shared_with FROM shares WHERE owner=?", (owner,))
    return [row[0] for row in c.fetchall()]

# ------------------------------
# 登录/注册页面 或 主界面
# ------------------------------
if not st.session_state.logged_in:
    st.subheader("🔐 请先登录或注册")
    tab1, tab2 = st.tabs(["📥 登录", "📝 注册"])

    with tab1:
        with st.form("login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            if st.form_submit_button("🚀 登录", type="primary"):
                if login_user(username, password):
                    token = make_auth_token(username)
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.pending_auth_token = token
                    st.session_state.clear_auth_client = False
                    set_auth_token_to_query(token)
                    upsert_login_session(username)
                    auth_log("login_ok", username=username)
                    st.success(f"欢迎回来，{username}！")
                    st.rerun()
                else:
                    auth_log("login_failed", username=username)
                    st.error("用户名或密码错误")

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
            clear_auth_token_from_query()
            clear_login_session()
            st.rerun()

        st.divider()
        st.subheader("🔗 共享管理")
        invited = get_my_invited_users(current_user)
        if invited:
            st.caption("我邀请的用户：")
            for u in invited:
                col1, col2 = st.columns([4, 1])
                col1.write(f"• {u}")
                if col2.button("撤销", key=f"revoke_{u}"):
                    revoke_share(current_user, u)
                    st.rerun()
        else:
            st.caption("暂无邀请用户")

        with st.expander("邀请新用户"):
            invite_username = st.text_input("对方用户名", key="invite_input")
            if st.button("发送邀请", type="primary", key="invite_btn"):
                if invite_username:
                    success, msg = invite_user(current_user, invite_username)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("请输入用户名")

        shared_from = get_shared_owners(current_user)
        if shared_from:
            st.caption("共享给我的人：")
            st.write(", ".join(shared_from))

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
        if market == "A股":
            name = get_a_stock_name(code)
            if name == code:
                name = get_fund_name(code)
            return name
        if market == "美股":
            return get_us_stock_name(code)
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

    # ------------------------------
    # 数据操作（支持共享）
    # ------------------------------
    @st.cache_data(ttl=3600)
    def is_fund_code(code):
        if not code or not str(code).isdigit() or len(str(code)) != 6:
            return False
        return get_fund_name(str(code)) != str(code)

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
        action_alias = {"create": "新增", "update": "修改", "delete": "删除"}
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
            rows.append({
                "时间": row_dict.get("action_time", ""),
                "操作人": row_dict.get("operator", ""),
                "动作": action_alias.get(row_dict.get("action"), row_dict.get("action")),
                "对象": entity_alias.get(row_dict.get("entity_type"), row_dict.get("entity_type")),
                "标的": get_display_target(row_dict),
                "归属人": row_dict.get("owner", ""),
                "变更摘要": build_change_summary(row_dict),
            })
        return pd.DataFrame(rows)

    def read_data(current_user):
        shared_owners = get_shared_owners(current_user)
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
                "update_time": now_str
            }
        )

    def delete_data(record_id, record_owner):
        if record_owner == current_user:
            c.execute("""
                SELECT investor, market, symbol_code, symbol_name, channel, cost_price, quantity, update_time, user
                FROM investments WHERE id=?
            """, (record_id,))
            old_row = c.fetchone()
            before_data = None
            if old_row:
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
        return False

    def update_data(record_id, record_owner, cost_price, quantity):
        if record_owner == current_user:
            c.execute("""
                SELECT investor, market, symbol_code, symbol_name, channel, cost_price, quantity, update_time, user
                FROM investments WHERE id=?
            """, (record_id,))
            old_row = c.fetchone()
            if not old_row:
                return False
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
        return False

    # ------------------------------
    # 添加投资
    # ------------------------------
    with st.expander("➕ 添加投资", expanded=True):
        investor_list = get_investor_list()
        col1, col2 = st.columns(2)
        with col1:
            if investor_list:
                investor = st.selectbox("选择投资人", investor_list + ["新增投资人"])
                if investor == "新增投资人":
                    investor = st.text_input("输入新投资人", value=current_user)
            else:
                investor = st.text_input("投资人", value=current_user)
            symbol_code = st.text_input("标的代码（600519 / AAPL / BTC / 017437）")
            symbol_code = symbol_code.strip().upper()
            preview_market = identify_market(symbol_code) if symbol_code else ""
            is_fund_for_input = is_fund_investment(preview_market, symbol_code) if symbol_code else False
        with col2:
            channel = st.text_input("渠道")
            cost_price = st.number_input(
                "成本价",
                min_value=0.0,
                step=0.0001 if is_fund_for_input else 0.01,
                format="%.4f" if is_fund_for_input else "%.2f"
            )
            quantity = st.number_input("数量", min_value=0.0)

        if st.button("提交", type="primary"):
            if symbol_code and quantity > 0:
                market = identify_market(symbol_code)
                name = get_symbol_name(market, symbol_code)
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
            st.dataframe(logs_df, width="stretch", hide_index=True)

    # ------------------------------
    # 投资明细 & 汇总
    # ------------------------------
    st.subheader("📋 投资明细")
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

        for _, row in df.iterrows():
            owner = row.get("user", "未知")
            with st.expander(f"{row['investor']} - {row['symbol_name']} ({row['symbol_code']})"):
                if owner == current_user:
                    st.caption("✅ 你是所有者 • 可编辑")
                else:
                    st.caption(f"🔗 由 **{owner}** 共享给你 • 只读")

                row_is_fund = is_fund_investment(row["market"], row["symbol_code"])
                col1, col2, col3 = st.columns([1, 1, 1])
                new_cost = col1.number_input(
                    "成本",
                    value=float(row["cost_price"]),
                    step=0.0001 if row_is_fund else 0.01,
                    format="%.4f" if row_is_fund else "%.2f",
                    key=f"cost{row['id']}"
                )
                new_qty = col2.number_input("数量", value=float(row["quantity"]), key=f"qty{row['id']}")

                if owner == current_user:
                    if col3.button("💾 保存", key=f"save{row['id']}"):
                        if update_data(row["id"], owner, new_cost, new_qty):
                            st.rerun()
                    if col3.button("🗑️ 删除", key=f"del{row['id']}"):
                        if delete_data(row["id"], owner):
                            st.rerun()
                else:
                    col3.info("只读")

                st.write(f"**当前价**：{row['current_price']:.4f}")
                st.write(f"**当前市值**：¥{row['current_market_value']:,.2f}")
                st.write(f"**收益率**：{row['yield_pct']}%")

        st.subheader("📊 资产汇总（含共享）")
        total_cost = df["total_cost"].sum()
        total_mv = df["current_market_value"].sum()
        total_profit = total_mv - total_cost
        total_yield = round((total_profit / total_cost * 100), 2) if total_cost > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("总成本", f"¥{total_cost:,.2f}")
        c2.metric("当前市值", f"¥{total_mv:,.2f}")
        c3.metric("总收益", f"¥{total_profit:,.2f}")
        c4.metric("总收益率", f"{total_yield}%")
    else:
        st.info("暂无数据，快去添加吧！")

    st.caption(f"全球资产管理系统 Pro Ultimate v2.6 | 刷新不登出已修复")
