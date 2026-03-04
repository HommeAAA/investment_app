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

# ------------------------------
# 基础设置
# ------------------------------
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

st.set_page_config(page_title="全球资产管理系统 Pro Ultimate", layout="wide", page_icon="🌍")
st.title("🌍 全球资产管理系统 Pro Ultimate")

# ------------------------------
# 数据库连接
# ------------------------------
@st.cache_resource
def get_db_connection():
    conn = sqlite3.connect("testApp.db", check_same_thread=False)
    return conn

conn = get_db_connection()
c = conn.cursor()

# ------------------------------
# 密码函数（支持旧密码自动迁移）
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
            return True, True   # 需要升级
        return False, False
    else:
        try:
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')), False
        except:
            return False, False

# ------------------------------
# 数据库初始化（已修复：标准SQL写法）
# ------------------------------
def init_database():
    # === 用户表（干净写法）===
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT
        )
    """)

    # === 投资表（干净写法）===
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

    # === 共享表（干净写法）===
    c.execute("""
        CREATE TABLE IF NOT EXISTS shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL,
            shared_with TEXT NOT NULL,
            created_at TEXT,
            UNIQUE(owner, shared_with)
        )
    """)
    conn.commit()

    # 自动升级旧投资表（兼容老数据）
    c.execute("PRAGMA table_info(investments)")
    cols = [row[1] for row in c.fetchall()]
    if "user" not in cols:
        c.execute("ALTER TABLE investments ADD COLUMN user TEXT")
        conn.commit()

    # 创建默认管理员账号
    c.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if c.fetchone()[0] == 0:
        hashed = hash_password("admin123")
        c.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                  ("admin", hashed, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        st.toast("✅ 默认管理员账号已创建：**admin / admin123**", icon="🎉")

init_database()

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
# 会话状态 + 登录/注册页面
# ------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None

if not st.session_state.logged_in:
    st.subheader("🔐 请先登录或注册")
    tab1, tab2 = st.tabs(["📥 登录", "📝 注册"])

    with tab1:
        with st.form("login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            if st.form_submit_button("🚀 登录", type="primary"):
                if login_user(username, password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.success(f"欢迎回来，{username}！")
                    st.rerun()
                else:
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

else:
    current_user = st.session_state.username

    # ------------------------------
    # 侧边栏（共享管理）
    # ------------------------------
    with st.sidebar:
        st.success(f"👤 当前用户：**{current_user}**")
        if st.button("🚪 登出"):
            st.session_state.logged_in = False
            st.session_state.username = None
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

    # ------------------------------
    # 行情 & 数据函数（保持不变）
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
        c.execute("""
            INSERT INTO investments 
            (investor, market, symbol_code, symbol_name, channel, cost_price, quantity, update_time, user)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (investor, market, symbol_code, symbol_name, channel, cost_price, quantity,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S"), current_user))
        conn.commit()

    def delete_data(record_id, record_owner):
        if record_owner == current_user:
            c.execute("DELETE FROM investments WHERE id=?", (record_id,))
            conn.commit()
            return True
        return False

    def update_data(record_id, record_owner, cost_price, quantity):
        if record_owner == current_user:
            c.execute("""
                UPDATE investments
                SET cost_price=?, quantity=?, update_time=?
                WHERE id = ?
            """, (cost_price, quantity, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), record_id))
            conn.commit()
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
        with col2:
            channel = st.text_input("渠道")
            cost_price = st.number_input("成本价", min_value=0.0)
            quantity = st.number_input("数量", min_value=0.0)

        if st.button("提交", type="primary"):
            if symbol_code and quantity > 0:
                market = identify_market(symbol_code)
                symbol_code = symbol_code.upper()
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

                col1, col2, col3 = st.columns([1, 1, 1])
                new_cost = col1.number_input("成本", value=float(row["cost_price"]), key=f"cost{row['id']}")
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

    st.caption(f"全球资产管理系统 Pro Ultimate v2.3 | bcrypt + 共享功能")