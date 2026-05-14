"""Gold price fetcher & WeChat Work pusher.

Expects these env vars:
    ALAPI_TOKEN        - ALAPI API token
    ALAPI_MARKET       - market code (default: cn)
    WECOM_WEBHOOK_URL   - WeChat Work bot webhook URL
    EXCHANGE_RATE_API   - (optional) exchange rate API URL or fallback value
"""

import os
import sys
import json
import urllib.request
from datetime import datetime, timezone, timedelta

API_URL = "https://v3.alapi.cn/api/gold"
BJT = timezone(timedelta(hours=8))

MARKET_NAMES = {
    "cn": "上海黄金交易所",
    "hk": "香港金银业贸易场",
    "LF": "融通金",
}


def fetch_gold_price(token: str, market: str) -> dict:
    url = f"{API_URL}?token={token}&market={market}"
    req = urllib.request.Request(url, headers={"User-Agent": "GoldPricePusher/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("success"):
        raise RuntimeError(f"API error: {data.get('message', 'unknown')}")
    return data


def fetch_exchange_rate() -> str:
    """Try fetching USD/CNY rate; return fallback on failure."""
    url = os.environ.get("EXCHANGE_RATE_API", "")
    if not url:
        return "7.25（默认参考值）"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GoldPricePusher/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # Try common response shapes
        if isinstance(data, dict):
            rate = data.get("rate") or data.get("data", {}).get("rate") or data.get("rates", {}).get("CNY")
            if rate:
                return str(rate)
        return "7.25（解析失败）"
    except Exception:
        return "7.25（获取失败）"


def build_markdown(data: dict, market: str) -> str:
    now_str = datetime.now(BJT).strftime("%Y-%m-%d %H:%M")
    source = MARKET_NAMES.get(market, f"ALAPI({market})")
    # exchange_rate = fetch_exchange_rate()

    lines = [
        "# 每日贵金属行情简报",
        f"> 更新时间：{now_str}（北京时间）",
        f"> 数据来源：{source} / ALAPI",
        "",
    ]

    METAL_ORDER = {"黄金": 0, "铂金": 1, "钯金": 2, "白银": 3}
    items = sorted(data["data"], key=lambda x: METAL_ORDER.get(x["name"], 99))
    for item in items:
        name = item["name"]
        symbol = item["symbol"]
        buy = item["buy_price"]
        sell = item["sell_price"]
        high = item["high_price"]
        low = item["low_price"]
        lines.append(f"## {name}")
        lines.append(f"- **{symbol}**：`{buy}` 元/克")
        lines.append(f"  - 买入：`{buy}` | 卖出：`{sell}`")
        lines.append(f"  - 最高：`{high}` | 最低：`{low}`")
        lines.append("")

    # 蓝宝石 - not provided by this API
    # lines.append("## 蓝宝石")
    # lines.append("- 暂无实时行情数据（ALAPI 暂不提供）")
    # lines.append("")

    # 参考汇率
    # lines.append("## 参考汇率")
    # lines.append(f"- 1 美元 ≈ `{exchange_rate}` 人民币")
    # lines.append("")
    lines.append(f"> *本数据由 ALAPI 提供，仅供参考*")

    return "\n".join(lines)


def send_to_wecom(webhook_url: str, markdown: str) -> None:
    payload = json.dumps({
        "msgtype": "markdown",
        "markdown": {"content": markdown},
    }).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("errcode") != 0:
        raise RuntimeError(f"WeCom webhook error: {body}")


def main():
    token = os.environ.get("ALAPI_TOKEN")
    market = os.environ.get("ALAPI_MARKET", "cn")
    webhook = os.environ.get("WECOM_WEBHOOK_URL")

    missing = []
    if not token:
        missing.append("ALAPI_TOKEN")
    if not webhook:
        missing.append("WECOM_WEBHOOK_URL")
    if missing:
        print(f"Missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching gold prices (market={market})...")
    data = fetch_gold_price(token, market)
    md = build_markdown(data, market)
    print(md)
    print("\nSending to WeChat Work...")
    send_to_wecom(webhook, md)
    print("Done.")


if __name__ == "__main__":
    main()
