import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import yfinance as yf
import requests
import os
import logging

# ------------------------------
# 基础设置
# ------------------------------
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

st.set_page_config(page_title="全球资产管理系统 Pro Ultimate", layout="wide")
st.title("🌍 全球资产管理系统 Pro Ultimate")

# ------------------------------
# 数据库初始化
# ------------------------------
conn = sqlite3.connect("testApp.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
          CREATE TABLE IF NOT EXISTS investments
          (
              id
              INTEGER
              PRIMARY
              KEY
              AUTOINCREMENT,
              investor
              TEXT,
              market
              TEXT,
              symbol_code
              TEXT,
              symbol_name
              TEXT,
              channel
              TEXT,
              cost_price
              REAL,
              quantity
              REAL,
              update_time
              TEXT
          )
          """)
conn.commit()


# ------------------------------
# 市场识别
# ------------------------------
def identify_market(code):
    code = str(code).upper()
    if "USDT" in code or code in ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]:
        return "Crypto"
    if code.isdigit() and len(code) == 6:
        return "A股"
    return "美股"


# ------------------------------
# 标的名称获取
# ------------------------------
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


# ------------------------------
# 行情获取
# ------------------------------
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
        data = yf.download(
            tickers=codes,
            period="1d",
            interval="1m",
            auto_adjust=False,
            progress=False
        )
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
# 数据操作
# ------------------------------
def read_data():
    return pd.read_sql_query("SELECT * FROM investments", conn)


def get_investor_list():
    df = read_data()
    return sorted(df["investor"].dropna().unique().tolist()) if not df.empty else []


def add_data(investor, market, symbol_code, symbol_name, channel, cost_price, quantity):
    c.execute("""
              INSERT INTO investments (investor, market, symbol_code, symbol_name, channel, cost_price, quantity,
                                       update_time)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?)
              """, (
                  investor, market, symbol_code, symbol_name, channel, cost_price, quantity,
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S")
              ))
    conn.commit()


def delete_data(id):
    c.execute("DELETE FROM investments WHERE id=?", (id,))
    conn.commit()


def update_data(id, cost_price, quantity):
    c.execute("""
              UPDATE investments
              SET cost_price=?,
                  quantity=?,
                  update_time=?
              WHERE id = ?
              """, (cost_price, quantity, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), id))
    conn.commit()


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
                investor = st.text_input("输入新投资人")
        else:
            investor = st.text_input("投资人")
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
            st.success("添加成功")
            st.rerun()


# ------------------------------
# 刷新按钮
# ------------------------------
def refresh_prices():
    st.cache_data.clear()
    st.rerun()


st.button("🔄 刷新行情", on_click=refresh_prices)

# ------------------------------
# 展示投资明细
# ------------------------------
st.subheader("📋 投资明细")
df = read_data()
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
    df["yield_pct"] = ((df["profit"] / df["total_cost"]) * 100).round(2)

    # ------------------------------
    # 持仓编辑/删除
    # ------------------------------
    for index, row in df.iterrows():
        with st.expander(f"{row['investor']} - {row['symbol_name']}"):
            col1, col2, col3 = st.columns([1, 1, 1])
            new_cost = col1.number_input("修改成本", value=float(row["cost_price"]), key=f"cost{row['id']}")
            new_quantity = col2.number_input("修改数量", value=float(row["quantity"]), key=f"qty{row['id']}")
            if col3.button("保存", key=f"save{row['id']}"):
                update_data(row["id"], new_cost, new_quantity)
                st.rerun()
            if col3.button("删除", key=f"del{row['id']}"):
                delete_data(row["id"])
                st.rerun()
            st.write("当前价:", row["current_price"])
            st.write("当前市值:", row["current_market_value"])
            st.write("收益率:", row["yield_pct"], "%")

    # ------------------------------
    # 资产汇总
    # ------------------------------
    st.subheader("📊 资产汇总")
    total_cost = df["total_cost"].sum()
    total_market_value = df["current_market_value"].sum()
    total_profit = total_market_value - total_cost
    total_yield = round((total_profit / total_cost * 100), 2) if total_cost > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总成本", f"¥{total_cost:,.2f}")
    c2.metric("当前市值", f"¥{total_market_value:,.2f}")
    c3.metric("总收益", f"¥{total_profit:,.2f}")
    c4.metric("总收益率", f"{total_yield}%")
else:
    st.info("暂无数据")