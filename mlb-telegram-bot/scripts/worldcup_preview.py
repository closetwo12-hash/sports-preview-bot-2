"""
FIFA 월드컵 2026 프리뷰 Generator — 칼럼니스트 스타일

데이터 소스: football-data.org API v4 (무료)
  - 오늘+내일 새벽 KST 범위 경기
  - 조별 순위 (그룹 스탠딩)
  - 전날 경기 결과
  - 팀 최근 폼

API 키: GitHub Secrets → FOOTBALL_API_KEY
  발급: https://www.football-data.org/client/register

발송: 매일 KST 오후 8시 (UTC 11:00, cron: 0 11 * * *)
      → EPL과 같은 시간, 월드컵 기간에만 발송
"""

import os, re, time, requests
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID  = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
FOOTBALL_API_KEY  = os.environ["FOOTBALL_API_KEY"]

KST       = timezone(timedelta(hours=9))
NOW_KST   = datetime.now(KST)
TODAY_KR  = NOW_KST.strftime("%Y년 %m월 %d일")
NOW_KR    = NOW_KST.strftime("%Y년 %m월 %d일 %H:%M KST")
TODAY     = NOW_KST.strftime("%Y-%m-%d")
TOMORROW  = (NOW_KST + timedelta(days=1)).strftime("%Y-%m-%d")
YESTERDAY = (NOW_KST - timedelta(days=1)).strftime("%Y-%m-%d")

# 월드컵 기간 체크 (2026-06-11 ~ 2026-07-19)
WC_START = datetime(2026, 6, 11, tzinfo=KST)
WC_END   = datetime(2026, 7, 20, tzinfo=KST)

BASE = "https://api.football-data.org/v4"
SESS = requests.Session()
SESS.headers.update({
    "X-Auth-Token": FOOTBALL_API_KEY,
    "Accept": "application/json",
})

# 팀명 한국어
TEAM_KR = {
    "Korea Republic": "대한민국", "South Korea": "대한민국",
    "Brazil": "브라질", "Argentina": "아르헨티나",
    "France": "프랑스", "England": "잉글랜드",
    "Spain": "스페인", "Germany": "독일",
    "Portugal": "포르투갈", "Netherlands": "네덜란드",
    "Belgium": "벨기에", "Italy": "이탈리아",
    "Uruguay": "우루과이", "Colombia": "콜롬비아",
    "Mexico": "멕시코", "United States": "미국",
    "Canada": "캐나다", "Japan": "일본",
    "Australia": "호주", "Morocco": "모로코",
    "Senegal": "세네갈", "Ghana": "가나",
    "Nigeria": "나이지리아", "Cameroon": "카메룬",
    "Saudi Arabia": "사우디아라비아", "Iran": "이란",
    "Qatar": "카타르", "Ecuador": "에콰도르",
    "Switzerland": "스위스", "Croatia": "크로아티아",
    "Denmark": "덴마크", "Poland": "폴란드",
    "Serbia": "세르비아", "Ukraine": "우크라이나",
    "Turkey": "튀르키예", "Austria": "오스트리아",
    "Sweden": "스웨덴", "Norway": "노르웨이",
    "Czech Republic": "체코", "Scotland": "스코틀랜드",
    "Wales": "웨일스", "Greece": "그리스",
    "Hungary": "헝가리", "Slovakia": "슬로바키아",
    "Romania": "루마니아", "Albania": "알바니아",
    "Chile": "칠레", "Peru": "페루",
    "Venezuela": "베네수엘라", "Bolivia": "볼리비아",
    "Paraguay": "파라과이", "Costa Rica": "코스타리카",
    "Panama": "파나마", "Honduras": "온두라스",
    "Jamaica": "자메이카",
    "New Zealand": "뉴질랜드", "China PR": "중국",
    "Indonesia": "인도네시아", "Iraq": "이라크",
    "Egypt": "이집트", "Algeria": "알제리",
    "Tunisia": "튀니지",
    "South Africa": "남아프리카공화국",
    "Ivory Coast": "코트디부아르",
    "DR Congo": "콩고민주공화국",
}

def team_kr(name: str) -> str:
    return TEAM_KR.get(name, name)


# ══════════════════════════════════════════════════
# 1. API 공통 호출
# ══════════════════════════════════════════════════
def fapi(path: str, params: dict = None) -> dict:
    try:
        r = SESS.get(f"{BASE}{path}", params=params or {}, timeout=15)
        if r.status_code == 429:
            print("  Rate limit — 65초 대기")
            time.sleep(65)
            r = SESS.get(f"{BASE}{path}", params=params or {}, timeout=15)
        if r.status_code != 200:
            print(f"  API {r.status_code}: {path} — {r.text[:100]}")
            return {}
        return r.json()
    except Exception as e:
        print(f"  API 오류({path}): {e}")
        return {}


# ══════════════════════════════════════════════════
# 2. 오늘 경기 수집 (KST 오늘 00:00 ~ 내일 06:00)
# ══════════════════════════════════════════════════
def fetch_today_matches() -> list:
    print(f"  월드컵 경기 수집 ({TODAY} ~ {TOMORROW})...")
    data = fapi("/matches", {"competitions": "WC",
                             "dateFrom": TODAY, "dateTo": TOMORROW})
    matches  = []
    kst_from = NOW_KST.replace(hour=0, minute=0, second=0, microsecond=0)
    kst_to   = kst_from + timedelta(hours=30)  # 내일 오전 6시까지

    for m in data.get("matches", []):
        if m.get("status") in ("FINISHED", "IN_PLAY", "PAUSED"):
            continue
        try:
            utc = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
            kst = utc.astimezone(KST)
        except:
            continue
        if not (kst_from <= kst < kst_to):
            continue

        ht = m["homeTeam"]["name"]
        at = m["awayTeam"]["name"]
        matches.append({
            "id":        m["id"],
            "kickoff":   kst.strftime("%m/%d %H:%M"),
            "home":      ht,
            "away":      at,
            "home_kr":   team_kr(ht),
            "away_kr":   team_kr(at),
            "home_id":   m["homeTeam"]["id"],
            "away_id":   m["awayTeam"]["id"],
            "stage":     m.get("stage", ""),
            "group":     m.get("group", ""),
            "matchday":  m.get("matchday", "-"),
        })

    matches.sort(key=lambda x: x["kickoff"])
    print(f"  ✅ {len(matches)}경기")
    return matches


# ══════════════════════════════════════════════════
# 3. 전날 결과
# ══════════════════════════════════════════════════
def fetch_yesterday_results() -> list:
    data = fapi("/matches", {"competitions": "WC",
                             "dateFrom": YESTERDAY, "dateTo": YESTERDAY})
    results = []
    for m in data.get("matches", []):
        if m.get("status") != "FINISHED":
            continue
        hs  = m["score"]["fullTime"]["home"]
        as_ = m["score"]["fullTime"]["away"]
        if hs is None or as_ is None:
            continue
        ht_kr = team_kr(m["homeTeam"]["name"])
        at_kr = team_kr(m["awayTeam"]["name"])
        winner = ht_kr if hs > as_ else (at_kr if as_ > hs else "무승부")
        results.append({
            "home_kr":    ht_kr,
            "away_kr":    at_kr,
            "home_score": hs,
            "away_score": as_,
            "winner":     winner,
            "summary":    f"{at_kr} {as_}:{hs} {ht_kr}",
            "stage":      m.get("stage",""),
            "group":      m.get("group",""),
        })
    return results


# ══════════════════════════════════════════════════
# 4. 조별 순위
# ══════════════════════════════════════════════════
_STANDINGS_CACHE = None

def fetch_standings() -> dict:
    global _STANDINGS_CACHE
    if _STANDINGS_CACHE is not None:
        return _STANDINGS_CACHE

    data = fapi("/competitions/WC/standings")
    stats = {}

    for standing in data.get("standings", []):
        group_name = standing.get("group", "")
        for entry in standing.get("table", []):
            kr = team_kr(entry["team"]["name"])
            stats[kr] = {
                "group":  group_name,
                "rank":   entry.get("position", "-"),
                "played": entry.get("playedGames", 0),
                "won":    entry.get("won", 0),
                "draw":   entry.get("draw", 0),
                "lost":   entry.get("lost", 0),
                "gf":     entry.get("goalsFor", 0),
                "ga":     entry.get("goalsAgainst", 0),
                "gd":     entry.get("goalDifference", 0),
                "pts":    entry.get("points", 0),
                "form":   entry.get("form", ""),
            }

    _STANDINGS_CACHE = stats
    return stats


# ══════════════════════════════════════════════════
# 5. 팀 최근 폼 (월드컵 경기 기준)
# ══════════════════════════════════════════════════
def fetch_team_form(team_id: int, team_kr_name: str) -> str:
    time.sleep(6)  # rate limit
    data = fapi(f"/teams/{team_id}/matches",
                {"competitions": "WC", "status": "FINISHED", "limit": 5})
    icons = {"W": "✅", "D": "➖", "L": "❌"}
    form  = []
    for m in data.get("matches", [])[-5:]:
        ht  = m["homeTeam"]["name"]
        hs  = m["score"]["fullTime"].get("home")
        as_ = m["score"]["fullTime"].get("away")
        if hs is None or as_ is None:
            continue
        is_home = (team_kr(ht) == team_kr_name)
        my  = hs if is_home else as_
        opp = as_ if is_home else hs
        r   = "W" if my > opp else ("D" if my == opp else "L")
        form.append(icons.get(r, "?"))
    return " ".join(form) if form else "첫 경기"


# ══════════════════════════════════════════════════
# 6. 데이터 보강
# ══════════════════════════════════════════════════
def enrich(matches: list, yesterday: list) -> list:
    standings = fetch_standings()
    time.sleep(2)
    result = []
    for m in matches:
        hkr = m["home_kr"]
        akr = m["away_kr"]
        print(f"  ⚽ {akr} vs {hkr} ({m['kickoff']})")

        hs  = standings.get(hkr, {})
        as_ = standings.get(akr, {})
        hf  = fetch_team_form(m["home_id"], hkr)
        af  = fetch_team_form(m["away_id"], akr)

        h_yd = next((r for r in yesterday
                     if r["home_kr"]==hkr or r["away_kr"]==hkr), None)
        a_yd = next((r for r in yesterday
                     if r["home_kr"]==akr or r["away_kr"]==akr), None)

        result.append({
            **m,
            "hs": hs, "as_": as_,
            "hf": hf, "af": af,
            "h_yd": h_yd, "a_yd": a_yd,
        })
    return result


# ══════════════════════════════════════════════════
# 7. Claude 프롬프트
# ══════════════════════════════════════════════════
def build_prompt(matches: list) -> str:
    yesterday_date = (NOW_KST - timedelta(days=1)).strftime("%m월 %d일")
    blocks = ""

    for i, m in enumerate(matches, 1):
        hkr = m["home_kr"]
        akr = m["away_kr"]
        hs  = m["hs"]
        as_ = m["as_"]

        # 스테이지 한국어
        stage_map = {
            "GROUP_STAGE": "조별리그",
            "LAST_32": "32강",
            "LAST_16": "16강",
            "QUARTER_FINALS": "8강",
            "SEMI_FINALS": "4강",
            "THIRD_PLACE": "3·4위전",
            "FINAL": "결승",
        }
        stage_kr = stage_map.get(m["stage"], m["stage"])
        group_str = f" {m['group']}" if m["group"] and "GROUP" in m["stage"] else ""

        def yd_str(yd, team):
            if not yd: return "경기 없음"
            won = (yd["winner"] == team)
            draw = (yd["winner"] == "무승부")
            return (f"{yd['summary']} "
                    f"({'승' if won else ('무' if draw else '패')}) "
                    f"[{stage_map.get(yd.get('stage',''), yd.get('stage',''))}]")

        def rank_str(s, team):
            if not s:
                return f"{team}: 데이터 없음"
            return (f"{s.get('group','')}{s.get('rank','-')}위 "
                    f"{s.get('pts',0)}pts "
                    f"({s.get('won',0)}승{s.get('draw',0)}무{s.get('lost',0)}패) "
                    f"득{s.get('gf',0)} 실{s.get('ga',0)} 득실{s.get('gd',0):+}")

        # 대한민국 출전 여부 플래그
        kor_match = (hkr == "대한민국" or akr == "대한민국")

        blocks += f"""
━━━ 경기{i}: {akr} vs {hkr}  |  {m['kickoff']} KST  |  {stage_kr}{group_str} ━━━
{'⭐ 한국 출전 경기 ⭐' if kor_match else ''}
[조별 현황]
  홈({hkr}): {rank_str(hs, hkr)}
  원정({akr}): {rank_str(as_, akr)}
[전날({yesterday_date}) 결과]
  홈({hkr}): {yd_str(m['h_yd'], hkr)}
  원정({akr}): {yd_str(m['a_yd'], akr)}
[대회 내 최근 폼]
  {hkr}: {m['hf']}
  {akr}: {m['af']}
"""

    return f"""당신은 15년 경력의 FIFA 월드컵 전문 축구 칼럼니스트입니다.
2026 FIFA 월드컵 경기 프리뷰를 한국어로 작성하세요.
오늘({TODAY_KR}) 한국 시간 기준 예정 경기입니다.

[경기 데이터]
{blocks}

[작성 지침]
1. 모든 경기를 빠짐없이 전부 분석.
2. 각 경기를 독립적인 짧은 칼럼으로 서술.
3. 조별리그는 조 순위와 득실 상황, 진출 시나리오를 중심으로.
4. 토너먼트(16강 이후)는 양팀의 대회 흐름, 체력, 전술 특징 중심으로.
5. 전날 결과 복기로 오늘 경기 맥락 제시.
6. 대한민국 출전 경기는 더 상세하고 감성적으로 서술 (한국 팬 대상).
7. 특정 선수명은 세계적으로 검증된 스타(손흥민, 메시, 호날두, 음바페 등)만 언급.
   부상/결장 가능성이 있으므로 과도한 특정 선수 의존 금지.
8. 마지막에 예상 결과(승/무/패) 명시.
9. 마크다운 기호(**) 절대 금지. 수치 나열 금지 — 스토리텔링 우선.
10. 각 경기 칼럼 350~450자 내외. 한국 경기는 500자 이상.

[형식]

⚽ {{원정}} vs {{홈}}  |  {{시간}} KST  {{스테이지}}
{{한국 출전 경기는 "🇰🇷 한국 출전!" 표시}}

{{전날 결과 복기}}

{{전력 분석 — 조 순위/폼 기반}}

{{진출 시나리오 또는 토너먼트 의미}}

오늘의 예상: {{결과}}
{{핵심 근거}}

══════════════════════════════

마지막:
⭐ 오늘의 주목경기: {{경기명 + 이유}}
🇰🇷 한국팀 한마디: {{한국 경기 있으면 특별 코멘트, 없으면 생략}}
⚠️ 오늘의 변수: {{핵심 변수}}

══════════════════════════════
🔒 본 최종 분석은 VIP에게만 공유됩니다.

📩 VIP 조합상담 문의는
👉 @HC_VV77 클릭 후 문의"""


# ══════════════════════════════════════════════════
# 8. Claude 호출
# ══════════════════════════════════════════════════
def call_claude(prompt: str) -> str:
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_API_KEY,
                 "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": "claude-sonnet-4-6", "max_tokens": 4096,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=300,
    )
    if r.status_code != 200:
        print(f"  Claude API {r.status_code}: {r.text[:100]}")
        return "분석 생성 실패"
    data = r.json()
    if not data.get("content"):
        return "Claude 응답 비어있음"
    return data["content"][0]["text"]


# ══════════════════════════════════════════════════
# 9. 텔레그램
# ══════════════════════════════════════════════════
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
            safe = re.sub(r"[<>&]", "", text)
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": safe},
                timeout=15)
    except Exception as e:
        print(f"  발송 실패: {e}")

def send_long(text: str):
    text = clean(text)
    MAX  = 3800
    if len(text) <= MAX:
        send_msg(text); return
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


# ══════════════════════════════════════════════════
# 10. 메인
# ══════════════════════════════════════════════════
def main():
    print(f"[{TODAY_KR}] 월드컵 프리뷰 시작...")

    # 월드컵 기간 외에는 실행 안 함
    if not (WC_START <= NOW_KST < WC_END):
        print(f"  월드컵 기간 아님 ({NOW_KST.strftime('%Y-%m-%d')}) — 종료")
        return

    print("📡 전날 결과 수집...")
    yesterday = fetch_yesterday_results()
    print(f"  → {len(yesterday)}경기")

    print("📡 오늘 경기 수집...")
    matches = fetch_today_matches()

    if not matches:
        print("오늘 월드컵 경기 없음 — 발송 생략")
        return

    print(f"  → {len(matches)}경기")
    print("📊 데이터 보강...")
    enriched = enrich(matches, yesterday)

    print("🤖 Claude 칼럼 생성...")
    preview = call_claude(build_prompt(enriched))

    print("📨 발송...")
    # 한국 경기 여부 표시
    kor_today = any(
        m["home_kr"] == "대한민국" or m["away_kr"] == "대한민국"
        for m in matches
    )
    kor_flag = " 🇰🇷 한국 경기 있음!" if kor_today else ""

    header = (
        f"⚽ FIFA 월드컵 2026 프리뷰{kor_flag}\n"
        f"📅 {TODAY_KR}\n🕐 {NOW_KR}\n"
        f"{'─'*28}\n\n"
    )
    send_long(header + preview)
    print("🎉 완료!")


if __name__ == "__main__":
    main()
