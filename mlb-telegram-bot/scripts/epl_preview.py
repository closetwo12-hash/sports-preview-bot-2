"""
EPL Daily Preview Generator — 칼럼니스트 스타일

데이터 소스: football-data.org API v4 (무료)
  - 오늘 EPL 경기 일정
  - 팀 순위 / 최근 5경기 폼
  - 홈/원정 득실 스탯
  - 전날 경기 결과

API 키: GitHub Secrets → FOOTBALL_API_KEY
  발급: https://www.football-data.org/client/register

발송: KST 오후 8시 (UTC 11:00, cron: 0 11 * * *)
"""

import os, re, time, requests
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID  = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
FOOTBALL_API_KEY  = os.environ["FOOTBALL_API_KEY"]

KST      = timezone(timedelta(hours=9))
NOW_KST  = datetime.now(KST)
TODAY_KR = NOW_KST.strftime("%Y년 %m월 %d일")
NOW_KR   = NOW_KST.strftime("%Y년 %m월 %d일 %H:%M KST")
TODAY     = NOW_KST.strftime("%Y-%m-%d")
TOMORROW  = (NOW_KST + timedelta(days=1)).strftime("%Y-%m-%d")
YESTERDAY = (NOW_KST - timedelta(days=1)).strftime("%Y-%m-%d")

BASE = "https://api.football-data.org/v4"
SESS = requests.Session()
SESS.headers.update({
    "X-Auth-Token": FOOTBALL_API_KEY,
    "Accept": "application/json",
})

# EPL 팀 한국어
TEAM_KR = {
    "Arsenal":               "아스널",
    "Aston Villa":           "아스톤 빌라",
    "Bournemouth":           "본머스",
    "Brentford":             "브렌트포드",
    "Brighton & Hove Albion":"브라이튼",
    "Brighton":              "브라이튼",
    "Chelsea":               "첼시",
    "Crystal Palace":        "크리스탈 팰리스",
    "Everton":               "에버튼",
    "Fulham":                "풀럼",
    "Ipswich Town":          "입스위치",
    "Leicester City":        "레스터",
    "Liverpool":             "리버풀",
    "Manchester City":       "맨시티",
    "Manchester United":     "맨유",
    "Newcastle United":      "뉴캐슬",
    "Nottingham Forest":     "노팅엄",
    "Southampton":           "사우샘프턴",
    "Tottenham Hotspur":     "토트넘",
    "West Ham United":       "웨스트햄",
    "Wolverhampton Wanderers":"울버햄튼",
    "Wolverhampton":         "울버햄튼",
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
            print("  ⚠️ Rate limit — 60초 대기")
            time.sleep(60)
            r = SESS.get(f"{BASE}{path}", params=params or {}, timeout=15)
        if r.status_code != 200:
            print(f"  ⚠️ API {r.status_code}: {path}")
            return {}
        return r.json()
    except Exception as e:
        print(f"  ⚠️ API 오류({path}): {e}")
        return {}


# ══════════════════════════════════════════════════
# 2. 오늘 EPL 경기
# ══════════════════════════════════════════════════
def fetch_today_matches() -> list:
    """
    KST 오늘 00:00 ~ 내일 06:00 사이 킥오프 경기를 수집.
    EPL 경기는 한국 시간으로 밤~새벽에 열리므로
    다음날 새벽 경기도 '오늘 경기'로 포함.
    """
    print(f"  EPL 경기 수집 ({TODAY} ~ {TOMORROW})...")
    # 오늘+내일 이틀치 조회
    data = fapi("/matches", {"competitions": "PL",
                             "dateFrom": TODAY, "dateTo": TOMORROW})
    matches = []
    # KST 기준 오늘 00:00 ~ 내일 06:00
    kst_from = NOW_KST.replace(hour=0, minute=0, second=0, microsecond=0)
    kst_to   = kst_from + timedelta(hours=30)  # 오늘 00:00 + 30시간 = 내일 06:00

    for m in data.get("matches", []):
        if m.get("status") in ("FINISHED", "IN_PLAY", "PAUSED"):
            continue
        try:
            utc = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
            kst = utc.astimezone(KST)
        except:
            continue
        # KST 기준 범위 밖 경기 제외
        if not (kst_from <= kst < kst_to):
            continue
        ht = m["homeTeam"]["name"]
        at = m["awayTeam"]["name"]
        kickoff = kst.strftime("%m/%d %H:%M")  # 날짜 포함 (새벽 경기 구분)
        matches.append({
            "id":       m["id"],
            "kickoff":  kickoff,
            "home":     ht,
            "away":     at,
            "home_kr":  team_kr(ht),
            "away_kr":  team_kr(at),
            "matchday": m.get("matchday", "-"),
            "home_id":  m["homeTeam"]["id"],
            "away_id":  m["awayTeam"]["id"],
        })
    # 킥오프 시간 순 정렬
    matches.sort(key=lambda x: x["kickoff"])
    print(f"  ✅ {len(matches)}경기 (KST 오늘 자정~내일 오전 6시)")
    return matches


# ══════════════════════════════════════════════════
# 3. 전날 결과
# ══════════════════════════════════════════════════
def fetch_yesterday_results() -> list:
    data = fapi("/matches", {"competitions": "PL", "dateFrom": YESTERDAY, "dateTo": YESTERDAY})
    results = []
    for m in data.get("matches", []):
        if m.get("status") != "FINISHED":
            continue
        hs = m["score"]["fullTime"]["home"]
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
            "summary":    f"{at_kr} {as_} : {hs} {ht_kr}",
        })
    return results


# ══════════════════════════════════════════════════
# 4. 팀 시즌 스탯 (순위 + 폼)
# ══════════════════════════════════════════════════
_STANDINGS_CACHE = None

def fetch_standings() -> dict:
    global _STANDINGS_CACHE
    if _STANDINGS_CACHE is not None:
        return _STANDINGS_CACHE
    data = fapi("/competitions/PL/standings")
    stats = {}
    for entry in data.get("standings", [{}])[0].get("table", []):
        team_name = entry["team"]["name"]
        kr        = team_kr(team_name)
        stats[kr] = {
            "rank":   entry.get("position", "-"),
            "played": entry.get("playedGames", "-"),
            "won":    entry.get("won", "-"),
            "draw":   entry.get("draw", "-"),
            "lost":   entry.get("lost", "-"),
            "gf":     entry.get("goalsFor", 0),
            "ga":     entry.get("goalsAgainst", 0),
            "gd":     entry.get("goalDifference", 0),
            "pts":    entry.get("points", "-"),
            "form":   entry.get("form", "-"),
        }
    _STANDINGS_CACHE = stats
    return stats


# ══════════════════════════════════════════════════
# 5. 팀 최근 5경기 홈/원정 분리 폼
# ══════════════════════════════════════════════════
def fetch_team_form(team_id: int, team_kr_name: str) -> dict:
    time.sleep(6)  # 무료 플랜 rate limit (10 req/min)
    data = fapi(f"/teams/{team_id}/matches",
                {"status": "FINISHED", "limit": 10})
    home_r = away_r = []
    home_gf = home_ga = away_gf = away_ga = 0
    home_cnt = away_cnt = 0

    for m in data.get("matches", []):
        ht = m["homeTeam"]["name"]
        at = m["awayTeam"]["name"]
        hs = m["score"]["fullTime"].get("home")
        as_ = m["score"]["fullTime"].get("away")
        if hs is None or as_ is None:
            continue
        is_home = (ht == team_kr_name or team_kr(ht) == team_kr_name)
        my  = hs if is_home else as_
        opp = as_ if is_home else hs
        opp_name = team_kr(at) if is_home else team_kr(ht)

        symbol = "W" if my > opp else ("D" if my == opp else "L")
        detail = f"{opp_name} {my}:{opp}"

        if is_home and home_cnt < 5:
            home_r.append((symbol, detail))
            home_gf += my; home_ga += opp; home_cnt += 1
        elif not is_home and away_cnt < 5:
            away_r.append((symbol, detail))
            away_gf += my; away_ga += opp; away_cnt += 1

    def fmt(results):
        icons = {"W":"✅","D":"➖","L":"❌"}
        return " ".join(icons.get(r[0],"?") for r in results) or "-"

    return {
        "home_form":   fmt(home_r),
        "away_form":   fmt(away_r),
        "home_gf_avg": f"{home_gf/home_cnt:.1f}" if home_cnt else "-",
        "home_ga_avg": f"{home_ga/home_cnt:.1f}" if home_cnt else "-",
        "away_gf_avg": f"{away_gf/away_cnt:.1f}" if away_cnt else "-",
        "away_ga_avg": f"{away_ga/away_cnt:.1f}" if away_cnt else "-",
    }


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
        print(f"  ⚽ {akr} @ {hkr}")

        hs = standings.get(hkr, {})
        as_ = standings.get(akr, {})

        hf = fetch_team_form(m["home_id"], hkr)
        af = fetch_team_form(m["away_id"], akr)

        h_yd = next((r for r in yesterday if r["home_kr"]==hkr or r["away_kr"]==hkr), None)
        a_yd = next((r for r in yesterday if r["home_kr"]==akr or r["away_kr"]==akr), None)

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
        hf  = m["hf"]
        af  = m["af"]

        def yd_str(yd, team):
            if not yd: return "경기 없음"
            won = (yd["winner"] == team)
            return f"{yd['summary']} ({'승' if won else ('무' if yd['winner']=='무승부' else '패')})"

        h_rank = (f"{hs.get('rank','-')}위 "
                  f"{hs.get('pts','-')}pts "
                  f"({hs.get('won','-')}승{hs.get('draw','-')}무{hs.get('lost','-')}패) "
                  f"득{hs.get('gf','-')} 실{hs.get('ga','-')} 득실{hs.get('gd','-'):+}")
        a_rank = (f"{as_.get('rank','-')}위 "
                  f"{as_.get('pts','-')}pts "
                  f"({as_.get('won','-')}승{as_.get('draw','-')}무{as_.get('lost','-')}패) "
                  f"득{as_.get('gf','-')} 실{as_.get('ga','-')} 득실{as_.get('gd','-'):+}")

        blocks += f"""
━━━ 경기{i}: {akr} @ {hkr}  |  {m['kickoff']} KST  |  {m['matchday']}R ━━━
[순위]
  홈({hkr}): {h_rank}
  원정({akr}): {a_rank}
[전날({yesterday_date}) 결과]
  홈({hkr}): {yd_str(m['h_yd'], hkr)}
  원정({akr}): {yd_str(m['a_yd'], akr)}
[홈 폼 (최근5홈경기)] {hkr}: {hf.get('home_form','-')} / 홈 평균 득점 {hf.get('home_gf_avg','-')} 실점 {hf.get('home_ga_avg','-')}
[원정 폼 (최근5원정)] {akr}: {af.get('away_form','-')} / 원정 평균 득점 {af.get('away_gf_avg','-')} 실점 {af.get('away_ga_avg','-')}
"""

    return f"""당신은 15년 경력의 EPL 전문 축구 칼럼니스트입니다.
오늘({TODAY_KR}) EPL 경기 프리뷰를 한국어로 작성하세요.

[경기 데이터]
{blocks}

[작성 지침]
1. 모든 경기를 빠짐없이 전부 분석.
2. 각 경기를 독립적인 짧은 칼럼으로 서술.
3. 전날 결과로 오늘 경기 맥락 제시.
4. 순위 차이, 홈/원정 폼, 득실 수치를 스토리로 연결.
5. 홈 어드밴티지 vs 원정 강팀의 구도 구체적으로 서술.
6. 특정 선수명은 제공된 데이터에 있는 경우만 언급. 부상/이적 가능성이 있으므로 확인되지 않은 선수명 금지.
7. 마지막에 예상 결과(승/무/패) 명시.
8. 마크다운 기호(**) 절대 금지. 수치 나열 금지 — 스토리텔링 우선.
9. 각 경기 칼럼 300~400자 내외.

[형식]

⚽ {{원정}} @ {{홈}}  |  {{시간}} KST  {{라운드}}R

{{전날 흐름 복기}}

{{순위/폼 기반 전력 분석}}

{{홈어드밴티지 vs 원정폼 분석}}

오늘의 예상: {{홈승/무승부/원정승}}
{{핵심 근거 1~2문장}}

══════════════════════════════

마지막:
⭐ 오늘의 주목경기: {{경기명 + 이유}}
⚠️ 오늘의 변수: {{핵심 변수}}

══════════════════════════════
🔒 본 최종 분석은 VIP에게만 공유됩니다."""


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
        timeout=180,
    )
    if r.status_code != 200:
        print(f"  ⚠️ Claude API {r.status_code}")
        return "분석 생성 실패"
    return r.json()["content"][0]["text"]


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
            print(f"  ⚠️ 텔레그램 {r.status_code}: {r.text[:100]}")
            safe = re.sub(r"[<>&]", "", text)
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": safe},
                timeout=15)
    except Exception as e:
        print(f"  ⚠️ 발송 실패: {e}")

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
    print(f"[{TODAY_KR}] EPL 프리뷰 시작...")

    print("📡 전날 결과 수집...")
    yesterday = fetch_yesterday_results()
    print(f"  → {len(yesterday)}경기 결과")

    print("📡 오늘 경기 수집...")
    matches = fetch_today_matches()

    if not matches:
        print("오늘 EPL 경기 없음 — 발송 생략")
        return

    print(f"  → {len(matches)}경기")
    print("📊 데이터 보강...")
    enriched = enrich(matches, yesterday)

    print("🤖 Claude 칼럼 생성...")
    preview = call_claude(build_prompt(enriched))

    print("📨 발송...")
    header = (
        f"⚽ EPL 데일리 프리뷰\n"
        f"📅 {TODAY_KR}\n🕐 {NOW_KR}\n"
        f"{'─'*28}\n\n"
    )
    send_long(header + preview)
    print("🎉 완료!")


if __name__ == "__main__":
    main()
