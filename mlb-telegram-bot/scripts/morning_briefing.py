"""
모닝 브리핑 — 증시 요약 + 한국/미국 주요 뉴스 10가지
발송: KST 오전 9시 (UTC 00:00, cron: 0 0 * * *)

데이터 소스:
  증시: yfinance (KOSPI, KOSDAQ, S&P500, 나스닥, 다우, 환율, 금, 원유)
  뉴스: Google News RSS (한국어 + 영어)
  분석: Claude API (증시 해설 + 뉴스 요약)
"""

import os, re, time, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False
    print("⚠️ yfinance 없음 — pip install yfinance")

TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID  = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

KST      = timezone(timedelta(hours=9))
NOW_KST  = datetime.now(KST)
TODAY_KR = NOW_KST.strftime("%Y년 %m월 %d일")
NOW_KR   = NOW_KST.strftime("%Y년 %m월 %d일 %H:%M KST")
TODAY_DOW = ["월","화","수","목","금","토","일"][NOW_KST.weekday()]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

# ══════════════════════════════════════════════════════════════
# 1. 증시 데이터 (yfinance)
# ══════════════════════════════════════════════════════════════
TICKERS = {
    # 한국 지수
    "KOSPI":   "^KS11",
    "KOSDAQ":  "^KQ11",
    # 미국 지수
    "S&P500":  "^GSPC",
    "나스닥":   "^IXIC",
    "다우존스": "^DJI",
    # 환율
    "달러/원":  "KRW=X",
    "엔/원":    "JPYKRW=X",
    # 원자재
    "금":      "GC=F",
    "WTI유가": "CL=F",
    # 주요 종목 (한국)
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "현대차":  "005380.KS",
    # 주요 종목 (미국)
    "애플":    "AAPL",
    "엔비디아": "NVDA",
    "테슬라":  "TSLA",
}

def fetch_market_data() -> dict:
    data = {}
    if not HAS_YF:
        return data

    try:
        symbols = list(TICKERS.values())
        tickers = yf.Tickers(" ".join(symbols))

        for name, sym in TICKERS.items():
            try:
                t     = tickers.tickers[sym]
                info  = t.fast_info
                price = info.last_price
                prev  = info.previous_close

                if price is None or prev is None or prev == 0:
                    # fast_info 실패 시 history로 fallback
                    hist  = t.history(period="2d")
                    if len(hist) >= 2:
                        price = float(hist["Close"].iloc[-1])
                        prev  = float(hist["Close"].iloc[-2])
                    elif len(hist) == 1:
                        price = float(hist["Close"].iloc[-1])
                        prev  = price
                    else:
                        continue

                chg     = price - prev
                chg_pct = chg / prev * 100 if prev != 0 else 0
                arrow   = "▲" if chg >= 0 else "▼"
                sign    = "+" if chg >= 0 else ""

                # 숫자 포맷 (환율·지수·가격 구분)
                if "원" in name or "달러" in name or "엔" in name:
                    price_str = f"{price:,.2f}"
                    chg_str   = f"{sign}{chg:,.2f}"
                elif price > 10000:
                    price_str = f"{price:,.0f}"
                    chg_str   = f"{sign}{chg:,.0f}"
                else:
                    price_str = f"{price:,.2f}"
                    chg_str   = f"{sign}{chg:,.2f}"

                data[name] = {
                    "price":   price_str,
                    "chg":     chg_str,
                    "chg_pct": f"{sign}{chg_pct:.2f}%",
                    "arrow":   arrow,
                    "raw_pct": chg_pct,
                }
            except Exception as e:
                print(f"  {name}({sym}) 수집 실패: {e}")
                data[name] = {"price":"-","chg":"-","chg_pct":"-","arrow":"—","raw_pct":0}
    except Exception as e:
        print(f"  증시 전체 수집 실패: {e}")

    return data


def format_market_block(data: dict) -> str:
    """증시 데이터를 텔레그램용 문자열로 포맷"""
    def line(name, emoji=""):
        d = data.get(name, {})
        if not d or d["price"] == "-":
            return f"{emoji} {name}: 데이터 없음"
        col = "🔴" if d["raw_pct"] < 0 else "🟢" if d["raw_pct"] > 0 else "⚪"
        return f"{col} {name}: {d['price']}  {d['arrow']} {d['chg_pct']}"

    kr_indices = [line("KOSPI"), line("KOSDAQ")]
    us_indices = [line("S&P500"), line("나스닥"), line("다우존스")]
    forex      = [line("달러/원"), line("엔/원")]
    commodities= [line("금"), line("WTI유가")]
    kr_stocks  = [line("삼성전자"), line("SK하이닉스"), line("현대차")]
    us_stocks  = [line("애플"), line("엔비디아"), line("테슬라")]

    return "\n".join([
        "📈 한국 증시",
        *kr_indices,
        "",
        "📊 미국 증시 (전일 종가)",
        *us_indices,
        "",
        "💱 환율",
        *forex,
        "",
        "🛢 원자재",
        *commodities,
        "",
        "🇰🇷 주요 종목",
        *kr_stocks,
        "",
        "🇺🇸 주요 종목",
        *us_stocks,
    ])


# ══════════════════════════════════════════════════════════════
# 2. 뉴스 수집 (Google News RSS)
# ══════════════════════════════════════════════════════════════
def fetch_rss_news(url: str, max_items: int = 15) -> list:
    """Google News RSS에서 뉴스 제목 + 출처 수집"""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=12)
        if r.status_code != 200:
            print(f"  RSS 수집 실패 {r.status_code}")
            return []
        root  = ET.fromstring(r.content)
        items = root.findall(".//item")
        news  = []
        for item in items[:max_items]:
            title  = item.findtext("title", "").strip()
            source_el = item.find("source")
            source = source_el.text.strip() if source_el is not None else ""
            # 제목에서 출처 제거 (구글 뉴스는 "제목 - 출처" 형태)
            if " - " in title and source:
                title = title.rsplit(" - ", 1)[0].strip()
            if title:
                news.append({"title": title, "source": source})
        return news
    except Exception as e:
        print(f"  RSS 수집 실패({url}): {e}")
        return []


def fetch_all_news() -> dict:
    print("  한국 뉴스 수집...")
    kr_news = fetch_rss_news(
        "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko", max_items=20
    )
    time.sleep(0.5)

    print("  미국 뉴스 수집...")
    us_news = fetch_rss_news(
        "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en", max_items=20
    )
    return {"kr": kr_news, "us": us_news}


# ══════════════════════════════════════════════════════════════
# 3. Claude 프롬프트 — 증시 해설 + 뉴스 요약
# ══════════════════════════════════════════════════════════════
def build_prompt(market_data: dict, news: dict) -> str:
    # 증시 데이터 블록
    market_lines = []
    for name, d in market_data.items():
        if d["price"] != "-":
            market_lines.append(f"  {name}: {d['price']} ({d['chg_pct']})")
    market_block = "\n".join(market_lines) if market_lines else "  데이터 없음"

    # 한국 뉴스 블록
    kr_block = "\n".join(
        [f"  {i+1}. {n['title']} ({n['source']})"
         for i, n in enumerate(news["kr"][:15])]
    ) or "  없음"

    # 미국 뉴스 블록
    us_block = "\n".join(
        [f"  {i+1}. {n['title']} ({n['source']})"
         for i, n in enumerate(news["us"][:15])]
    ) or "  없음"

    return f"""당신은 경제 전문 애널리스트입니다.
오늘({TODAY_KR} {TODAY_DOW}요일) 아침 9시 모닝 브리핑을 작성하세요.

[증시 데이터]
{market_block}

[한국 뉴스 헤드라인]
{kr_block}

[미국 뉴스 헤드라인]
{us_block}

[작성 지침]
1. 증시 해설: 전날 미국 증시와 오늘 한국 증시 흐름을 2~3문장으로 자연스럽게 서술.
   주요 등락 원인을 뉴스와 연결해 설명. 수치는 맥락 속에 자연스럽게.
2. 한국 뉴스: 헤드라인 중 중요한 것 10가지를 선별해 한 줄 요약 (한국어).
   정치/경제/사회/국제 균형 있게.
3. 미국 뉴스: 헤드라인 중 중요한 것 10가지를 선별해 한 줄 요약 (한국어로 번역).
   경제/정치/테크/국제 균형 있게.
4. 마크다운 기호(**텍스트** 등) 절대 금지.
5. 각 뉴스 항목은 번호 + 한 줄로 간결하게.
6. 전체 길이 3500자 이내.

[형식 — 기호 그대로 사용]

📈 오늘의 증시 동향
{{증시 흐름 해설 2~3문장}}

🔑 오늘의 핵심 포인트
{{오늘 가장 주목할 포인트 2~3개 불릿 없이 서술}}

══════════════════════════════

🇰🇷 한국 주요 뉴스 TOP 10

1. {{뉴스 제목 요약}}
2. {{뉴스 제목 요약}}
3. {{뉴스 제목 요약}}
4. {{뉴스 제목 요약}}
5. {{뉴스 제목 요약}}
6. {{뉴스 제목 요약}}
7. {{뉴스 제목 요약}}
8. {{뉴스 제목 요약}}
9. {{뉴스 제목 요약}}
10. {{뉴스 제목 요약}}

══════════════════════════════

🇺🇸 미국 주요 뉴스 TOP 10

1. {{뉴스 제목 요약 (한국어)}}
2. {{뉴스 제목 요약 (한국어)}}
3. {{뉴스 제목 요약 (한국어)}}
4. {{뉴스 제목 요약 (한국어)}}
5. {{뉴스 제목 요약 (한국어)}}
6. {{뉴스 제목 요약 (한국어)}}
7. {{뉴스 제목 요약 (한국어)}}
8. {{뉴스 제목 요약 (한국어)}}
9. {{뉴스 제목 요약 (한국어)}}
10. {{뉴스 제목 요약 (한국어)}}"""


def call_claude(prompt: str) -> str:
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_API_KEY,
                 "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": "claude-sonnet-4-6", "max_tokens": 2048,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    if r.status_code != 200:
        print(f"  Claude API {r.status_code}: {r.text[:100]}")
        return "브리핑 생성 실패"
    data = r.json()
    if not data.get("content"):
        return "Claude 응답 비어있음"
    return data["content"][0]["text"]


# ══════════════════════════════════════════════════════════════
# 4. 텔레그램 발송
# ══════════════════════════════════════════════════════════════
def clean(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*',     r'\1', text)
    text = re.sub(r'__(.+?)__',     r'\1', text)
    text = re.sub(r'\n{3,}',        '\n\n', text)
    return text.strip()

def send_msg(text: str):
    if len(text) > 4096:
        text = text[:4090] + "..."
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=15)
        if r.status_code != 200:
            print(f"  텔레그램 {r.status_code}: {r.text[:100]}")
            safe = re.sub(r"[<>&]", "", text)
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": safe},
                timeout=15)
    except Exception as e:
        print(f"  발송 실패: {e}")

def send_long(text: str):
    text = clean(text); MAX = 3800
    if len(text) <= MAX:
        send_msg(text); print("✅ 발송"); return
    # ══ 구분선 기준으로 분할
    parts = [p.strip() for p in re.split(r'══+', text) if p.strip()]
    chunk = ""; n = 1
    for p in parts:
        cand = chunk + "\n\n" + p if chunk else p
        if len(cand) > MAX:
            if chunk: send_msg(chunk); print(f"✅ {n}번"); n += 1
            chunk = p
        else:
            chunk = cand
    if chunk: send_msg(chunk); print(f"✅ {n}번")


# ══════════════════════════════════════════════════════════════
# 5. 메인
# ══════════════════════════════════════════════════════════════
def main():
    print(f"[{TODAY_KR}] 모닝 브리핑 시작...")

    print("📊 증시 데이터 수집...")
    market_data = fetch_market_data()
    print(f"  → {len(market_data)}개 티커 수집")

    print("📰 뉴스 수집...")
    news = fetch_all_news()
    print(f"  → 한국 {len(news['kr'])}건 / 미국 {len(news['us'])}건")

    print("🤖 Claude 브리핑 생성...")
    prompt   = build_prompt(market_data, news)
    briefing = call_claude(prompt)

    # 헤더: 증시 원시 데이터 먼저 발송
    market_text = format_market_block(market_data)
    header = (
        f"🌅 모닝 브리핑\n"
        f"📅 {TODAY_KR} ({TODAY_DOW})\n"
        f"🕘 {NOW_KR}\n"
        f"{'─'*28}\n\n"
        f"{market_text}"
    )

    print("📨 발송...")
    # 1부: 증시 수치
    send_msg(header)
    time.sleep(0.5)
    # 2부: Claude 해설 + 뉴스
    send_long(briefing)
    print("🎉 완료!")


if __name__ == "__main__":
    main()
