"""
fetch_market_data.py
从 Yahoo Finance 拉取今日精确市场数据，保存为 market_data.json。
由 GitHub Actions generate-briefing.yml 调用。
"""
import json
import sys
import time
from datetime import datetime

import pytz
import yfinance as yf

# S&P 500 十一板块 ETF
SECTORS = {
    "科技 (Technology)": "XLK",
    "通信服务 (Communication Services)": "XLC",
    "非必需消费 (Consumer Discretionary)": "XLY",
    "必需消费 (Consumer Staples)": "XLP",
    "医疗健康 (Health Care)": "XLV",
    "金融 (Financials)": "XLF",
    "工业 (Industrials)": "XLI",
    "能源 (Energy)": "XLE",
    "材料 (Materials)": "XLB",
    "公用事业 (Utilities)": "XLU",
    "房地产 (Real Estate)": "XLRE",
}

# 重点关注个股（用于识别当日最大涨跌幅）
WATCHLIST = {
    "AAPL": "苹果",
    "MSFT": "微软",
    "NVDA": "英伟达",
    "GOOGL": "谷歌",
    "AMZN": "亚马逊",
    "META": "Meta",
    "TSLA": "特斯拉",
    "AVGO": "博通",
    "JPM": "摩根大通",
    "BAC": "美国银行",
    "GS": "高盛",
    "MS": "摩根士丹利",
    "V": "Visa",
    "MA": "万事达卡",
    "LLY": "礼来",
    "UNH": "联合健康",
    "JNJ": "强生",
    "ABBV": "艾伯维",
    "XOM": "埃克森美孚",
    "CVX": "雪佛龙",
    "WMT": "沃尔玛",
    "COST": "好市多",
    "HD": "家得宝",
    "AMD": "超微半导体",
    "INTC": "英特尔",
    "QCOM": "高通",
    "ARM": "ARM控股",
    "NFLX": "奈飞",
    "DIS": "迪士尼",
    "PLTR": "Palantir",
    "SMCI": "超微电脑",
    "COIN": "Coinbase",
    "SHOP": "Shopify",
    "MSTR": "MicroStrategy",
    "GE": "通用电气",
    "CAT": "卡特彼勒",
    "BA": "波音",
}

# 全球主要指数
GLOBAL_INDICES = {
    "上证综指": "000001.SS",
    "恒生指数": "^HSI",
    "日经225": "^N225",
    "DAX (德国)": "^GDAXI",
    "FTSE 100 (英国)": "^FTSE",
}

# 大宗商品
COMMODITIES = {
    "WTI原油 ($/桶)": "CL=F",
    "黄金 ($/盎司)": "GC=F",
}


def fmt_pct(val: float) -> str:
    return f"+{val:.2f}%" if val >= 0 else f"{val:.2f}%"


def get_day_change(ticker_sym: str, retries: int = 3):
    """
    返回 (close, pct_change) 或 (None, None)。
    pct_change 单位：百分比，例如 0.67 代表 +0.67%。
    失败时最多重试 retries 次，指数退避。
    """
    for attempt in range(retries):
        try:
            t = yf.Ticker(ticker_sym)
            hist = t.history(period="5d")
            if hist is None or len(hist) < 2:
                return None, None
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                return None, None
            curr = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])
            if prev == 0:
                return curr, None
            pct = (curr - prev) / prev * 100
            return round(curr, 2), round(pct, 2)
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** attempt  # 1s, 2s
                print(f"  [retry {attempt+1}/{retries}] {ticker_sym}: {e} — waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"  [warn] {ticker_sym}: {e}", file=sys.stderr)
                return None, None
    return None, None


def main():
    et = pytz.timezone("America/New_York")
    now = datetime.now(et)

    data = {
        "date": now.strftime("%Y-%m-%d"),
        "generated_at": now.strftime("%Y-%m-%d %H:%M ET"),
        "indices": {},
        "sectors": {},
        "bonds_fx": {},
        "global_markets": {},
        "commodities": {},
        "top_movers": [],
    }

    # ── 三大指数 ──────────────────────────────────────────────
    print("Fetching US indices...")
    for name, sym in [
        ("标普500 (S&P 500)", "^GSPC"),
        ("纳斯达克 (Nasdaq)", "^IXIC"),
        ("道琼斯 (DJIA)", "^DJI"),
    ]:
        close, pct = get_day_change(sym)
        if close is not None and pct is not None:
            data["indices"][name] = {
                "symbol": sym,
                "close": close,
                "pct_change": pct,
                "pct_str": fmt_pct(pct),
            }
            print(f"  {name}: {close:,.2f} ({fmt_pct(pct)})")

    # ── 十一板块 ──────────────────────────────────────────────
    print("Fetching sector ETFs...")
    for name, sym in SECTORS.items():
        _, pct = get_day_change(sym)
        if pct is not None:
            data["sectors"][name] = {
                "symbol": sym,
                "pct_change": pct,
                "pct_str": fmt_pct(pct),
            }

    # ── 美债 & 美元指数 ───────────────────────────────────────
    print("Fetching bonds and FX...")
    for attempt in range(3):
        try:
            t = yf.Ticker("^TNX")
            hist = t.history(period="5d")
            closes = hist["Close"].dropna()
            if len(closes) >= 2:
                curr_y = float(closes.iloc[-1])
                prev_y = float(closes.iloc[-2])
                # ^TNX 单位是百分比，例如 4.52 = 4.52%
                # 变化量转换为基点：1个百分点 = 100 bps
                bps = round((curr_y - prev_y) * 100, 1)
                bps_str = f"{'+' if bps >= 0 else ''}{bps:.0f} bps"
                data["bonds_fx"]["10年期美债收益率"] = {
                    "value": round(curr_y, 2),
                    "bps_change": bps,
                    "display": f"{curr_y:.2f}%",
                    "change_display": bps_str,
                }
                print(f"  10Y Treasury: {curr_y:.2f}% ({bps_str})")
            break
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"  [warn] ^TNX: {e}", file=sys.stderr)

    dxy_close, dxy_pct = get_day_change("DX-Y.NYB")
    if dxy_close is not None and dxy_pct is not None:
        data["bonds_fx"]["美元指数 (DXY)"] = {
            "value": round(dxy_close, 2),
            "pct_change": dxy_pct,
            "pct_str": fmt_pct(dxy_pct),
        }
        print(f"  DXY: {dxy_close:.2f} ({fmt_pct(dxy_pct)})")

    # ── 全球市场 ──────────────────────────────────────────────
    print("Fetching global indices...")
    for name, sym in GLOBAL_INDICES.items():
        close, pct = get_day_change(sym)
        if close is not None and pct is not None:
            data["global_markets"][name] = {
                "symbol": sym,
                "close": close,
                "pct_change": pct,
                "pct_str": fmt_pct(pct),
            }

    # ── 大宗商品 ──────────────────────────────────────────────
    print("Fetching commodities...")
    for name, sym in COMMODITIES.items():
        close, pct = get_day_change(sym)
        if close is not None and pct is not None:
            data["commodities"][name] = {
                "symbol": sym,
                "value": close,
                "pct_change": pct,
                "pct_str": fmt_pct(pct),
            }

    # ── 个股涨跌幅（Top Movers）──────────────────────────────
    print("Fetching watchlist for top movers...")
    movers = []
    for ticker, cn_name in WATCHLIST.items():
        close, pct = get_day_change(ticker)
        if close is not None and pct is not None:
            movers.append(
                {
                    "ticker": ticker,
                    "cn_name": cn_name,
                    "close": close,
                    "pct_change": pct,
                    "pct_str": fmt_pct(pct),
                }
            )

    # 按绝对值排序，取 Top 10
    movers.sort(key=lambda x: abs(x["pct_change"]), reverse=True)
    data["top_movers"] = movers[:10]

    print("\nTop 5 movers:")
    for m in data["top_movers"][:5]:
        print(f"  {m['ticker']} ({m['cn_name']}): {m['pct_str']}")

    # ── 保存 ──────────────────────────────────────────────────
    with open("market_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to market_data.json ({data['date']})")
    return data


if __name__ == "__main__":
    main()
