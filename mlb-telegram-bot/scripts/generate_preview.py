"""
MLB Daily Preview Generator — 칼럼니스트 스타일
분석 방향:
  - 전날 경기 결과 복기
  - 투수 최근 3~5경기 등판 패턴 서술
  - 좌타/우타 상성 구체 언급
  - 불펜 피로도 & 위기관리 능력 서술
  - 스토리텔링 중심 (딱딱한 수치 나열 X)
  - 예상 승리팀 명시
"""

import os, io, time
import re, math, requests
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID  = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

KST       = timezone(timedelta(hours=9))
_KST_NOW  = datetime.now(KST)
TODAY     = _KST_NOW.strftime("%Y-%m-%d")          # KST 기준 오늘
YESTERDAY = (_KST_NOW - timedelta(days=1)).strftime("%Y-%m-%d")  # KST 기준 어제
TODAY_KR  = _KST_NOW.strftime("%Y년 %m월 %d일")
NOW_KR    = _KST_NOW.strftime("%Y년 %m월 %d일 %H:%M KST")
SEASON    = _KST_NOW.year

# ══════════════════════════════════════════════════════════════
# 번역 테이블
# ══════════════════════════════════════════════════════════════
TEAM_KR = {
    "New York Yankees":"뉴욕 양키스","Boston Red Sox":"보스턴 레드삭스",
    "Los Angeles Dodgers":"LA 다저스","San Francisco Giants":"샌프란시스코 자이언츠",
    "Houston Astros":"휴스턴 애스트로스","Atlanta Braves":"애틀랜타 브레이브스",
    "New York Mets":"뉴욕 메츠","Philadelphia Phillies":"필라델피아 필리스",
    "Toronto Blue Jays":"토론토 블루제이스","Baltimore Orioles":"볼티모어 오리올스",
    "Tampa Bay Rays":"탬파베이 레이스","Chicago White Sox":"시카고 화이트삭스",
    "Chicago Cubs":"시카고 컵스","Cleveland Guardians":"클리블랜드 가디언스",
    "Detroit Tigers":"디트로이트 타이거스","Kansas City Royals":"캔자스시티 로열스",
    "Minnesota Twins":"미네소타 트윈스","Milwaukee Brewers":"밀워키 브루어스",
    "St. Louis Cardinals":"세인트루이스 카디널스","Cincinnati Reds":"신시내티 레즈",
    "Pittsburgh Pirates":"피츠버그 파이리츠","Colorado Rockies":"콜로라도 로키스",
    "Arizona Diamondbacks":"애리조나 다이아몬드백스","Los Angeles Angels":"LA 에인절스",
    "Oakland Athletics":"오클랜드 애슬레틱스","Seattle Mariners":"시애틀 매리너스",
    "Texas Rangers":"텍사스 레인저스","San Diego Padres":"샌디에이고 파드리스",
    "Miami Marlins":"마이애미 말린스","Washington Nationals":"워싱턴 내셔널스",
    "Athletics":"오클랜드 애슬레틱스",
}
PLAYER_KR = {
    "Gerrit Cole":"게릿 콜","Carlos Rodon":"카를로스 로돈","Luis Severino":"루이스 세베리노",
    "Clarke Schmidt":"클라크 슈미트","Juan Soto":"후안 소토","Aaron Judge":"에런 저지",
    "Giancarlo Stanton":"지안카를로 스탠턴","Tanner Houck":"태너 하우크",
    "Garrett Crochet":"개럿 크로셰","Brayan Bello":"브라이안 베요",
    "Rafael Devers":"라파엘 데버스","Triston Casas":"트리스턴 카사스",
    "Yoshinobu Yamamoto":"야마모토 요시노부","Walker Buehler":"워커 뷸러",
    "Tyler Glasnow":"타일러 글래스나우","Shohei Ohtani":"오타니 쇼헤이",
    "Freddie Freeman":"프레디 프리먼","Mookie Betts":"무키 베츠",
    "Logan Webb":"로건 웹","Kyle Harrison":"카일 해리슨",
    "Framber Valdez":"프램버 발데스","Hunter Brown":"헌터 브라운",
    "Jose Altuve":"호세 알투베","Yordan Alvarez":"요르단 알바레스",
    "Chris Sale":"크리스 세일","Spencer Strider":"스펜서 스트라이더",
    "Ronald Acuna Jr.":"로날드 아쿠냐 주니어","Matt Olson":"맷 올슨",
    "Kodai Senga":"센가 고다이","Sean Manaea":"숀 마나이아","Pete Alonso":"피트 알론소",
    "Zack Wheeler":"잭 휠러","Aaron Nola":"아론 놀라","Bryce Harper":"브라이스 하퍼",
    "Trea Turner":"트레아 터너","Jose Berrios":"호세 베리오스",
    "Kevin Gausman":"케빈 가우스만","Vladimir Guerrero Jr.":"블라디미르 게레로 주니어",
    "Bo Bichette":"보 비쳇","Shane Bieber":"셰인 비버","Tanner Bibee":"태너 비비",
    "Jose Ramirez":"호세 라미레스","Tarik Skubal":"타릭 스쿠발",
    "Jack Flaherty":"잭 플래허티","Cole Ragans":"콜 레이건스",
    "Bobby Witt Jr.":"바비 윗 주니어","Pablo Lopez":"파블로 로페스",
    "Joe Ryan":"조 라이언","Carlos Correa":"카를로스 코레아",
    "Freddy Peralta":"프레디 페랄타","Corbin Burnes":"코빈 번스",
    "Miles Mikolas":"마일스 미콜라스","Sonny Gray":"소니 그레이",
    "Nolan Arenado":"놀란 아레나도","Nathan Eovaldi":"네이선 이오발디",
    "Jon Gray":"존 그레이","Corey Seager":"코리 시거",
    "Luis Castillo":"루이스 카스티요","George Kirby":"조지 커비",
    "Julio Rodriguez":"줄리오 로드리게스","Dylan Cease":"딜런 시스",
    "Michael King":"마이클 킹","Fernando Tatis Jr.":"페르난도 타티스 주니어",
    "Manny Machado":"매니 마차도","Patrick Sandoval":"패트릭 샌도발",
    "Reid Detmers":"리드 뎃머스","Kyle Freeland":"카일 프릴랜드",
    "Zac Gallen":"잭 갈렌","Merrill Kelly":"메릴 켈리","Ketel Marte":"케텔 마르테",
    "Jesus Luzardo":"헤수스 루사르도","Sandy Alcantara":"샌디 알칸타라",
    "MacKenzie Gore":"매켄지 고어","Zach Eflin":"잭 에플린",
    "Gunnar Henderson":"거나 헨더슨","Shane McClanahan":"셰인 맥클래너핸",
    "Justin Steele":"저스틴 스틸","Marcus Stroman":"마커스 스트로먼",
    "Shota Imanaga":"이마나가 쇼타","Ian Happ":"이언 해프",
    "Hunter Greene":"헌터 그린","Mitch Keller":"미치 켈러",
    "Paul Blackburn":"폴 블랙번","JP Sears":"JP 시어스",
    "Corbin Carroll":"코빈 캐롤","Paul Skenes":"폴 스킨스",
    "Erick Fedde":"에릭 페디",
}

def team_kr(n):   return TEAM_KR.get(n, n)
def player_kr(n): return PLAYER_KR.get(n, n)

# ══════════════════════════════════════════════════════════════
# 1. 공통 API 헬퍼
# ══════════════════════════════════════════════════════════════
BASE = "https://statsapi.mlb.com/api/v1"

def mlb_get(path, params=None, timeout=15):
    try:
        r = requests.get(BASE + path, params=params or {}, timeout=timeout)
        if r.status_code != 200:
            print(f"  ⚠️ MLB API {r.status_code}: {path}")
            return {}
        return r.json()
    except Exception as e:
        print(f"  ⚠️ MLB API 오류({path}): {e}")
        return {}

# ══════════════════════════════════════════════════════════════
# 2. 전날 경기 결과 수집
# ══════════════════════════════════════════════════════════════
def fetch_yesterday_results():
    """전날 MLB 경기 결과 수집"""
    results = []
    try:
        data = mlb_get("/schedule", {
            "sportId": 1, "date": YESTERDAY,
            "hydrate": "decisions,linescore,team",
        })
        for db in data.get("dates", []):
            for g in db.get("games", []):
                status = g.get("status", {}).get("abstractGameState", "")
                if status != "Final":
                    continue
                home = g["teams"]["home"]
                away = g["teams"]["away"]
                hn   = team_kr(home["team"]["name"])
                an   = team_kr(away["team"]["name"])
                hs   = home.get("score", "-")
                as_  = away.get("score", "-")
                winner_side = "home" if home.get("isWinner") else "away"
                winner = hn if winner_side == "home" else an

                # 결정 투수
                decisions = g.get("decisions", {})
                winning_p = player_kr(decisions.get("winner", {}).get("fullName", ""))
                losing_p  = player_kr(decisions.get("loser",  {}).get("fullName", ""))
                save_p    = player_kr(decisions.get("save",   {}).get("fullName", ""))

                results.append({
                    "gamePk":   g["gamePk"],
                    "home":     hn,
                    "away":     an,
                    "home_id":  home["team"]["id"],
                    "away_id":  away["team"]["id"],
                    "home_score": hs,
                    "away_score": as_,
                    "winner":   winner,
                    "winning_pitcher": winning_p,
                    "losing_pitcher":  losing_p,
                    "save_pitcher":    save_p,
                    "summary":  f"{an} {as_} : {hs} {hn}",
                })
    except Exception as e:
        print(f"  전날결과 수집 실패: {e}")
    return results


# ══════════════════════════════════════════════════════════════
# 3. 오늘 경기 일정 수집
# ══════════════════════════════════════════════════════════════
def _pitcher_info(side):
    pp = side.get("probablePitcher", {})
    if not pp:
        return {"id": None, "name": "미정", "name_kr": "미정",
                "era": "-", "whip": "-", "throws": "?"}
    nm = pp.get("fullName", "미정")
    return {
        "id":      pp.get("id"),
        "name":    nm,
        "name_kr": player_kr(nm),
        "throws":  pp.get("pitchHand", {}).get("code", "?"),
        "era":     "-", "whip": "-",
    }


def _parse_lineup(side):
    lp = side.get("lineup", [])
    return [
        {"name_kr": player_kr(p.get("fullName", "")),
         "bat_side": p.get("batSide", {}).get("code", "?")}
        for p in lp if p.get("fullName")
    ]


def fetch_todays_games():
    data = mlb_get("/schedule", {
        "sportId": 1, "date": TODAY,
        "hydrate": "probablePitcher,team,venue,lineups",
    })
    games = []
    for db in data.get("dates", []):
        for g in db.get("games", []):
            if g.get("status", {}).get("abstractGameState", "") == "Final":
                continue
            home = g["teams"]["home"]
            away = g["teams"]["away"]

            try:
                dt     = datetime.fromisoformat(g.get("gameDate", "").replace("Z", "+00:00"))
                dt_kst = dt.astimezone(KST)
                # 날짜 차이 계산
                now_kst = datetime.now(KST)
                delta   = (dt_kst.date() - now_kst.date()).days
                if delta == 0:
                    date_label = "오늘"
                elif delta == 1:
                    date_label = "내일"
                else:
                    date_label = f"{dt_kst.month}/{dt_kst.day}"
                time_kst = f"{date_label} {dt_kst.strftime('%H:%M')} KST"
            except:
                time_kst = "-"

            hn, an = home["team"]["name"], away["team"]["name"]
            games.append({
                "gamePk":        g["gamePk"],
                "game_date_utc": g.get("gameDate",""),
                "time_kst": time_kst,
                "venue":    g.get("venue", {}).get("name", "-"),
                "home": {
                    "id":      home["team"]["id"],
                    "name":    hn, "name_kr": team_kr(hn),
                    "abbr":    home["team"]["abbreviation"],
                    "pitcher": _pitcher_info(home),
                    "lineup":  _parse_lineup(home),
                },
                "away": {
                    "id":      away["team"]["id"],
                    "name":    an, "name_kr": team_kr(an),
                    "abbr":    away["team"]["abbreviation"],
                    "pitcher": _pitcher_info(away),
                    "lineup":  _parse_lineup(away),
                },
            })
    return sorted(games, key=lambda x: x.get("game_date_utc",""))


# ══════════════════════════════════════════════════════════════
# 4. 팀 시즌 스탯
# ══════════════════════════════════════════════════════════════
# 스탠딩 캐시 (API 호출 최소화)
_STANDINGS_CACHE = {}

def fetch_standings_cache():
    global _STANDINGS_CACHE
    if _STANDINGS_CACHE:
        return _STANDINGS_CACHE
    try:
        data = mlb_get("/standings", {
            "leagueId": "103,104",  # AL, NL
            "season": SEASON,
            "standingsTypes": "regularSeason",
        })
        for record in data.get("records", []):
            div_name = record.get("division", {}).get("nameShort", "")
            for tr in record.get("teamRecords", []):
                tid = tr["team"]["id"]
                _STANDINGS_CACHE[tid] = {
                    "wins":   tr.get("wins", "-"),
                    "losses": tr.get("losses", "-"),
                    "pct":    tr.get("winningPercentage", "-"),
                    "rank":   tr.get("divisionRank", "-"),
                    "div":    div_name,
                    "gb":     tr.get("gamesBack", "-"),
                }
    except Exception as e:
        print(f"  스탠딩 수집 실패: {e}")
    return _STANDINGS_CACHE


def fetch_team_season_stats(team_id):
    try:
        data = mlb_get(f"/teams/{team_id}/stats",
                       {"stats": "season", "group": "hitting,pitching", "season": SEASON})
        rs, ra, ops, era, avg = 0, 0, "-", "-", "-"
        for blk in data.get("stats", []):
            grp = blk.get("group", {}).get("displayName", "")
            sp  = blk.get("splits", [{}])[0].get("stat", {})
            if grp == "hitting":
                rs  = int(sp.get("runs", 0) or 0)
                ops = sp.get("ops", "-")
                avg = sp.get("avg", "-")
            elif grp == "pitching":
                ra  = int(sp.get("runs", 0) or 0)
                era = sp.get("era", "-")
        pyth = "-"
        if rs > 0 and ra > 0:
            e = 1.83
            pyth = f"{rs**e / (rs**e + ra**e):.3f}"

        # 승패/순위 추가
        standings = fetch_standings_cache()
        st = standings.get(team_id, {})

        return {
            "rs": rs, "ra": ra, "ops": ops, "era": era, "avg": avg,
            "pythagorean": pyth,
            "wins":   st.get("wins", "-"),
            "losses": st.get("losses", "-"),
            "pct":    st.get("pct", "-"),
            "rank":   st.get("rank", "-"),
            "div":    st.get("div", "-"),
            "gb":     st.get("gb", "-"),
        }
    except:
        return {"rs": 0, "ra": 0, "ops": "-", "era": "-", "avg": "-",
                "pythagorean": "-", "wins": "-", "losses": "-",
                "pct": "-", "rank": "-", "div": "-", "gb": "-"}


# ══════════════════════════════════════════════════════════════
# 5. 투수 고급 스탯 + 최근 등판 기록
# ══════════════════════════════════════════════════════════════
def fetch_pitcher_advanced(pitcher_id):
    if not pitcher_id:
        return {}
    result = {}
    try:
        # 시즌 스탯
        data = mlb_get(f"/people/{pitcher_id}/stats",
                       {"stats": "season", "group": "pitching", "season": SEASON,
                        "fields": "stats,splits,stat,strikeOuts,baseOnBalls,homeRuns,"
                                  "inningsPitched,era,whip,groundOuts,airOuts,battersFaced"})
        sp = data.get("stats", [{}])[0].get("splits", [{}])[0].get("stat", {})
        if sp:
            k   = float(sp.get("strikeOuts", 0) or 0)
            bb  = float(sp.get("baseOnBalls", 0) or 0)
            hr  = float(sp.get("homeRuns", 0) or 0)
            ip  = float(sp.get("inningsPitched", 0) or 0)
            go  = float(sp.get("groundOuts", 0) or 0)
            ao  = float(sp.get("airOuts", 0) or 0)
            bf  = float(sp.get("battersFaced", 0) or 0)
            result.update({
                "era":  sp.get("era", "-"),
                "whip": sp.get("whip", "-"),
                "k9":   f"{k/ip*9:.1f}"  if ip > 0 else "-",
                "bb9":  f"{bb/ip*9:.1f}" if ip > 0 else "-",
                "hr9":  f"{hr/ip*9:.1f}" if ip > 0 else "-",
                "kbb":  f"{(k-bb)/bf*100:.1f}%" if bf > 0 else "-",
                "gbp":  f"{go/(go+ao)*100:.1f}%" if (go+ao) > 0 else "-",
                "fip":  f"{(13*hr + 3*bb - 2*k)/ip + 3.10:.2f}" if ip > 0 else "-",
                "ip":   f"{ip:.1f}",
            })

        # 최근 5경기 게임 로그
        log_data = mlb_get(f"/people/{pitcher_id}/stats",
                           {"stats": "gameLog", "group": "pitching", "season": SEASON,
                            "fields": "stats,splits,stat,inningsPitched,earnedRuns,"
                                      "strikeOuts,baseOnBalls,homeRuns,note,game,date,opponent,isWin"})
        recent = []
        splits = log_data.get("stats", [{}])[0].get("splits", [])
        for s in splits[-5:]:
            st = s.get("stat", {})
            gm = s.get("game", {})
            opp_id = s.get("opponent", {}).get("id")
            opp_name = team_kr(s.get("opponent", {}).get("name", "?"))
            home_away = "홈" if s.get("isHome") else "원정"
            recent.append({
                "date":     s.get("date", ""),
                "opponent": opp_name,
                "home_away": home_away,
                "ip":       st.get("inningsPitched", "-"),
                "er":       st.get("earnedRuns", "-"),
                "k":        st.get("strikeOuts", "-"),
                "bb":       st.get("baseOnBalls", "-"),
                "result":   "승" if st.get("wins", 0) else ("패" if st.get("losses", 0) else "-"),
            })
        result["recent_games"] = recent[-5:]

        # 홈/원정 분할 스탯
        split_data = mlb_get(f"/people/{pitcher_id}/stats",
                             {"stats": "statSplits", "group": "pitching", "season": SEASON,
                              "sitCodes": "h,a"})  # h=home, a=away
        home_era = away_era = "-"
        for sp_blk in split_data.get("stats", []):
            for sp_s in sp_blk.get("splits", []):
                code = sp_s.get("split", {}).get("code", "")
                era_v = sp_s.get("stat", {}).get("era", "-")
                if code == "h":
                    home_era = era_v
                elif code == "a":
                    away_era = era_v
        result["home_era"] = home_era
        result["away_era"] = away_era

        # 좌우 타자 대전 스탯
        handedness_data = mlb_get(f"/people/{pitcher_id}/stats",
                                  {"stats": "statSplits", "group": "pitching", "season": SEASON,
                                   "sitCodes": "vl,vr"})
        vs_left = vs_right = "-"
        for sp_blk in handedness_data.get("stats", []):
            for sp_s in sp_blk.get("splits", []):
                code = sp_s.get("split", {}).get("code", "")
                avg_v = sp_s.get("stat", {}).get("avg", "-")
                if code == "vl":
                    vs_left = avg_v
                elif code == "vr":
                    vs_right = avg_v
        result["vs_left"]  = vs_left
        result["vs_right"] = vs_right

    except Exception as e:
        print(f"  투수 고급 스탯 실패: {e}")
    return result


# ══════════════════════════════════════════════════════════════
# 6. 불펜 피로도 수집
# ══════════════════════════════════════════════════════════════
def fetch_bullpen_stats(team_id, yesterday_results):
    """전날 불펜 등판 기록 + 최근 팀 불펜 ERA"""
    bullpen = {
        "yesterday_relievers": [],
        "save_situation": False,
        "closer_used": False,
        "closer_name": "확인불가",
        "era": "-",
        "era_last7": "-",
    }
    try:
        # 팀 불펜 시즌 ERA
        data = mlb_get(f"/teams/{team_id}/stats",
                       {"stats": "season", "group": "pitching", "season": SEASON,
                        "pitcherPref": "R"})  # relievers only - approximate
        for blk in data.get("stats", []):
            sp = blk.get("splits", [{}])[0].get("stat", {})
            if sp.get("era"):
                bullpen["era"] = sp.get("era", "-")
                break

        # 전날 해당 팀 경기 찾아서 불펜 투수 확인
        team_yesterday = next(
            (r for r in yesterday_results
             if r.get("home_id") == team_id or r.get("away_id") == team_id),
            None
        )
        if team_yesterday:
            pk = team_yesterday["gamePk"]
            box = mlb_get(f"/game/{pk}/boxscore")
            side = "home" if box.get("teams", {}).get("home", {}).get("team", {}).get("id") == team_id else "away"
            pitchers = box.get("teams", {}).get(side, {}).get("pitchers", [])
            starter_id = pitchers[0] if pitchers else None
            # 선발 제외 나머지가 불펜
            relief_ids = pitchers[1:] if len(pitchers) > 1 else []
            all_players = box.get("teams", {}).get(side, {}).get("players", {})
            for pid in relief_ids:
                key = f"ID{pid}"
                p = all_players.get(key, {})
                pname = player_kr(p.get("person", {}).get("fullName", ""))
                stats = p.get("stats", {}).get("pitching", {})
                ip = stats.get("inningsPitched", "0")
                saves = stats.get("saves", 0)
                holds = stats.get("holds", 0)
                if ip and ip != "0.0" and ip != "0":
                    bullpen["yesterday_relievers"].append({
                        "name": pname,
                        "ip":   ip,
                        "is_closer": (saves > 0),
                    })
                    if saves > 0:
                        bullpen["closer_used"]  = True
                        bullpen["closer_name"]  = pname
                        bullpen["save_situation"] = True
    except Exception as e:
        print(f"  불펜 통계 실패: {e}")
    return bullpen


# ══════════════════════════════════════════════════════════════
# 7. 부상자 명단
# ══════════════════════════════════════════════════════════════
def fetch_injuries(team_id):
    try:
        data = mlb_get(f"/teams/{team_id}/roster",
                       {"rosterType": "injured", "season": SEASON})
        players = []
        for p in data.get("roster", [])[:5]:
            nm  = player_kr(p.get("person", {}).get("fullName", ""))
            pos = p.get("position", {}).get("abbreviation", "")
            sts = p.get("status", {}).get("description", "IL")
            players.append(f"{nm}({pos}) — {sts}")
        return players if players else ["부상자 없음"]
    except:
        return ["조회 불가"]


# ══════════════════════════════════════════════════════════════
# 8. 데이터 보강
# ══════════════════════════════════════════════════════════════

def fetch_recent_form_mlb(team_id: int, team_name: str) -> str:
    """MLB 팀 최근 5경기 폼"""
    try:
        data = mlb_get("/schedule", {
            "sportId": 1,
            "teamId": team_id,
            "startDate": (datetime.now(KST) - timedelta(days=20)).strftime("%Y-%m-%d"),
            "endDate":   (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d"),
            "hydrate": "linescore",
            "gameType": "R",
        })
        results = []
        for db in data.get("dates", []):
            for g in db.get("games", []):
                if g.get("status", {}).get("abstractGameState") != "Final":
                    continue
                ls = g.get("linescore", {})
                h_runs = ls.get("teams", {}).get("home", {}).get("runs")
                a_runs = ls.get("teams", {}).get("away", {}).get("runs")
                if h_runs is None or a_runs is None:
                    continue
                h_id = g["teams"]["home"]["team"]["id"]
                is_home = (h_id == team_id)
                my  = h_runs if is_home else a_runs
                opp = a_runs if is_home else h_runs
                if my > opp:   results.append("✅")
                elif my < opp: results.append("❌")
                else:          results.append("➖")
        last5 = results[-5:]
        return " ".join(last5) if last5 else "-"
    except Exception as e:
        print(f"  폼 수집 실패({team_name}): {e}")
        return "-"

def _lineup_handedness(lineup):
    left   = [p["name_kr"] for p in lineup if p.get("bat_side") == "L"]
    right  = [p["name_kr"] for p in lineup if p.get("bat_side") == "R"]
    switch = [p["name_kr"] for p in lineup if p.get("bat_side") == "S"]
    if not lineup:
        return {"left": left, "right": right, "switch": switch, "note": "라인업 미발표"}
    note = (f"좌타 {len(left)}명 / 우타 {len(right)}명"
            + (f" / 스위치 {len(switch)}명" if switch else ""))
    return {"left": left[:3], "right": right[:3], "switch": switch, "note": note}


def enrich_games(games, yesterday_results):
    enriched = {}
    for g in games:
        pk = g["gamePk"]
        h, a = g["home"], g["away"]
        print(f"  데이터 수집: {a['name_kr']} @ {h['name_kr']}")

        hs  = fetch_team_season_stats(h["id"])
        as_ = fetch_team_season_stats(a["id"])
        hp  = fetch_pitcher_advanced(h["pitcher"]["id"])
        ap  = fetch_pitcher_advanced(a["pitcher"]["id"])
        h_il = fetch_injuries(h["id"])
        a_il = fetch_injuries(a["id"])
        h_bull = fetch_bullpen_stats(h["id"], yesterday_results)
        a_bull = fetch_bullpen_stats(a["id"], yesterday_results)
        h_form = fetch_recent_form_mlb(h["id"], h["name_kr"])
        a_form = fetch_recent_form_mlb(a["id"], a["name_kr"])

        # 전날 해당 팀 경기 결과
        h_yesterday = next(
            (r for r in yesterday_results if r.get("home_id") == h["id"] or r.get("away_id") == h["id"]),
            None
        )
        a_yesterday = next(
            (r for r in yesterday_results if r.get("home_id") == a["id"] or r.get("away_id") == a["id"]),
            None
        )

        enriched[pk] = {
            "home_stats":    hs,
            "away_stats":    as_,
            "home_pitcher_adv": hp,
            "away_pitcher_adv": ap,
            "home_il":       h_il,
            "away_il":       a_il,
            "home_bull":     h_bull,
            "away_bull":     a_bull,
            "h_yesterday":   h_yesterday,
            "a_yesterday":   a_yesterday,
            "home_lineup_hand": _lineup_handedness(h["lineup"]),
            "away_lineup_hand": _lineup_handedness(a["lineup"]),
            "home_form":     h_form,
            "away_form":     a_form,
        }
    return enriched


# ══════════════════════════════════════════════════════════════
# 9. Claude 프롬프트 — 칼럼니스트 스타일
# ══════════════════════════════════════════════════════════════
def build_prompt(games, enriched):
    yesterday_date = (datetime.now(KST) - timedelta(days=1)).strftime("%m월 %d일")

    blocks = ""
    for g in games:
        pk  = g["gamePk"]
        en  = enriched.get(pk, {})
        h, a = g["home"], g["away"]
        hs   = en.get("home_stats", {})
        as_  = en.get("away_stats", {})
        hp   = en.get("home_pitcher_adv", {})
        ap   = en.get("away_pitcher_adv", {})
        hb   = en.get("home_bull", {})
        ab   = en.get("away_bull", {})
        hyl  = en.get("h_yesterday")
        ayl  = en.get("a_yesterday")
        hlh  = en.get("home_lineup_hand", {})
        alh  = en.get("away_lineup_hand", {})

        # 전날 결과 정리
        def yd_str(yd, team_name):
            if not yd:
                return "경기 없음 또는 미확인"
            won = yd["winner"] == team_name
            wp  = yd.get("winning_pitcher", "")
            lp  = yd.get("losing_pitcher", "")
            sv  = yd.get("save_pitcher", "")
            sv_str = f" / 세이브: {sv}" if sv else ""
            return (f"{yd['summary']} ({'승' if won else '패'})"
                    f" — 승리투수: {wp} / 패배투수: {lp}{sv_str}")

        h_yd_str = yd_str(hyl, h["name_kr"])
        a_yd_str = yd_str(ayl, a["name_kr"])

        # 투수 최근 등판
        def recent_str(recent):
            if not recent:
                return "기록 미확인"
            return " / ".join(
                [f"{r['date']} {r['home_away']} vs{r['opponent']} "
                 f"{r['ip']}이닝 {r['er']}실점 {r['k']}K({r['result']})"
                 for r in recent]
            )

        hp_recent = recent_str(hp.get("recent_games", []))
        ap_recent = recent_str(ap.get("recent_games", []))

        # 투수 구종 손방향
        h_throws = "좌완" if h["pitcher"].get("throws") == "L" else "우완"
        a_throws = "좌완" if a["pitcher"].get("throws") == "L" else "우완"

        # 불펜 전날 등판 정리
        def bull_str(bull):
            relv = bull.get("yesterday_relievers", [])
            if not relv:
                return "전날 불펜 등판 없음 또는 미확인"
            closer_used = bull.get("closer_used", False)
            names = [f"{r['name']}({r['ip']}이닝)" for r in relv]
            base = f"등판: {', '.join(names)}"
            if closer_used:
                base += f" / 🔴 마무리({bull.get('closer_name','?')}) 소진"
            return base

        h_bull_str = bull_str(hb)
        a_bull_str = bull_str(ab)

        # 라인업 좌우
        hl_str = (f"{hlh.get('note','?')} "
                  f"— 좌타 주축: {', '.join(hlh.get('left',[])[:2]) or '미발표'}"
                  f" / 우타 주축: {', '.join(hlh.get('right',[])[:2]) or '미발표'}")
        al_str = (f"{alh.get('note','?')} "
                  f"— 좌타 주축: {', '.join(alh.get('left',[])[:2]) or '미발표'}"
                  f" / 우타 주축: {', '.join(alh.get('right',[])[:2]) or '미발표'}")

        # 부상자
        h_il_str = " / ".join(en.get("home_il", []))
        a_il_str = " / ".join(en.get("away_il", []))

        blocks += f"""
━━━ {a['name_kr']} @ {h['name_kr']} | {g['time_kst']} KST ━━━
[전날({yesterday_date}) 결과]
  홈({h['name_kr']}): {h_yd_str}
  원정({a['name_kr']}): {a_yd_str}

[선발 매치업]
  홈 {h['pitcher']['name_kr']} ({h_throws}): 시즌 ERA {hp.get('era','-')} / FIP {hp.get('fip','-')} / WHIP {hp.get('whip','-')}
    홈/원정 ERA: {hp.get('home_era','-')} / {hp.get('away_era','-')}
    좌타/우타 피안타율: {hp.get('vs_left','-')} / {hp.get('vs_right','-')}
    최근 5경기: {hp_recent}
  원정 {a['pitcher']['name_kr']} ({a_throws}): 시즌 ERA {ap.get('era','-')} / FIP {ap.get('fip','-')} / WHIP {ap.get('whip','-')}
    홈/원정 ERA: {ap.get('home_era','-')} / {ap.get('away_era','-')}
    좌타/우타 피안타율: {ap.get('vs_left','-')} / {ap.get('vs_right','-')}
    최근 5경기: {ap_recent}

[타선 구성 & 상성]
  홈({h['name_kr']}): OPS {hs.get('ops','-')} / 타율 {hs.get('avg','-')} / {hl_str}
  원정({a['name_kr']}): OPS {as_.get('ops','-')} / 타율 {as_.get('avg','-')} / {al_str}

[불펜 피로도]
  홈({h['name_kr']}): {h_bull_str}
  원정({a['name_kr']}): {a_bull_str}

[부상자]
  홈 IL: {h_il_str}
  원정 IL: {a_il_str}
"""

    return f"""당신은 15년 경력의 MLB 전문 야구 칼럼니스트입니다.
오늘({TODAY_KR}) 경기 프리뷰를 한국어로 작성하세요.

[경기 데이터]
{blocks}

[작성 지침]
1. 모든 경기를 빠짐없이 전부 분석하되, 빅매치 우선.
2. 각 경기를 독립적인 짧은 칼럼처럼 작성하세요.
3. 전날 경기 결과와 흐름(분위기, 승리투수/마무리 투수 등판 여부)을 먼저 언급하며 오늘 맥락을 잡으세요.
4. 선발투수 분석 (필수):
   - 제공된 이름·ERA·FIP·WHIP·K/9·BB/9·K-BB%·GB%·홈원정 분할ERA·좌우 피안타율·최근 등판을 반드시 활용
   - 최근 3~5경기 등판 패턴을 스토리로 서술 (예: 퀄리티스타트 연속 여부, 홈/원정 ERA 격차)
   - FIP가 ERA보다 낮으면 운이 나빴던 것, 높으면 성적이 부풀려진 것으로 해석해 서술
   - 좌우 피안타율 차이가 크면 상대 라인업 구성과 연결
   - 데이터가 '-'인 경우 '정보 미확인'으로 처리, 억측 금지
   - 선발투수명이 '미정'인 경우: '선발 미공시'로 표기하고 팀 ERA 기반으로 마운드 상태 추정 서술
5. 타선 분석은 선발 손방향(좌완/우완)과 상대 타선 좌/우 구성의 유불리를 구체적으로 서술하세요.
6. 불펜/마무리는 고정된 선수 정보 무시 — 제공된 전날 등판 여부·부상자·실제 기록만으로 피로도와 신뢰도를 판단해 서술하세요.
7. 부상자는 주전급 결장이 있을 때만 언급.
8. 마지막에 오늘 예상 승리팀을 반드시 명시하세요.
12. 투수/타자 특정 선수 이름은 제공된 라인업·데이터에 있는 경우만 언급. 부상·이적 가능성이 있으므로 확인되지 않은 선수명 언급 금지.
9. 마크다운 기호(**텍스트** 등) 절대 사용 금지.
10. 수치 나열 금지. 수치는 맥락 속에 자연스럽게 녹여 쓰세요.
11. 각 경기 칼럼은 350~450자 내외로 압축감 있게.

[형식 — 기호 그대로 사용]

⚾ [원정] @ [홈]  |  [월일 시간] KST

[전날 흐름 복기 — 1~2문장, 오늘 경기와 연결]

[선발 매치업 서술 — 최근 컨디션 중심, 홈/원정 분할 & 좌우 피안타율 포함]

[타선 상성 — 좌타/우타 구성과 선발 손방향의 유불리 구체 서술]

[불펜 & 마무리 가용성 서술]

오늘의 예상: [승리팀] 우세
[핵심 근거 1~2문장]

══════════════════════════════

마지막:
⭐ 오늘의 주목경기: [경기명 + 이유]
🎯 오늘의 주목 선발: [투수명 + 기대 포인트]
📊 오늘의 타선 다크호스: [팀명 + 이유]
⚠️ 오늘의 변수: [경기 흐름을 뒤바꿀 핵심 변수]

══════════════════════════════
🔒 본 최종 분석은 VIP에게만 공유됩니다.

📩 VIP 조합상담 문의는
👉 @HC_VV77 클릭 후 문의"""


# ══════════════════════════════════════════════════════════════
# 10. Claude API 호출
# ══════════════════════════════════════════════════════════════
def generate_preview_text(prompt):
    headers = {"x-api-key": ANTHROPIC_API_KEY,
               "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    body = {"model": "claude-sonnet-4-6", "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}]}
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers=headers, json=body, timeout=300)
    if r.status_code != 200:
        print(f"  ⚠️ Claude API {r.status_code}: {r.text[:200]}")
        return "Claude API 오류로 분석을 생성하지 못했습니다."
    data = r.json()
    if not data.get("content"):
        return "Claude 응답이 비어있습니다."
    return data["content"][0]["text"]


# ══════════════════════════════════════════════════════════════
# 11. 이미지 카드 생성 (경기별 카드)
# ══════════════════════════════════════════════════════════════
def _download_font_if_needed():
    """폰트가 없으면 GitHub에서 다운로드"""
    import os
    font_dir = "/tmp/fonts"
    font_path = f"{font_dir}/NotoSansCJK-Regular.ttc"
    bold_path  = f"{font_dir}/NotoSansCJK-Bold.ttc"

    if os.path.exists(font_path):
        return font_dir

    os.makedirs(font_dir, exist_ok=True)
    try:
        import urllib.request
        url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTC/NotoSansCJK-Regular.ttc"
        print(f"  폰트 다운로드 중...")
        urllib.request.urlretrieve(url, font_path)
        print(f"  ✅ 폰트 다운로드 완료")
    except Exception as e:
        print(f"  ⚠️ 폰트 다운로드 실패: {e}")
    return font_dir

FONT_PATHS = [
    # Nix 환경 (Railway)
    "/run/current-system/sw/share/X11/fonts/NotoSansCJK-Bold.ttc",
    "/run/current-system/sw/share/X11/fonts/NotoSansCJK-Regular.ttc",
    # Ubuntu 환경 (GitHub Actions)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-DemiLight.ttc",
    # 동적 다운로드
    "/tmp/fonts/NotoSansCJK-Bold.ttc",
    "/tmp/fonts/NotoSansCJK-Regular.ttc",
]

def get_font(size, bold=False):
    paths = FONT_PATHS if bold else FONT_PATHS[1:]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except:
            pass
    # 없으면 다운로드 후 재시도
    _download_font_if_needed()
    for p in ["/tmp/fonts/NotoSansCJK-Bold.ttc", "/tmp/fonts/NotoSansCJK-Regular.ttc"]:
        try:
            return ImageFont.truetype(p, size)
        except:
            pass
    return ImageFont.load_default()



def draw_form_badges(draw, form_str, x, y):
    icons = {"W": (34,197,94), "L": (239,68,68), "D": (71,85,105)}
    label_map = {"✅":"W","❌":"L","➖":"D"}
    for ch in form_str.split():
        label = label_map.get(ch, ch[:1])
        color = icons.get(label, (71,85,105))
        draw.rounded_rectangle([x, y-11, x+24, y+7], radius=4, fill=color)
        draw.text((x+12, y-2), label, font=get_font(11), fill=(255,255,255), anchor="mm")
        x += 28
    return x

def make_mlb_card(g: dict, en: dict, preview_text: str) -> bytes:
    W, H = 800, 880
    BG   = (13, 21, 32);   BG2 = (22, 32, 48);   BG3 = (17, 27, 40)
    T1   = (241,245,249);  T2  = (148,163,184);   T3  = (71,85,105)
    DIV  = (30,45,65);     GRN = (34,197,94);     RED = (239,68,68)
    GOLD = (250,204,21)

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    f_big  = get_font(30, bold=True)
    f_med  = get_font(20, bold=True)
    f_base = get_font(18)
    f_sm   = get_font(14)
    f_xs   = get_font(12)
    f_hdr  = get_font(13)

    home = g["home"]; away = g["away"]
    hn = home["name_kr"]; an = away["name_kr"]
    hp = home["pitcher"]; ap = away["pitcher"]
    hs = en.get("home_stats",{}); as_ = en.get("away_stats",{})
    hb = en.get("home_bull",{});  ab  = en.get("away_bull",{})
    hyl= en.get("h_yesterday");   ayl = en.get("a_yesterday")
    hf = en.get("home_form","-"); af  = en.get("away_form","-")

    # ── 헤더
    draw.rectangle([0,0,W,60], fill=BG2)
    draw.text((W//2,20), "MLB 데일리 프리뷰", font=f_hdr, fill=T2, anchor="mm")
    draw.text((W//2,44), f"{TODAY_KR}  ·  {g['time_kst']} KST  ·  {g.get('venue','-')}", font=f_xs, fill=T3, anchor="mm")

    y = 68
    BOX_W = 358; BOX_H = 168

    # MLB 팀 컬러
    MLB_COLOR = {
        "LA 다저스":(0,90,156), "뉴욕 양키스":(12,35,64),
        "휴스턴 애스트로스":(0,45,98), "애틀랜타 브레이브스":(206,17,65),
        "보스턴 레드삭스":(189,48,57), "샌프란시스코 자이언츠":(253,90,30),
        "뉴욕 메츠":(0,45,114), "필라델피아 필리스":(232,24,40),
        "토론토 블루제이스":(19,74,142), "볼티모어 오리올스":(223,70,1),
        "탬파베이 레이스":(9,44,92), "시카고 화이트삭스":(39,37,31),
        "시카고 컵스":(14,51,134), "클리블랜드 가디언스":(0,56,93),
        "디트로이트 타이거스":(12,35,64), "캔자스시티 로열스":(0,70,135),
        "미네소타 트윈스":(211,17,69), "밀워키 브루어스":(18,40,75),
        "세인트루이스 카디널스":(196,30,58), "신시내티 레즈":(198,1,31),
        "피츠버그 파이리츠":(39,37,31), "콜로라도 로키스":(51,0,111),
        "애리조나 다이아몬드백스":(167,25,48), "LA 에인절스":(186,0,33),
        "시애틀 매리너스":(0,92,92), "텍사스 레인저스":(0,50,120),
        "샌디에이고 파드리스":(47,36,29), "마이애미 말린스":(0,163,224),
        "워싱턴 내셔널스":(171,0,3), "오클랜드 애슬레틱스":(0,56,49),
    }
    hc = MLB_COLOR.get(hn, (80,80,80))
    ac = MLB_COLOR.get(an, (80,80,80))

    # 홈팀 박스
    draw.rounded_rectangle([16,y,16+BOX_W,y+BOX_H], radius=12, fill=BG2)
    draw.rectangle([16,y,16+BOX_W,y+5], fill=hc)
    draw.text((16+BOX_W//2, y+30), "홈", font=f_sm, fill=(*hc,255)[:3], anchor="mm")
    draw.text((16+BOX_W//2, y+68), hn, font=f_big, fill=T1, anchor="mm")
    draw.line([36,y+90,16+BOX_W-20,y+90], fill=DIV, width=1)
    h_wins = hs.get('wins','-'); h_losses = hs.get('losses','-')
    h_rank = hs.get('rank','-'); h_div = hs.get('div','-')
    h_rec = f"{h_wins}승 {h_losses}패  {h_div} {h_rank}위"
    draw.text((16+BOX_W//2, y+104), h_rec, font=f_sm, fill=T2, anchor="mm")
    h_era_txt = f"팀ERA {hs.get('era','-')}  OPS {hs.get('ops','-')}"
    draw.text((16+BOX_W//2, y+122), h_era_txt, font=f_xs, fill=T3, anchor="mm")
    h_sp_name = f"{hp.get('name_kr','미정')}"
    h_sp_info = f"({'좌완' if hp.get('throws')=='L' else '우완'})  ERA {en.get('home_pitcher_adv',{}).get('era','-')}  WHIP {en.get('home_pitcher_adv',{}).get('whip','-')}"
    draw.text((36, y+130), h_sp_name, font=f_base, fill=T1, anchor="lm")
    draw.text((36, y+152), h_sp_info, font=f_xs, fill=T2, anchor="lm")

    # VS
    draw.text((W//2, y+86), "VS", font=f_med, fill=T3, anchor="mm")

    # 원정팀 박스
    ax = W-16-BOX_W
    draw.rounded_rectangle([ax,y,ax+BOX_W,y+BOX_H], radius=12, fill=BG2)
    draw.rectangle([ax,y,ax+BOX_W,y+5], fill=ac)
    draw.text((ax+BOX_W//2, y+30), "원정", font=f_sm, fill=(*ac,255)[:3], anchor="mm")
    draw.text((ax+BOX_W//2, y+68), an, font=f_big, fill=T1, anchor="mm")
    draw.line([ax+20,y+90,ax+BOX_W-20,y+90], fill=DIV, width=1)
    a_wins = as_.get('wins','-'); a_losses = as_.get('losses','-')
    a_rank = as_.get('rank','-'); a_div = as_.get('div','-')
    a_rec = f"{a_wins}승 {a_losses}패  {a_div} {a_rank}위"
    draw.text((ax+BOX_W//2, y+104), a_rec, font=f_sm, fill=T2, anchor="mm")
    a_era_txt = f"팀ERA {as_.get('era','-')}  OPS {as_.get('ops','-')}"
    draw.text((ax+BOX_W//2, y+122), a_era_txt, font=f_xs, fill=T3, anchor="mm")
    a_sp_name = f"{ap.get('name_kr','미정')}"
    a_sp_info = f"({'좌완' if ap.get('throws')=='L' else '우완'})  ERA {en.get('away_pitcher_adv',{}).get('era','-')}  WHIP {en.get('away_pitcher_adv',{}).get('whip','-')}"
    draw.text((ax+20, y+130), a_sp_name, font=f_base, fill=T1, anchor="lm")
    draw.text((ax+20, y+152), a_sp_info, font=f_xs, fill=T2, anchor="lm")

    y += BOX_H + 12

    # 불펜 피로도
    draw.rounded_rectangle([16,y,W-16,y+60], radius=10, fill=BG2)
    draw.text((36, y+14), "불펜 피로도", font=f_xs, fill=T3, anchor="lm")
    h_closer = hb.get("closer_used",False)
    a_closer = ab.get("closer_used",False)
    hb_txt = f"{hn}: {'🔴 마무리 소진' if h_closer else '✅ 정상'}"
    ab_txt = f"{an}: {'🔴 마무리 소진' if a_closer else '✅ 정상'}"
    hb_col = RED if h_closer else GRN
    ab_col = RED if a_closer else GRN
    draw.text((36, y+42), hb_txt, font=f_sm, fill=hb_col, anchor="lm")
    draw.text((W//2+10, y+42), ab_txt, font=f_sm, fill=ab_col, anchor="lm")

    y += 74

    # 최근 5경기 폼
    draw.rounded_rectangle([16,y,W-16,y+56], radius=10, fill=BG2)
    draw.text((36, y+14), "최근 5경기", font=f_xs, fill=T3, anchor="lm")
    draw.text((36, y+38), f"{hn}", font=f_xs, fill=T2, anchor="lm")
    draw_form_badges(draw, hf, 130, y+38)
    draw.text((W//2+10, y+38), f"{an}", font=f_xs, fill=T2, anchor="lm")
    draw_form_badges(draw, af, W//2+90, y+38)
    y += 70

    # 전날 결과
    draw.rounded_rectangle([16,y,W-16,y+46], radius=10, fill=BG2)
    draw.text((36, y+14), "전날 결과", font=f_xs, fill=T3, anchor="lm")
    h_yd_txt = f"{hn}: {hyl['summary'] if hyl else '경기없음'}"
    a_yd_txt = f"{an}: {ayl['summary'] if ayl else '경기없음'}"
    draw.text((36, y+34), h_yd_txt[:35], font=f_xs, fill=T2, anchor="lm")
    draw.text((W//2+10, y+34), a_yd_txt[:35], font=f_xs, fill=T2, anchor="lm")

    y += 60

    # 프리뷰 분석
    draw.rounded_rectangle([16,y,W-16,y+400], radius=12, fill=BG3)
    draw.text((36, y+18), "프리뷰 분석", font=f_xs, fill=T3, anchor="lm")
    draw.line([36,y+30,W-36,y+30], fill=DIV, width=1)

    ty = y + 46
    for line in preview_text.split("\n"):
        if not line.strip(): ty += 8; continue
        if "오늘의 예상" in line or "우세" in line:
            draw.text((36, ty), line.strip()[:55], font=f_base, fill=GOLD, anchor="lm")
            ty += 28
        else:
            # 줄바꿈
            chars = line.strip(); cur = ""; wrapped = []
            for ch in chars:
                test = cur+ch
                bb = draw.textbbox((0,0), test, font=f_base)
                if bb[2] > W-72 and cur:
                    wrapped.append(cur); cur = ch
                else: cur = test
            if cur: wrapped.append(cur)
            for wl in wrapped:
                if ty > y+385: break
                draw.text((36, ty), wl, font=f_base, fill=T1, anchor="lm")
                ty += 25
        if ty > y+385: break

    y += 412

    # VIP
    draw.rounded_rectangle([16,y,W-16,y+46], radius=10, fill=BG2)
    draw.text((W//2, y+14), "🔒 VIP 전용 분석", font=f_xs, fill=T3, anchor="mm")
    draw.text((W//2, y+34), "📩 문의: @HC_VV77", font=f_sm, fill=T2, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    buf.seek(0)
    return buf.getvalue()


def send_media_group(image_bytes_list: list):
    import json
    if not image_bytes_list: return
    for batch_start in range(0, len(image_bytes_list), 10):
        batch = image_bytes_list[batch_start:batch_start+10]
        files = {}; media = []
        for i, img_bytes in enumerate(batch):
            fname = f"photo{i}"
            files[fname] = (f"{fname}.jpg", img_bytes, "image/jpeg")
            media.append({"type":"photo","media":f"attach://{fname}"})
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup",
                data={"chat_id": TELEGRAM_CHAT_ID, "media": json.dumps(media)},
                files=files, timeout=60)
            if r.status_code==200: print(f"✅ 묶음 발송 완료 ({len(batch)}장)")
            else: print(f"⚠️ 발송 실패: {r.text[:200]}")
        except Exception as e:
            print(f"⚠️ 발송 오류: {e}")
        time.sleep(1)


def call_claude_single(prompt: str) -> str:
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_API_KEY,
                     "anthropic-version":"2023-06-01",
                     "content-type":"application/json"},
            json={"model":"claude-sonnet-4-6","max_tokens":800,
                  "messages":[{"role":"user","content":prompt}]},
            timeout=90)
        if r.status_code!=200: return "분석 생성 실패"
        return r.json()["content"][0]["text"]
    except Exception as e:
        print(f"  Claude 오류: {e}")
        return "분석 생성 실패"


def build_single_prompt_mlb(g: dict, en: dict) -> str:
    hn = g["home"]["name_kr"]; an = g["away"]["name_kr"]
    hs = en.get("home_stats",{}); as_ = en.get("away_stats",{})
    hp = en.get("home_pitcher_adv",{}); ap = en.get("away_pitcher_adv",{})
    hb = en.get("home_bull",{}); ab = en.get("away_bull",{})
    hyl = en.get("h_yesterday"); ayl = en.get("a_yesterday")
    h_throw = "좌완" if g["home"]["pitcher"].get("throws")=="L" else "우완"
    a_throw = "좌완" if g["away"]["pitcher"].get("throws")=="L" else "우완"

    return f"""MLB 칼럼니스트로서 아래 경기 프리뷰를 300자 내외로 작성하세요.
마지막 줄은 반드시 "오늘의 예상: {{팀명}} 우세" 형식으로 끝내세요.
마크다운 기호 금지. 수치 나열 금지. 스토리텔링 우선.
확인되지 않은 선수명 언급 금지.

경기: {an} @ {hn} | {g["time_kst"]} KST
홈({hn}): {hs.get("wins","-")}승 {hs.get("losses","-")}패 ERA {hs.get("era","-")} OPS {hs.get("ops","-")}
원정({an}): {as_.get("wins","-")}승 {as_.get("losses","-")}패 ERA {as_.get("era","-")} OPS {as_.get("ops","-")}
전날: 홈={hyl["summary"] if hyl else "경기없음"} / 원정={ayl["summary"] if ayl else "경기없음"}
홈 선발: {g["home"]["pitcher"].get("name_kr","미정")}({h_throw}) ERA {hp.get("era","-")} FIP {hp.get("fip","-")} WHIP {hp.get("whip","-")}
원정 선발: {g["away"]["pitcher"].get("name_kr","미정")}({a_throw}) ERA {ap.get("era","-")} FIP {ap.get("fip","-")} WHIP {ap.get("whip","-")}
불펜: 홈 마무리={'소진🔴' if hb.get("closer_used") else '정상✅'} / 원정 마무리={'소진🔴' if ab.get("closer_used") else '정상✅'}"""


# ══════════════════════════════════════════════════════════════
# 12. 텔레그램 — 텍스트 메시지 (헤더용)
# ══════════════════════════════════════════════════════════════
def send_message(text: str):
    if len(text) > 4096: text = text[:4090] + "..."
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)
        if r.status_code != 200:
            safe = re.sub(r"[<>&]", "", text)
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": safe}, timeout=15)
    except Exception as e:
        print(f"  ⚠️ 발송 실패: {e}")


# ══════════════════════════════════════════════════════════════
# 13. 메인 — 이미지 카드 묶음 발송
# ══════════════════════════════════════════════════════════════
def main():
    print(f"[{TODAY_KR}] MLB 프리뷰 시작...")

    print("📡 전날 경기 결과 수집...")
    yesterday_results = fetch_yesterday_results()
    print(f"  → {len(yesterday_results)}경기")

    print("📡 오늘 경기 수집...")
    games = fetch_todays_games()
    if not games:
        print("오늘 MLB 경기 없음")
        return

    print(f"  → {len(games)}경기")
    print("📊 데이터 수집...")
    enriched = enrich_games(games, yesterday_results)



    # 경기별 이미지 카드 생성
    print("🎨 이미지 카드 생성...")
    image_list = []
    for i, g in enumerate(games, 1):
        pk  = g["gamePk"]
        en  = enriched.get(pk, {})
        hn  = g["home"]["name_kr"]
        an  = g["away"]["name_kr"]
        print(f"  {i}/{len(games)} {an} @ {hn} 분석 생성...")

        prompt  = build_single_prompt_mlb(g, en)
        preview = call_claude_single(prompt)
        img_bytes = make_mlb_card(g, en, preview)
        image_list.append(img_bytes)
        print(f"  ✅ 카드 생성")
        time.sleep(1)

    # 묶음 발송
    print("📨 이미지 묶음 발송...")
    send_media_group(image_list)
    print("🎉 완료!")


if __name__ == "__main__":
    main()
