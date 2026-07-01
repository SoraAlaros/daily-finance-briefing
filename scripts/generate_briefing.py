"""
generate_briefing.py
读取 market_data.json（由 fetch_market_data.py 生成），
调用 Claude API + web_search 生成简报，
输出到 briefings/zh/YYYY-MM-DD.md。

环境变量：ANTHROPIC_API_KEY
"""
import json
import os
import sys
from pathlib import Path

import anthropic

SYSTEM_PROMPT = """你是一名专业的金融分析师助手，负责每日生成一份高质量的金融市场资讯简报（中文版）。

## 最重要的规则：数据准确性

用户提供的 JSON 市场数据来自 **Yahoo Finance API 实时抓取**，所有数字100%准确。
**你必须严格使用 JSON 中的数字，不得修改、近似或替换任何数值。**

绝对不能自己编造或估算的数据：
- 三大指数收盘点位（close）和涨跌幅（pct_str）
- 标普500各板块涨跌幅（pct_str）
- 美债收益率（display）和变化（change_display）
- 美元指数（value）和涨跌幅（pct_str）
- 全球指数（close + pct_str）
- 大宗商品价格（value + pct_str）
- 焦点个股涨跌幅（pct_str）——从 top_movers 字段取，**只用 pct_str，不自行计算**

## 你的工作流程

**第一步：记住所有市场数据数字**

**第二步：使用 web_search 搜索（高效，尽量控制在10次以内）**
- 针对 top_movers 中涨跌幅最大的3-5只个股，逐一搜索今日新闻/原因
- 今日重大财经新闻（美联储、通胀、就业、关税贸易、央行动态、A股港股、原油黄金）
- 华尔街机构最新观点：高盛/摩根士丹利/摩根大通/贝莱德/PIMCO 近期报告/博客/播客
- 明日重要日程：经济数据公布、财报、联储官员讲话

**第三步：生成完整 Markdown 简报**

## 格式规范

### 不含YTD
所有表格只显示"当日涨跌幅"一列，**永久不加 YTD 列**。

### 涨跌颜色（HTML span，pandoc 可保留）
- 涨：`<span style="color:#16a34a">▲+X.XX%</span>`
- 跌：`<span style="color:#dc2626">▼-X.XX%</span>`
- 平（±0.05%以内）：`0.00%`

pct_str 字段已含 + 或 - 号，直接填入即可，例如 pct_str="+0.67%" → `<span style="color:#16a34a">▲+0.67%</span>`

### 加粗
- 三大指数收盘点位和涨跌幅
- 全球要闻标题
- 华尔街核心观点
- 焦点个股涨跌幅
- 明日关注事件名

## 简报完整结构与格式示例

```
# 每日金融市场资讯简报 — {YYYY}年{M}月{D}日

## 📊 美股收盘

**三大指数**
| 指数 | 收盘点位 | 当日涨跌幅 |
|------|---------|------------|
（用 JSON indices 字段，收盘点位和涨跌幅均加粗）

**标普500板块表现**
| 板块 | 当日涨跌幅 |
|------|------------|
（用 JSON sectors 字段，11个板块全部列出，按涨跌幅从高到低排序）

**美债与美元**
| 指标 | 当前值 | 当日变化 |
|------|--------|----------|
（用 JSON bonds_fx 字段）

**焦点个股**
| 股票 | 当日涨跌幅 | 原因 |
|------|------------|------|
（从 top_movers 中选3-5只最有新闻价值的，搜索每只的原因，涨跌幅加粗）

---

## 🌍 全球市场与今日要闻

（欧亚股市涨跌简表，然后6-10条要闻，每条格式如下示例：）

**1. 特朗普表示美国"必须回应"，伊朗被指击落美军直升机**

来源：彭博社 / TheStreet（[原文链接](https://...)）

伊朗被指在霍尔木兹海峡附近击落一架美国陆军阿帕奇武装直升机，两名飞行员据报安全无虞。特朗普随即表示美国"必须做出回应"，进一步加剧市场对中东冲突扩大的担忧。消息令股市盘中急挫，纳斯达克100一度下跌逾2%，随后在特朗普暗示协议可能"两三天内"达成的消息下有所回稳。本次事件再度凸显伊朗战争对金融市场的冲击远未结束，也标志着自4月停火以来最严峻的一次地缘摩擦升温。

（每条要闻必须有：加粗标题 + 来源行 + 3-5句正文，涵盖事件经过、市场影响、背景意义）

---

## 🏦 华尔街观点

（5条，来自高盛/摩根士丹利/摩根大通/贝莱德/PIMCO等，每条格式如下示例：）

**高盛资产管理：建设性立场不变，青睐股票收益策略应对波动**

来源：高盛资产管理 2026年6月市场脉搏（[原文链接](https://...)）

核心观点：**高盛维持对股票和固定收益资产的建设性判断，但警惕更高的收益率、油价或地缘政治风险的冲击，当前推荐以"股票收益策略"缓冲潜在波动同时参与上行。**

高盛指出，全球股市从3月低点的急剧反弹令其对高收益率、油价上行或地缘政治黑天鹅的风险保持警惕。公司认为AI建设周期将持续拉动实物资产投资需求，私募基础设施在通胀环境中历史上展现出较强韧性。就中东能源冲击而言，高盛预计将在未来数月内大部分消退，但挥之不去的通胀担忧意味着多元化组合回报将低于早前预期。

（每条华尔街观点必须有：加粗机构+核心标题 + 来源行含链接 + 核心观点一句加粗 + 2-4句详细正文阐述逻辑和具体内容）

---

## 🔭 明日关注

（重要经济数据/财报/央行讲话，事件名加粗）

---
*简报生成时间：{生成时间}（美东时间）*
*数据来源：Yahoo Finance API（市场数据精确抓取）、Bloomberg、华尔街见闻、FT、WSJ、MarketWatch、高盛、摩根士丹利、摩根大通、贝莱德、PIMCO等*
```
"""


def generate_briefing(market_data: dict) -> str:
    client = anthropic.Anthropic()

    date_str = market_data["date"]

    user_prompt = f"""今天是 {date_str}（美东时间）。

以下是今日精确市场数据（Yahoo Finance API 实时抓取，数字100%准确，请严格使用）：

```json
{json.dumps(market_data, ensure_ascii=False, indent=2)}
```

请按步骤生成今日市场简报：
1. 使用 web_search 搜索今日焦点个股新闻（从 top_movers 挑选3-5只最有新闻价值的）
2. 使用 web_search 搜索今日重大财经新闻（6-10条）
3. 使用 web_search 搜索华尔街机构近期观点（5条）
4. 使用 web_search 搜索明日重要事件
5. 生成完整的 Markdown 简报

**关键提醒：市场数据（指数点位/涨跌幅/债券/外汇/个股pct_str）必须100%使用上方JSON中的精确数字，不得修改。**
搜索时请高效，控制在10次以内。
"""

    messages = [{"role": "user", "content": user_prompt}]
    all_text = []

    # 支持 pause_turn / max_tokens 续写（服务端工具循环或 token 不足时继续）
    for iteration in range(6):
        print(f"  Claude API call (iteration {iteration + 1})...", flush=True)
        with client.messages.stream(
            model="claude-opus-4-8",
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=messages,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
        ) as stream:
            final = stream.get_final_message()

        # 收集文字内容（跳过 thinking/tool 块）
        for block in final.content:
            if block.type == "text" and block.text.strip():
                all_text.append(block.text)

        print(f"  Done (stop_reason={final.stop_reason})", flush=True)

        if final.stop_reason in ("end_turn",):
            break

        if final.stop_reason in ("pause_turn", "max_tokens"):
            # 追加 assistant 消息后继续
            messages.append({"role": "assistant", "content": final.content})
            print("  Continuing...", flush=True)
            continue

        # 其他 stop_reason（如 stop_sequence）也终止
        break

    briefing = "".join(all_text).strip()

    if not briefing:
        raise ValueError("Claude returned empty briefing")

    # 如有前言（preamble），定位到简报正文开头
    header = "# 每日金融市场资讯简报"
    if header in briefing:
        briefing = briefing[briefing.index(header):]
    else:
        raise ValueError(f"Briefing header not found — output may be truncated. Preview: {briefing[:200]}")

    return briefing


def main():
    data_file = "market_data.json"
    if not os.path.exists(data_file):
        print(f"Error: {data_file} not found. Run fetch_market_data.py first.", file=sys.stderr)
        sys.exit(1)

    with open(data_file, "r", encoding="utf-8") as f:
        market_data = json.load(f)

    date_str = market_data["date"]
    print(f"Generating briefing for {date_str}...")

    briefing = generate_briefing(market_data)

    output_dir = Path("briefings/zh")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{date_str}.md"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(briefing)

    print(f"\nBriefing saved: {output_file}")
    print(f"Preview:\n{briefing[:300]}\n...")


if __name__ == "__main__":
    main()
