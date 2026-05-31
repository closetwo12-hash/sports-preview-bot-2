"""
NPB Daily Preview Generator — 칼럼니스트 스타일 (v5 최종)

단일 소스 전략:
  npb.jp/announcement/starter/
    → 상단 링크: 오늘 경기 URL (팀코드·구장·시간 포함)
    → 하단 테이블: 예고선발 투수
  
  URL 팀코드 매핑으로 팀명 확정 (전각스페이스 파싱 불필요)
  전날 결과: 어제 MMDD로 같은 패턴 링크 필터링

  투수 스탯: npb.jp/bis/YYYY/stats/pit_c.html + pit_p.html
  순위:      npb.jp/bis/YYYY/stats/std_c.html + std_p.html
"""

import os, re, time, requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID  = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

KST      = timezone(timedelta(hours=9))
NOW_KST  = datetime.now(KST)
TODAY_KR = NOW_KST.strftime("%Y년 %m월 %d일")
NOW_KR   = NOW_KST.strftime("%Y년 %m월 %d일 %H:%M KST")
SEASON   = str(NOW_KST.year)
MMDD     = NOW_KST.strftime("%m%d")
YESTERDAY_MMDD = (NOW_KST - timedelta(days=1)).strftime("%m%d")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
SESS = requests.Session()
SESS.headers.update({
    "User-Agent": UA,
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Referer": "https://npb.jp/",
})

# ══════════════════════════════════════════════════════════════
# 팀 정보
# ══════════════════════════════════════════════════════════════
URL_CODE_KR = {
    "g":"요미우리","s":"야쿠르트","db":"DeNA",
    "d":"주니치","t":"한신","c":"히로시마",
    "h":"소프트뱅크","f":"닛폰햄","b":"오릭스",
    "e":"라쿠텐","l":"세이부","m":"롯데",
}
JP_TO_KR = {
    "読売ジャイアンツ":"요미우리","巨人":"요미우리",
    "東京ヤクルトスワローズ":"야쿠르트","ヤクルト":"야쿠르트",
    "横浜DeNAベイスターズ":"DeNA","DeNA":"DeNA","横浜":"DeNA",
    "中日ドラゴンズ":"주니치","中日":"주니치",
    "阪神タイガース":"한신","阪神":"한신",
    "広島東洋カープ":"히로시마","広島":"히로시마",
    "福岡ソフトバンクホークス":"소프트뱅크","ソフトバンク":"소프트뱅크",
    "北海道日本ハムファイターズ":"닛폰햄","日本ハム":"닛폰햄",
    "オリックス・バファローズ":"오릭스","オリックス":"오릭스",
    "東北楽天ゴールデンイーグルス":"라쿠텐","楽天":"라쿠텐",
    "埼玉西武ライオンズ":"세이부","西武":"세이부",
    "千葉ロッテマリーンズ":"롯데","ロッテ":"롯데",
}
TEAM_LEAGUE = {
    "요미우리":"CL","야쿠르트":"CL","DeNA":"CL",
    "주니치":"CL","한신":"CL","히로시마":"CL",
    "소프트뱅크":"PL","닛폰햄":"PL","오릭스":"PL",
    "라쿠텐":"PL","세이부":"PL","롯데":"PL",
}
CLOSER = {
    "요미우리":"오오시로 히로키","야쿠르트":"키시다 케이타","DeNA":"야마사키 코나",
    "주니치":"마쓰야마 타쿠미","한신":"이와사키 유키","히로시마":"이치다 나루키",
    "소프트뱅크":"오노 야스아키","닛폰햄":"야나기야 쇼타","오릭스":"아베 유이치로",
    "라쿠텐":"마쓰이 유키","세이부":"히라노 타카유키","롯데":"코마츠 켄야",
}
# 타선 정보: 하드코딩 제거 — Claude가 실제 기록 기반으로 서술
VENUE_MAP = {
    "東京ドーム":"도쿄돔","神 宮":"진구","神宮":"진구",
    "横 浜":"요코하마","バンテリン":"반테린돔","甲子園":"고시엔",
    "マツダ":"마쓰다","PayPay":"페이페이돔","みずほ":"페이페이돔",
    "エスコン":"ES CON FIELD","楽天モバイル":"라쿠텐모바일",
    "ZOZO":"ZOZO마린","ベルーナ":"베루나돔","京セラ":"교세라돔",
}

def jp_to_kr(s: str) -> str:
    s = s.strip()
    if s in JP_TO_KR: return JP_TO_KR[s]
    for k, v in JP_TO_KR.items():
        if k in s: return v
    return s

def venue_kr(s: str) -> str:
    for k, v in VENUE_MAP.items():
        if k in s: return v
    return s.strip()


# ══════════════════════════════════════════════════════════════
# 1. 핵심: starter 페이지에서 링크 파싱
#    모든 NPB 페이지 상단에 오늘 경기 링크가 동일하게 표시됨
#    형식: <a href="/scores/YYYY/MMDD/팀-팀-번호/">텍스트</a>
# ══════════════════════════════════════════════════════════════
_STARTER_SOUP = None

def _get_starter_soup() -> BeautifulSoup:
    global _STARTER_SOUP
    if _STARTER_SOUP:
        return _STARTER_SOUP
    # 여러 소스 순서대로 시도
    urls = [
        "https://npb.jp/announcement/starter/",
        f"https://npb.jp/games/{SEASON}/schedule_{NOW_KST.strftime('%m')}_detail.html",
        f"https://npb.jp/interleague/{SEASON}/schedule_detail.html",
    ]
    for url in urls:
        try:
            r = SESS.get(url, timeout=12)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text()
            # 오늘 날짜 링크가 있는 페이지 사용
            if MMDD in text or f"/scores/{SEASON}/{MMDD}/" in r.text:
                print(f"  ✅ NPB 소스: {url.split('/')[-1]}")
                _STARTER_SOUP = soup
                return _STARTER_SOUP
        except Exception as e:
            print(f"  ⚠️ {url.split('/')[-1]} 실패: {e}")
    # 못 찾았어도 첫 번째 페이지라도 사용
    try:
        r = SESS.get("https://npb.jp/announcement/starter/", timeout=12)
        _STARTER_SOUP = BeautifulSoup(r.text, "html.parser")
        print("  ⚠️ 오늘 경기 링크 없음 — starter 페이지 사용")
    except Exception as e:
        print(f"  ⚠️ NPB 페이지 전체 실패: {e}")
        _STARTER_SOUP = BeautifulSoup("", "html.parser")
    return _STARTER_SOUP


def _extract_games_from_links(soup: BeautifulSoup, mmdd: str) -> list:
    """
    페이지 상단 링크에서 특정 날짜의 경기 추출.
    href 패턴: /scores/YYYY/MMDD/홈-원정-번호/
    링크 텍스트: "팀명 팀명-（구장） 시간" 또는 종료시 스코어 포함
    """
    games   = []
    seen    = set()
    pattern = re.compile(rf"/scores/{SEASON}/{mmdd}/(\w+)-(\w+)-(\d+)/")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            href = "https://npb.jp" + href

        m = pattern.search(href)
        if not m:
            continue

        home_code = m.group(1)
        away_code = m.group(2)
        game_num  = m.group(3)
        key       = f"{home_code}-{away_code}-{game_num}"
        if key in seen:
            continue
        seen.add(key)

        home_kr = URL_CODE_KR.get(home_code, "")
        away_kr = URL_CODE_KR.get(away_code, "")
        if not home_kr or not away_kr:
            continue

        text = a.get_text(separator=" ", strip=True)

        # 구장
        venue = "-"
        for k, v in VENUE_MAP.items():
            if k in text:
                venue = v; break

        # 시간
        time_m   = re.search(r"(\d{1,2}:\d{2})", text)
        time_str = time_m.group(1) if time_m else "18:00"

        # 스코어 (종료 경기: "6-0" 형태, 시간과 구분하려면 ":" 없는 것)
        score_m   = re.search(r"\b(\d+)-(\d+)\b", text)
        finished  = score_m is not None
        home_score = int(score_m.group(1)) if score_m else None
        away_score = int(score_m.group(2)) if score_m else None

        games.append({
            "time":         time_str,
            "venue":        venue,
            "home":         home_kr,
            "away":         away_kr,
            "home_score":   home_score,
            "away_score":   away_score,
            "finished":     finished,
            "home_pitcher": "미정",
            "away_pitcher": "미정",
            "href":         href,
        })

    return games


# ══════════════════════════════════════════════════════════════
# 2. 예고선발 파싱 (starter 페이지 테이블)
# ══════════════════════════════════════════════════════════════
def _parse_starters(soup: BeautifulSoup) -> dict:
    """
    予告先発 페이지 선수 사진 링크 (/bis/players/ID.html) 에서
    선수 페이지 <title> 파싱 → 투수명 + 팀명 추출.
    title 형식: "戸郷\u3000翔征（読売ジャイアンツ） | 個人年度別成績"
    """
    starters   = {}
    player_ids = []

    for a in soup.find_all("a", href=True):
        m = re.search(r"/bis/players/(\d+)\.html", a["href"])
        if m:
            pid = m.group(1)
            if pid not in player_ids:
                player_ids.append(pid)

    print(f"  예고선발 선수 ID {len(player_ids)}명")

    for pid in player_ids:
        try:
            r = SESS.get(f"https://npb.jp/bis/players/{pid}.html", timeout=8)
            if r.status_code != 200:
                continue
            title_m = re.search(r"<title>([^<]+)</title>", r.text)
            if not title_m:
                continue
            title = title_m.group(1).strip()
            # "戸郷　翔征（読売ジャイアンツ）" 형태 파싱
            # 全角괄호（）또는 半角괄호() 모두 처리
            nm = re.match(r"^(.+?)[\uff08(](.+?)[\uff09)]", title)
            if not nm:
                continue
            name    = re.sub(r"[\u3000\s]+", " ", nm.group(1)).strip()
            team_jp = nm.group(2).strip()
            team_kr = jp_to_kr(team_jp)
            if team_kr in TEAM_LEAGUE and name:
                starters[team_kr] = name
                print(f"    {team_kr}: {name}")
            time.sleep(0.2)
        except Exception as e:
            print(f"  선수({pid}) 파싱 실패: {e}")

    return starters
def fetch_schedule() -> list:
    print(f"  NPB 오늘({MMDD}) 경기 수집...")
    soup  = _get_starter_soup()
    games = _extract_games_from_links(soup, MMDD)

    # 예고선발 적용
    starters = _parse_starters(soup)
    print(f"  예고선발 {len(starters)}팀: {starters}")
    for g in games:
        g["home_pitcher"] = starters.get(g["home"], "미정")
        g["away_pitcher"] = starters.get(g["away"], "미정")

    print(f"  ✅ {len(games)}경기")
    return games


def fetch_yesterday_results() -> list:
    print(f"  NPB 전날({YESTERDAY_MMDD}) 결과 수집...")
    soup    = _get_starter_soup()  # 같은 페이지 재사용
    games   = _extract_games_from_links(soup, YESTERDAY_MMDD)
    results = []
    for g in games:
        if not g["finished"]:
            continue
        hs, vs = g["home_score"], g["away_score"]
        winner = g["home"] if hs > vs else (g["away"] if vs > hs else "무")
        results.append({
            "home": g["home"], "away": g["away"],
            "home_score": hs,  "away_score": vs,
            "winner": winner,
            "summary": f"{g['away']} {vs} : {hs} {g['home']}",
        })
    print(f"  → {len(results)}경기 결과")
    return results


# ══════════════════════════════════════════════════════════════
# 4. 팀 스탯 (영문 공식 사이트)
# ══════════════════════════════════════════════════════════════
ENG_PARTIAL = {
    "Yomiuri":"요미우리","Yakult":"야쿠르트","DeNA":"DeNA","Chunichi":"주니치",
    "Hanshin":"한신","Hiroshima":"히로시마","SoftBank":"소프트뱅크",
    "Softbank":"소프트뱅크","Nippon-Ham":"닛폰햄","ORIX":"오릭스","Orix":"오릭스",
    "Rakuten":"라쿠텐","Seibu":"세이부","Lotte":"롯데",
}

def _eng_to_kr(s: str) -> str:
    for k, v in ENG_PARTIAL.items():
        if k.lower() in s.lower(): return v
    return ""


def fetch_all_team_stats() -> dict:
    stats = {}
    for lc, lg in [("c","CL"),("p","PL")]:
        try:
            r    = SESS.get(f"https://npb.jp/bis/eng/{SEASON}/stats/std_{lc}.html", timeout=12)
            soup = BeautifulSoup(r.text, "html.parser")
            for row in soup.select("table tbody tr"):
                cols = row.select("td")
                if len(cols) < 6: continue
                kr = _eng_to_kr(cols[0].get_text(strip=True))
                if not kr: continue
                stats.setdefault(kr, {}).update({
                    "win":    cols[2].get_text(strip=True),
                    "lose":   cols[3].get_text(strip=True),
                    "draw":   cols[4].get_text(strip=True),
                    "wpct":   cols[5].get_text(strip=True),
                    "gb":     cols[6].get_text(strip=True) if len(cols)>6 else "-",
                    "league": lg,
                })
        except Exception as e: print(f"  순위({lc}) 실패: {e}")

    for lc in ["c","p"]:
        try:
            r    = SESS.get(f"https://npb.jp/bis/eng/{SEASON}/stats/pit_{lc}.html", timeout=12)
            soup = BeautifulSoup(r.text, "html.parser")
            bkt: dict = {}
            for row in soup.select("table tbody tr"):
                cols = row.select("td")
                if len(cols) < 9: continue
                kr = _eng_to_kr(cols[2].get_text(strip=True))
                if not kr: continue
                try:
                    ip  = float(re.sub(r"[^\d.]","",cols[7].get_text()) or 0)
                    era = float(cols[8].get_text(strip=True))
                    if ip > 0:
                        a,b = bkt.get(kr,(0.0,0.0)); bkt[kr]=(a+ip*era,b+ip)
                except: pass
            for kr,(w,t) in bkt.items():
                stats.setdefault(kr,{}); stats[kr]["era"]=f"{w/t:.2f}" if t>0 else "-"
        except Exception as e: print(f"  팀ERA({lc}) 실패: {e}")

    for lc in ["c","p"]:
        try:
            r    = SESS.get(f"https://npb.jp/bis/eng/{SEASON}/stats/bat_{lc}.html", timeout=12)
            soup = BeautifulSoup(r.text, "html.parser")
            ob: dict = {}
            for row in soup.select("table tbody tr"):
                cols = row.select("td")
                if len(cols) < 15: continue
                kr = _eng_to_kr(cols[2].get_text(strip=True))
                if not kr: continue
                try: ob.setdefault(kr,[]).append(float(cols[14].get_text(strip=True)))
                except: pass
            for kr,lst in ob.items():
                stats.setdefault(kr,{}); stats[kr]["ops"]=f"{sum(lst)/len(lst):.3f}"
        except Exception as e: print(f"  팀OPS({lc}) 실패: {e}")

    return stats


# ══════════════════════════════════════════════════════════════
# 5. 투수 개인 스탯 캐시
# ══════════════════════════════════════════════════════════════
_PITCHER_CACHE: dict = {}

def _load_pitcher_cache():
    if _PITCHER_CACHE: return
    for lc in ["c","p"]:
        try:
            r    = SESS.get(f"https://npb.jp/bis/eng/{SEASON}/stats/pit_{lc}.html", timeout=12)
            soup = BeautifulSoup(r.text, "html.parser")
            for row in soup.select("table tbody tr"):
                cols = row.select("td")
                if len(cols) < 9: continue
                # 이름 셀에서 텍스트 + 링크(선수ID) 추출
                name_td = cols[1]
                name    = name_td.get_text(strip=True)
                if not name: continue
                # 선수 ID 추출 (href="/bis/players/41045138.html")
                pid_link = name_td.find("a", href=True)
                pid      = ""
                if pid_link:
                    pm = re.search(r"/bis/players/(\d+)\.html", pid_link["href"])
                    if pm: pid = pm.group(1)
                ip_f = float(re.sub(r"[^\d.]","",cols[7].get_text()) or 0)
                k_f  = float(re.sub(r"\D","",cols[11].get_text()) or 0) if len(cols)>11 else 0
                bb_f = float(re.sub(r"\D","",cols[12].get_text()) or 0) if len(cols)>12 else 0
                stat = {
                    "w":    cols[3].get_text(strip=True) if len(cols)>3 else "-",
                    "l":    cols[4].get_text(strip=True) if len(cols)>4 else "-",
                    "era":  cols[8].get_text(strip=True) if len(cols)>8 else "-",
                    "whip": cols[9].get_text(strip=True) if len(cols)>9 else "-",
                    "ip":   cols[7].get_text(strip=True),
                    "k9":   f"{k_f/ip_f*9:.1f}" if ip_f>0 else "-",
                    "bb9":  f"{bb_f/ip_f*9:.1f}" if ip_f>0 else "-",
                    "pid":  pid,
                }
                _PITCHER_CACHE[name] = stat
                if pid:
                    _PITCHER_CACHE[pid] = stat   # ID로도 검색 가능
        except Exception as e: print(f"  투수캐시({lc}) 실패: {e}")


def fetch_pitcher_stat(name: str) -> dict:
    """투수명 또는 선수 ID로 시즌 스탯 조회"""
    empty = {"era":"-","whip":"-","w":"-","l":"-","ip":"-","k9":"-","bb9":"-","pid":""}
    if name in ("미정","","-"): return empty
    _load_pitcher_cache()
    # 이름 직접 매칭
    if name in _PITCHER_CACHE: return _PITCHER_CACHE[name]
    # 일본어 이름 부분 매칭 (全角스페이스 포함 변형 대응)
    name_clean = re.sub(r"[　\s]+", " ", name).strip()
    for k, v in _PITCHER_CACHE.items():
        k_clean = re.sub(r"[　\s]+", " ", k).strip()
        if name_clean == k_clean or name_clean in k_clean or k_clean in name_clean:
            return v
    return empty


# ══════════════════════════════════════════════════════════════
# 6. 최근 5경기 폼 (starter 페이지 + 이전 날짜 순회)
# ══════════════════════════════════════════════════════════════
def fetch_recent_form(team: str) -> tuple:
    finished_games = []
    soup = _get_starter_soup()

    # starter 페이지에 보이는 모든 날짜의 경기 수집
    all_links = soup.find_all("a", href=True)
    score_pattern = re.compile(rf"/scores/{SEASON}/(\d{{4}})/(\w+)-(\w+)-\d+/")

    seen = set()
    for a in all_links:
        href = a["href"]
        if not href.startswith("http"):
            href = "https://npb.jp" + href
        m = score_pattern.search(href)
        if not m: continue
        mmdd_link = m.group(1)
        if mmdd_link == MMDD: continue  # 오늘 제외
        if mmdd_link in seen: continue
        seen.add(mmdd_link + m.group(2) + m.group(3))

        home_kr = URL_CODE_KR.get(m.group(2), "")
        away_kr = URL_CODE_KR.get(m.group(3), "")
        if team not in (home_kr, away_kr): continue

        text    = a.get_text(separator=" ", strip=True)
        score_m = re.search(r"\b(\d+)-(\d+)\b", text)
        if not score_m: continue

        hs = int(score_m.group(1)); vs = int(score_m.group(2))
        is_home = (team == home_kr)
        opp_kr  = away_kr if is_home else home_kr
        my  = hs if is_home else vs
        opp = vs if is_home else hs

        if my > opp:   finished_games.append(("✅", f"{opp_kr} 승({my}:{opp})"))
        elif my < opp: finished_games.append(("❌", f"{opp_kr} 패({my}:{opp})"))
        else:          finished_games.append(("➖", f"{opp_kr} 무({my}:{opp})"))

        if len(finished_games) >= 5: break

    last5 = finished_games[:5]
    return (" ".join(x[0] for x in last5) if last5 else "-"), [x[1] for x in last5]


# ══════════════════════════════════════════════════════════════
# 7. 불펜 피로도
# ══════════════════════════════════════════════════════════════
def fetch_bullpen_fatigue(team: str) -> dict:
    closer  = CLOSER.get(team, "정보없음")
    fatigue = {"closer": closer, "close_games": 0, "status": "확인불가"}
    soup    = _get_starter_soup()
    close_count   = 0
    checked_dates = set()

    score_pattern = re.compile(rf"/scores/{SEASON}/(\d{{4}})/(\w+)-(\w+)-\d+/")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            href = "https://npb.jp" + href
        m = score_pattern.search(href)
        if not m: continue
        mmdd_link = m.group(1)
        if mmdd_link == MMDD: continue
        home_kr = URL_CODE_KR.get(m.group(2), "")
        away_kr = URL_CODE_KR.get(m.group(3), "")
        if team not in (home_kr, away_kr): continue
        text    = a.get_text(separator=" ", strip=True)
        score_m = re.search(r"\b(\d+)-(\d+)\b", text)
        if not score_m: continue
        diff = abs(int(score_m.group(1)) - int(score_m.group(2)))
        if mmdd_link not in checked_dates and len(checked_dates) < 3:
            checked_dates.add(mmdd_link)
            if diff <= 2:
                close_count += 1

    fatigue["close_games"] = close_count
    if close_count == 0:
        fatigue["status"] = f"✅ {closer} 정상 예상"
    elif close_count == 1:
        fatigue["status"] = f"⚠️ {closer} 접전 1경기 등판 가능"
    else:
        fatigue["status"] = f"🔴 {closer} {close_count}경기 접전 연속 (소진 위험)"
    return fatigue


# ══════════════════════════════════════════════════════════════
# 8. 데이터 보강
# ══════════════════════════════════════════════════════════════
def enrich(games: list, yesterday_results: list) -> list:
    print("  팀 스탯 수집...")
    all_stats = fetch_all_team_stats()
    print("  투수 스탯 캐시...")
    _load_pitcher_cache()

    result = []
    for g in games:
        h, a = g["home"], g["away"]
        print(f"  📊 {a} @ {h}")
        hs   = all_stats.get(h, {})
        as_  = all_stats.get(a, {})
        hp   = fetch_pitcher_stat(g["home_pitcher"])
        ap   = fetch_pitcher_stat(g["away_pitcher"])
        hf, hf_d = fetch_recent_form(h)
        af, af_d = fetch_recent_form(a)
        hbull = fetch_bullpen_fatigue(h)
        abull = fetch_bullpen_fatigue(a)
        h_yd = next((r for r in yesterday_results if r["home"]==h or r["away"]==h), None)
        a_yd = next((r for r in yesterday_results if r["home"]==a or r["away"]==a), None)
        result.append({
            **g,
            "hs":hs,"as_":as_,"hp":hp,"ap":ap,
            "hf":hf,"hf_detail":hf_d,"af":af,"af_detail":af_d,
            "hbull":hbull,"abull":abull,
            "h_yesterday":h_yd,"a_yesterday":a_yd,
        })
    return result


# ══════════════════════════════════════════════════════════════
# 9. Claude 프롬프트
# ══════════════════════════════════════════════════════════════
def build_prompt(games: list) -> str:
    yesterday_date = (NOW_KST - timedelta(days=1)).strftime("%m월 %d일")
    blocks = ""
    for i, g in enumerate(games, 1):
        h, a = g["home"], g["away"]
        def yd_str(yd, team):
            if not yd: return "경기 없음"
            return f"{yd['summary']} ({'승' if yd['winner']==team else '패'})"
        hs=g["hs"]; as_=g["as_"]
        h_lg=hs.get("league",TEAM_LEAGUE.get(h,"?"))
        a_lg=as_.get("league",TEAM_LEAGUE.get(a,"?"))
        h_rank=(f"[{h_lg}] {hs.get('win','-')}승{hs.get('lose','-')}패{hs.get('draw','0')}무"
                f" (승률 {hs.get('wpct','-')}) ERA {hs.get('era','-')} OPS {hs.get('ops','-')}")
        a_rank=(f"[{a_lg}] {as_.get('win','-')}승{as_.get('lose','-')}패{as_.get('draw','0')}무"
                f" (승률 {as_.get('wpct','-')}) ERA {as_.get('era','-')} OPS {as_.get('ops','-')}")
        blocks += f"""
━━━ 경기{i}: {a} @ {h}  |  {g['time']} JST  |  {g['venue']} ━━━
[팀 현황] 홈({h}): {h_rank}  /  원정({a}): {a_rank}
[전날({yesterday_date})] 홈: {yd_str(g['h_yesterday'],h)}  /  원정: {yd_str(g['a_yesterday'],a)}
[선발] 홈 {g['home_pitcher']}: ERA {g['hp']['era']} WHIP {g['hp']['whip']} K/9 {g['hp']['k9']} ({g['hp']['w']}승{g['hp']['l']}패)
       원정 {g['away_pitcher']}: ERA {g['ap']['era']} WHIP {g['ap']['whip']} K/9 {g['ap']['k9']} ({g['ap']['w']}승{g['ap']['l']}패)
[타선] 홈({h}): OPS {hs.get('ops','-')} / ERA {hs.get('era','-')}
       원정({a}): OPS {as_.get('ops','-')} / ERA {as_.get('era','-')}
[불펜] 홈: {g['hbull']['status']}  /  원정: {g['abull']['status']}
[최근5경기] 홈: {g['hf']}  /  원정: {g['af']}
"""

    return f"""당신은 15년 경력의 NPB 전문 야구 칼럼니스트입니다.
오늘({TODAY_KR}) NPB 경기 프리뷰를 한국어로 작성하세요.

[경기 데이터]
{blocks}

[작성 지침]
1. NPB를 잘 아는 한국 야구팬 독자 대상.
2. 각 경기를 독립적인 짧은 칼럼으로.
3. 전날 결과 복기로 오늘 경기 맥락 제시.
4. 선발투수 분석 (필수):
   - 제공된 이름·ERA·WHIP·K/9·BB/9·승패 기록을 반드시 활용
   - 최근 컨디션 흐름을 스토리로 서술 (ERA 수준으로 오늘 기대치 판단)
   - 좌완/우완 여부와 상대 타선 구성의 유불리 연결
   - 데이터가 '-'인 경우 '정보 미확인'으로 처리, 억측 금지
   - 선발투수명이 '미정'인 경우: '선발 미공시'로 표기하고 팀 ERA 기반으로 마운드 상태 추정 서술
5. 타선 상성: 선발 손방향과 좌/우 구성 유불리 구체적으로.
6. 불펜/마무리는 하드코딩 정보 무시 — 제공된 최근 접전경기·실제 기록만으로 판단해 서술.
7. 구장 특성(도쿄돔 홈런, 고시엔 외야 등) 자연스럽게.
8. 모든 경기를 빠짐없이 전부 분석.
9. 마지막에 예상 승리팀 명시.
11. 투수/타자 특정 선수 이름은 제공된 예고선발·데이터에 있는 경우만 언급. 부상·이적·방출 가능성이 있으므로 확인되지 않은 선수명 언급 금지.
10. 마크다운 기호 절대 금지. 수치 나열 금지 — 스토리텔링 우선.
11. 각 경기 칼럼 300~400자.

[형식]
⚾ {{원정}} @ {{홈}}  |  {{시간}} JST  {{구장}}
{{전날 흐름 복기}}
{{선발 매치업 — 손방향·컨디션}}
{{타선 상성}}
{{불펜 피로도}}
오늘의 예상: {{승리팀}} 우세
{{핵심 근거 1~2문장}}
══════════════════════════════
마지막:
⭐ 오늘의 주목경기: {{경기명 + 이유}}
🎯 오늘의 주목 선발: {{투수명 + 기대 포인트}}
⚠️ 오늘의 변수: {{핵심 변수}}
══════════════════════════════
🔒 본 최종 분석은 VIP에게만 공유됩니다."""


def call_claude(prompt: str) -> str:
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},
        json={"model":"claude-sonnet-4-6","max_tokens":4096,"messages":[{"role":"user","content":prompt}]},
        timeout=120,
    )
    if r.status_code != 200:
        print(f"  ⚠️ Claude API {r.status_code}")
        return "분석 생성 실패"
    data = r.json()
    if not data.get("content"):
        return "Claude 응답 비어있음"
    return data["content"][0]["text"]


# ══════════════════════════════════════════════════════════════
# 10. 텔레그램
# ══════════════════════════════════════════════════════════════
def clean(t):
    t=re.sub(r'\*\*(.+?)\*\*',r'\1',t); t=re.sub(r'\*(.+?)\*',r'\1',t)
    t=re.sub(r'__(.+?)__',r'\1',t);     t=re.sub(r'\n{3,}','\n\n',t)
    return t.strip()

def send_msg(text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id":TELEGRAM_CHAT_ID,"text":text},timeout=15)

def send_long(text):
    text=clean(text); MAX=3800
    if len(text)<=MAX: send_msg(text); print("✅ 발송"); return
    parts=[p.strip() for p in re.split(r'══+',text) if p.strip()]
    chunk=""; n=1
    for p in parts:
        cand=chunk+"\n\n"+p if chunk else p
        if len(cand)>MAX:
            if chunk: send_msg(chunk); print(f"✅ {n}번"); n+=1
            chunk=p
        else: chunk=cand
    if chunk: send_msg(chunk); print(f"✅ {n}번")


# ══════════════════════════════════════════════════════════════
# 11. 메인
# ══════════════════════════════════════════════════════════════
def main():
    print(f"[{TODAY_KR}] NPB 프리뷰 시작 (오늘 MMDD={MMDD})...")

    print("📡 전날 결과 수집...")
    yesterday_results = fetch_yesterday_results()

    print("📡 오늘 경기 수집...")
    games = fetch_schedule()

    if not games:
        send_msg(f"⚾ NPB 데일리 프리뷰\n📅 {TODAY_KR}\n🕐 {NOW_KR}\n\n오늘은 NPB 경기가 없습니다. 🌙")
        print("경기 없음"); return

    print(f"  → {len(games)}경기")
    print("📊 데이터 보강...")
    enriched = enrich(games, yesterday_results)

    print("🤖 Claude 칼럼 생성...")
    preview = call_claude(build_prompt(enriched))

    print("📨 발송...")
    header = f"⚾ NPB 데일리 프리뷰\n📅 {TODAY_KR}\n🕐 {NOW_KR}\n{'─'*28}\n\n"
    send_long(header + preview)
    print("🎉 완료!")


if __name__ == "__main__":
    main()
