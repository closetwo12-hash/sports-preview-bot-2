"""
NPB Daily Preview Generator — 이미지 카드 묶음 발송 버전

경기별 이미지 카드 생성 (PIL) → 텔레그램 sendMediaGroup으로 묶음 발송
"""

import os, re, time, requests, io
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

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

# ══════════════════════════════════════════════════
# 팀 정보
# ══════════════════════════════════════════════════
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
VENUE_MAP = {
    "東京ドーム":"도쿄돔","神 宮":"진구","神宮":"진구",
    "横 浜":"요코하마","バンテリン":"반테린돔","甲子園":"고시엔",
    "マツダ":"마쓰다","PayPay":"페이페이돔","みずほ":"페이페이돔",
    "エスコン":"ES CON FIELD","楽天モバイル":"라쿠텐모바일",
    "ZOZO":"ZOZO마린","ベルーナ":"베루나돔","京セラ":"교세라돔",
}
TEAM_COLOR = {
    "요미우리":  (255, 152, 0),
    "야쿠르트":  (0, 102, 204),
    "DeNA":     (0, 56, 168),
    "주니치":   (0, 40, 130),
    "한신":     (255, 204, 0),
    "히로시마":  (220, 30, 30),
    "소프트뱅크":(255, 184, 0),
    "닛폰햄":   (0, 90, 170),
    "오릭스":   (0, 60, 120),
    "라쿠텐":   (204, 0, 0),
    "세이부":   (0, 92, 175),
    "롯데":     (0, 0, 0),
}

def jp_to_kr(s):
    s = s.strip()
    if s in JP_TO_KR: return JP_TO_KR[s]
    for k,v in JP_TO_KR.items():
        if k in s: return v
    return s



PITCHER_KR = {
    # 요미우리
    "則本 昂大": "노리모토 타카히로", "戸郷 翔征": "토고 쇼세이",
    "菅野 智之": "스가노 토모유키", "山崎 伊織": "야마사키 이오리",
    "グリフィン": "그리핀", "赤星 優志": "아카호시 유지",
    # 한신
    "西 勇輝": "니시 유키", "伊藤 将司": "이토 마사시",
    "村上 頌樹": "무라카미 쇼키", "才木 浩人": "사이키 히로토",
    "青柳 晃洋": "아오야기 코요", "髙橋 遥人": "타카하시 하루토",
    # 오릭스
    "九里 亜蓮": "쿠리 아렌", "山下 舜平大": "야마시타 슌페이타",
    "宮城 大弥": "미야기 히로야", "田嶋 大樹": "타지마 타이키",
    "東 晃平": "아즈마 코헤이",
    # 소프트뱅크
    "大津 亮介": "오츠 료스케", "有原 航平": "아리하라 코헤이",
    "石川 柊太": "이시카와 슈타", "モイネロ": "모이넬로",
    "松本 晴": "마츠모토 하루",
    # 닛폰햄
    "伊藤 大海": "이토 히로미", "上沢 直之": "우와사와 나오유키",
    "加藤 貴之": "카토 타카유키", "金村 尚真": "카네무라 나오마사",
    # 라쿠텐
    "荘司 康誠": "쇼지 코세이", "岸 孝之": "기시 타카유키",
    "瀧中 瞭太": "타키나카 료타", "早川 隆久": "하야카와 타카히사",
    # DeNA
    "平良 拳太郎": "타이라 켄타로", "東 克樹": "아즈마 카츠키",
    "石田 裕太郎": "이시다 유타로", "ジャクソン": "잭슨",
    "Ａ．ジャクソン": "A.잭슨",
    # 야쿠르트
    "松本 健吾": "마츠모토 켄고", "高橋 奎二": "타카하시 케이지",
    "サイスニード": "사이스니드", "小川 泰弘": "오가와 야스히로",
    # 주니치
    "Ｋ．マラー": "K.말러", "マラー": "말러",
    "髙橋 宏斗": "타카하시 히로토", "柳 裕也": "야나기 유야",
    "小笠原 慎之介": "오가사와라 신노스케",
    # 세이부
    "平良 海馬": "타이라 카이마", "武内 夏暉": "타케우치 나츠키",
    "今井 達也": "이마이 타츠야", "隅田 知一郎": "스미다 토모이치로",
    # 롯데
    "床田 寛樹": "토코다 히로키", "小島 和哉": "코지마 카즈야",
    "種市 篤暉": "タネイチ 아츠키", "佐々木 朗希": "사사키 로키",
    # 히로시마
    "九里 亜蓮": "쿠리 아렌", "床田 寛樹": "토코다 히로키",
    "森下 暢仁": "모리시타 미치토", "大瀬良 大地": "오세라 다이치",
    "アドゥワ 誠": "아두와 마코토",
}

def pitcher_kr(name_jp: str) -> str:
    """일본어 선수명 → 한국어 독음. 없으면 원문 그대로."""
    name_jp = name_jp.strip()
    # 공백 정규화
    name_norm = re.sub(r"[　\s]+", " ", name_jp).strip()
    if name_norm in PITCHER_KR:
        return PITCHER_KR[name_norm]
    if name_jp in PITCHER_KR:
        return PITCHER_KR[name_jp]
    # 부분 매칭
    for k, v in PITCHER_KR.items():
        k_norm = re.sub(r"[　\s]+", " ", k).strip()
        if k_norm == name_norm or k in name_jp or name_jp in k:
            return v
    return name_jp


def venue_kr(s):
    for k,v in VENUE_MAP.items():
        if k in s: return v
    return s.strip()

# ══════════════════════════════════════════════════
# 폰트 로드
# ══════════════════════════════════════════════════
FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-DemiLight.ttc",
]

def get_font(size, bold=False):
    paths = FONT_PATHS if bold else FONT_PATHS[1:]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except:
            pass
    return ImageFont.load_default()

# ══════════════════════════════════════════════════
# 이미지 카드 생성
# ══════════════════════════════════════════════════
W, H = 800, 900

# 색상
BG       = (13, 21, 32)
BG2      = (22, 32, 48)
BG3      = (17, 27, 40)
TEXT1    = (241, 245, 249)
TEXT2    = (148, 163, 184)
TEXT3    = (71, 85, 105)
DIVIDER  = (30, 45, 65)
GREEN    = (34, 197, 94)
RED      = (239, 68, 68)
GRAY     = (71, 85, 105)
GOLD     = (250, 204, 21)

def draw_rounded_rect(draw, xy, radius, fill, outline=None, width=1):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill,
                           outline=outline, width=width)

def wrap_text(text, font, max_width, draw):
    """텍스트를 max_width에 맞게 줄바꿈"""
    words = list(text)
    lines = []
    current = ""
    for char in text:
        test = current + char
        bbox = draw.textbbox((0,0), test, font=font)
        if bbox[2] > max_width and current:
            lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines

def make_card(g: dict, preview_text: str) -> bytes:
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # 폰트
    f_big   = get_font(30, bold=True)
    f_med   = get_font(22, bold=True)
    f_base  = get_font(18)
    f_sm    = get_font(15)
    f_xs    = get_font(13)
    f_hdr   = get_font(14)

    home = g["home"]; away = g["away"]
    hc   = TEAM_COLOR.get(home, (100,100,100))
    ac   = TEAM_COLOR.get(away, (100,100,100))
    hs   = g.get("hs", {}); as_ = g.get("as_", {})
    hp   = g.get("hp", {}); ap  = g.get("ap", {})
    hb   = g.get("hbull", {}); ab = g.get("abull", {})

    y = 0

    # ── 헤더 ──────────────────────────────────────
    draw_rounded_rect(draw, [0,0,W,64], 0, BG2)
    draw.text((W//2, 20), "NPB 데일리 프리뷰", font=f_hdr, fill=TEXT2, anchor="mm")
    date_str = f"{TODAY_KR}  {g.get('time','-')} JST  {g.get('venue','-')}"
    draw.text((W//2, 46), date_str, font=f_xs, fill=TEXT3, anchor="mm")
    y = 72

    # ── 홈/원정 팀 박스 ───────────────────────────
    BOX_W = 358; BOX_H = 170
    # 홈팀
    draw_rounded_rect(draw, [16, y, 16+BOX_W, y+BOX_H], 12, BG2)
    draw.rectangle([16, y, 16+BOX_W, y+5], fill=hc)
    draw.text((16+BOX_W//2, y+32), "홈", font=f_sm, fill=(*hc, 255), anchor="mm")
    draw.text((16+BOX_W//2, y+72), home, font=f_big, fill=TEXT1, anchor="mm")
    # 홈 스탯
    h_draw = hs.get('draw','0')
    rank_h = (f"{hs.get('rank','-')}위  "
              f"{hs.get('win','-')}승 {hs.get('lose','-')}패"
              + (f" {h_draw}무" if h_draw not in ('0','-','') else ""))
    draw.text((16+BOX_W//2, y+106), rank_h, font=f_sm, fill=TEXT2, anchor="mm")
    draw.line([36, y+120, 16+BOX_W-20, y+120], fill=DIVIDER, width=1)
    sp_h = f"선발: {g.get('home_pitcher','미정')}"
    draw.text((36, y+134), sp_h, font=f_sm, fill=(*hc,), anchor="lm")
    era_h = f"ERA {hp.get('era','-')}  WHIP {hp.get('whip','-')}  {hp.get('w','-')}승{hp.get('l','-')}패"
    draw.text((36, y+152), era_h, font=f_xs, fill=TEXT3, anchor="lm")

    # 원정팀
    ax = W - 16 - BOX_W
    draw_rounded_rect(draw, [ax, y, ax+BOX_W, y+BOX_H], 12, BG2)
    draw.rectangle([ax, y, ax+BOX_W, y+5], fill=ac)
    draw.text((ax+BOX_W//2, y+32), "원정", font=f_sm, fill=(*ac,), anchor="mm")
    draw.text((ax+BOX_W//2, y+72), away, font=f_big, fill=TEXT1, anchor="mm")
    a_draw = as_.get('draw','0')
    rank_a = (f"{as_.get('rank','-')}위  "
              f"{as_.get('win','-')}승 {as_.get('lose','-')}패"
              + (f" {a_draw}무" if a_draw not in ('0','-','') else ""))
    draw.text((ax+BOX_W//2, y+106), rank_a, font=f_sm, fill=TEXT2, anchor="mm")
    draw.line([ax+20, y+120, ax+BOX_W-20, y+120], fill=DIVIDER, width=1)
    sp_a = f"선발: {g.get('away_pitcher','미정')}"
    draw.text((ax+20, y+134), sp_a, font=f_sm, fill=(*ac,), anchor="lm")
    era_a = f"ERA {ap.get('era','-')}  WHIP {ap.get('whip','-')}  {ap.get('w','-')}승{ap.get('l','-')}패"
    draw.text((ax+20, y+152), era_a, font=f_xs, fill=TEXT3, anchor="lm")

    # VS
    draw.text((W//2, y+90), "VS", font=f_med, fill=TEXT3, anchor="mm")
    y += BOX_H + 14

    # ── 최근 5경기 폼 (홈/원정 구분) ───────────────
    draw_rounded_rect(draw, [16, y, W-16, y+86], 10, BG2)
    draw.text((36, y+14), "최근 5경기", font=f_xs, fill=TEXT3, anchor="lm")

    def draw_form(text, start_x, start_y):
        icons = {"✅":"W","❌":"L","➖":"D"}
        colors = {"W": GREEN, "L": RED, "D": GRAY}
        x = start_x
        for ch in text.split():
            label = icons.get(ch, ch[:1].upper() if ch else "-")
            color = colors.get(label, GRAY)
            draw.rounded_rectangle([x, start_y-10, x+24, start_y+8], radius=4, fill=color)
            draw.text((x+12, start_y-1), label, font=f_xs, fill=TEXT1, anchor="mm")
            x += 28
        return x

    # 홈팀 폼
    draw.text((36, y+38), f"{home} 홈", font=f_xs, fill=TEXT2, anchor="lm")
    draw_form(g.get("hf_home", g.get("hf","-")), 130, y+38)
    draw.text((36, y+62), f"{home} 원정", font=f_xs, fill=TEXT3, anchor="lm")
    draw_form(g.get("hf_away", "-"), 130, y+62)

    # 원정팀 폼
    draw.text((W//2+10, y+38), f"{away} 홈", font=f_xs, fill=TEXT2, anchor="lm")
    draw_form(g.get("af_home", g.get("af","-")), W//2+100, y+38)
    draw.text((W//2+10, y+62), f"{away} 원정", font=f_xs, fill=TEXT3, anchor="lm")
    draw_form(g.get("af_away", "-"), W//2+100, y+62)
    y += 100

    # ── 불펜 피로도 ───────────────────────────────
    draw_rounded_rect(draw, [16, y, W-16, y+64], 10, BG2)
    draw.text((36, y+16), "불펜 피로도", font=f_xs, fill=TEXT3, anchor="lm")

    def bull_color(status):
        if "✅" in status: return GREEN
        if "🔴" in status: return RED
        return (255, 170, 0)

    hbs = hb.get("status","확인불가")
    abs_ = ab.get("status","확인불가")
    hbc = bull_color(hbs)
    abc = bull_color(abs_)

    draw.text((36, y+40), f"{home}:", font=f_xs, fill=TEXT2, anchor="lm")
    hbs_clean = re.sub(r'[✅⚠️🔴]','',hbs).strip()
    draw.text((120, y+40), hbs_clean[:30], font=f_xs, fill=hbc, anchor="lm")

    draw.text((W//2+10, y+40), f"{away}:", font=f_xs, fill=TEXT2, anchor="lm")
    abs_clean = re.sub(r'[✅⚠️🔴]','',abs_).strip()
    draw.text((W//2+80, y+40), abs_clean[:30], font=f_xs, fill=abc, anchor="lm")
    y += 78

    # ── 프리뷰 분석 텍스트 ────────────────────────
    draw_rounded_rect(draw, [16, y, W-16, y+400], 12, BG3)
    draw.text((36, y+20), "프리뷰 분석", font=f_xs, fill=TEXT3, anchor="lm")
    draw.line([36, y+32, W-36, y+32], fill=DIVIDER, width=1)

    # 텍스트 렌더링
    ty = y + 48
    max_w = W - 72
    for line in preview_text.split('\n'):
        if not line.strip():
            ty += 8
            continue
        # 오늘의 예상 라인은 강조
        if "오늘의 예상" in line:
            draw.text((36, ty), line.strip(), font=f_base, fill=GOLD, anchor="lm")
            ty += 28
        else:
            wrapped = wrap_text(line.strip(), f_base, max_w, draw)
            for wl in wrapped:
                if ty > y + 380:
                    break
                draw.text((36, ty), wl, font=f_base, fill=TEXT1, anchor="lm")
                ty += 26
        if ty > y + 380:
            break
    y += 410

    # ── 하단 VIP ──────────────────────────────────
    draw_rounded_rect(draw, [16, y, W-16, y+48], 10, BG2)
    draw.text((W//2, y+16), "🔒 VIP 전용 분석", font=f_xs, fill=TEXT3, anchor="mm")
    draw.text((W//2, y+36), "📩 문의: @HC_VV77", font=f_sm, fill=TEXT2, anchor="mm")

    # 바이트로 변환
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    buf.seek(0)
    return buf.getvalue()

# ══════════════════════════════════════════════════
# 데이터 수집 함수들 (기존과 동일)
# ══════════════════════════════════════════════════
_STARTER_SOUP = None

def _get_starter_soup():
    global _STARTER_SOUP
    if _STARTER_SOUP: return _STARTER_SOUP
    urls = [
        "https://npb.jp/announcement/starter/",
        f"https://npb.jp/games/{SEASON}/schedule_{NOW_KST.strftime('%m')}_detail.html",
        f"https://npb.jp/interleague/{SEASON}/schedule_detail.html",
    ]
    for url in urls:
        try:
            r = SESS.get(url, timeout=12)
            if r.status_code != 200: continue
            html = r.content.decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            if MMDD in html or f"/scores/{SEASON}/{MMDD}/" in html:
                print(f"  ✅ 소스: {url.split('/')[-1]}")
                _STARTER_SOUP = soup
                return soup
        except Exception as e:
            print(f"  ⚠️ {e}")
    try:
        r = SESS.get("https://npb.jp/announcement/starter/", timeout=12)
        html = r.content.decode("utf-8", errors="ignore")
        _STARTER_SOUP = BeautifulSoup(html, "html.parser")
    except:
        _STARTER_SOUP = BeautifulSoup("", "html.parser")
    return _STARTER_SOUP

def _extract_games_from_links(soup, mmdd):
    games = []; seen = set()
    pattern = re.compile(rf"/scores/{SEASON}/{mmdd}/(\w+)-(\w+)-(\d+)/")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"): href = "https://npb.jp" + href
        m = pattern.search(href)
        if not m: continue
        hc = m.group(1); ac = m.group(2); gn = m.group(3)
        key = f"{hc}-{ac}-{gn}"
        if key in seen: continue
        seen.add(key)
        home_kr = URL_CODE_KR.get(hc, "")
        away_kr = URL_CODE_KR.get(ac, "")
        if not home_kr or not away_kr: continue
        text = a.get_text(separator=" ", strip=True)
        venue = venue_kr(text) if text else "-"
        time_m = re.search(r"(\d{1,2}:\d{2})", text)
        time_str = time_m.group(1) if time_m else "18:00"
        score_m = re.search(r"\b(\d+)-(\d+)\b", text)
        finished = score_m is not None
        games.append({
            "time": time_str, "venue": venue,
            "home": home_kr, "away": away_kr,
            "home_score": int(score_m.group(1)) if score_m else None,
            "away_score": int(score_m.group(2)) if score_m else None,
            "finished": finished,
            "home_pitcher": "미정", "away_pitcher": "미정",
            "href": href,
        })
    return games

def _parse_starters(soup) -> dict:
    """
    예고선발 테이블에서 팀별 선발투수 직접 파싱.
    테이블 구조: 팀명 | 투수명 | 팀명 | 투수명 (같은 행)
    """
    starters   = {}
    player_ids = []

    # 선수 사진 링크에서 선수 ID 추출
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/bis/players/" in href and ".html" in href:
            m = re.search(r"/bis/players/(\d+)\.html", href)
            if m:
                pid = m.group(1)
                if pid not in player_ids:
                    player_ids.append(pid)

    print(f"  예고선발 선수 ID {len(player_ids)}명")

    # 각 선수 페이지 title에서 이름+팀 파싱
    for pid in player_ids:
        try:
            r = SESS.get(f"https://npb.jp/bis/players/{pid}.html", timeout=10)
            print(f"    [{pid}] {r.status_code}")
            if r.status_code != 200:
                continue
            # 인코딩 명시적으로 UTF-8 지정
            html = r.content.decode("utf-8", errors="ignore")
            title_m = re.search(r"<title>([^<]+)</title>", html)
            if not title_m:
                continue
            title = title_m.group(1).strip()
            # 형식: "戸郷　翔征（読売ジャイアンツ） | 個人年度別成績"
            nm = re.match(r"^(.+?)[\uff08(](.+?)[\uff09)]", title)
            if not nm:
                continue
            name    = re.sub(r"[\u3000\s]+", " ", nm.group(1)).strip()
            team_jp = nm.group(2).strip()
            team_kr = jp_to_kr(team_jp)
            if team_kr in TEAM_LEAGUE and name:
                name_display = pitcher_kr(name)
                starters[team_kr] = name_display
                print(f"    ✅ {team_kr}: {name_display} ({name})")
            time.sleep(0.2)
        except Exception as e:
            print(f"    [{pid}] 오류: {e}")

    if not starters:
        print("  ⚠️ 선발 수집 실패")
    return starters


def fetch_schedule():
    print(f"  NPB 오늘({MMDD}) 경기 수집...")
    soup = _get_starter_soup()
    games = _extract_games_from_links(soup, MMDD)
    starters = _parse_starters(soup)
    for g in games:
        g["home_pitcher"] = starters.get(g["home"], "미정")
        g["away_pitcher"] = starters.get(g["away"], "미정")
    print(f"  ✅ {len(games)}경기")
    return games

def fetch_yesterday_results():
    soup = _get_starter_soup()
    games = _extract_games_from_links(soup, YESTERDAY_MMDD)
    results = []
    for g in games:
        if not g["finished"]: continue
        hs, vs = g["home_score"], g["away_score"]
        winner = g["home"] if hs > vs else (g["away"] if vs > hs else "무")
        results.append({"home":g["home"],"away":g["away"],
                        "home_score":hs,"away_score":vs,"winner":winner,
                        "summary":f"{g['away']} {vs}:{hs} {g['home']}"})
    return results

_PITCHER_CACHE = {}

def _load_pitcher_cache():
    if _PITCHER_CACHE: return
    for lc in ["c","p"]:
        try:
            r = SESS.get(f"https://npb.jp/bis/eng/{SEASON}/stats/pit_{lc}.html", timeout=12)
            soup = BeautifulSoup(r.text, "html.parser")
            for row in soup.select("table tbody tr"):
                cols = row.select("td")
                if len(cols) < 9: continue
                name = cols[1].get_text(strip=True)
                if not name: continue
                ip_f = float(re.sub(r"[^\d.]","",cols[7].get_text()) or 0)
                k_f  = float(re.sub(r"\D","",cols[11].get_text()) or 0) if len(cols)>11 else 0
                bb_f = float(re.sub(r"\D","",cols[12].get_text()) or 0) if len(cols)>12 else 0
                _PITCHER_CACHE[name] = {
                    "w": cols[3].get_text(strip=True) if len(cols)>3 else "-",
                    "l": cols[4].get_text(strip=True) if len(cols)>4 else "-",
                    "era": cols[8].get_text(strip=True) if len(cols)>8 else "-",
                    "whip": cols[9].get_text(strip=True) if len(cols)>9 else "-",
                    "k9": f"{k_f/ip_f*9:.1f}" if ip_f>0 else "-",
                    "bb9": f"{bb_f/ip_f*9:.1f}" if ip_f>0 else "-",
                }
        except Exception as e:
            print(f"  투수캐시({lc}) 실패: {e}")

def fetch_pitcher_stat(name):
    empty = {"era":"-","whip":"-","k9":"-","bb9":"-","w":"-","l":"-"}
    if name in ("미정","","-"): return empty
    _load_pitcher_cache()
    if name in _PITCHER_CACHE: return _PITCHER_CACHE[name]
    name_clean = re.sub(r"[\u3000\s]+", " ", name).strip()
    for k,v in _PITCHER_CACHE.items():
        if re.sub(r"[\u3000\s]+"," ",k).strip() == name_clean: return v
    return empty

ENG_PARTIAL = {
    "Yomiuri":"요미우리","Yakult":"야쿠르트","DeNA":"DeNA","Chunichi":"주니치",
    "Hanshin":"한신","Hiroshima":"히로시마","SoftBank":"소프트뱅크",
    "Softbank":"소프트뱅크","Nippon-Ham":"닛폰햄","ORIX":"오릭스","Orix":"오릭스",
    "Rakuten":"라쿠텐","Seibu":"세이부","Lotte":"롯데",
}

def _eng_to_kr(s):
    for k,v in ENG_PARTIAL.items():
        if k.lower() in s.lower(): return v
    return ""

def fetch_all_team_stats():
    stats = {}
    for lc,lg in [("c","CL"),("p","PL")]:
        try:
            r = SESS.get(f"https://npb.jp/bis/eng/{SEASON}/stats/std_{lc}.html", timeout=12)
            soup = BeautifulSoup(r.content.decode("utf-8","ignore"), "html.parser")
            for row in soup.select("table tbody tr"):
                cols = row.select("td")
                if len(cols)<6: continue
                kr = _eng_to_kr(cols[0].get_text(strip=True))
                if not kr: continue
                stats.setdefault(kr,{}).update({
                    "rank": cols[1].get_text(strip=True) if len(cols)>1 else "-",
                    "win":  cols[2].get_text(strip=True),
                    "lose": cols[3].get_text(strip=True),
                    "draw": cols[4].get_text(strip=True),
                    "wpct": cols[5].get_text(strip=True),
                    "league": lg,
                })
        except Exception as e:
            print(f"  순위({lc}) 실패: {e}")
    for lc in ["c","p"]:
        try:
            r = SESS.get(f"https://npb.jp/bis/eng/{SEASON}/stats/pit_{lc}.html", timeout=12)
            soup = BeautifulSoup(r.content.decode("utf-8","ignore"), "html.parser")
            bkt = {}
            for row in soup.select("table tbody tr"):
                cols = row.select("td")
                if len(cols)<9: continue
                kr = _eng_to_kr(cols[2].get_text(strip=True))
                if not kr: continue
                try:
                    ip = float(re.sub(r"[^\d.]","",cols[7].get_text()) or 0)
                    era = float(cols[8].get_text(strip=True))
                    if ip>0:
                        a,b = bkt.get(kr,(0.0,0.0)); bkt[kr]=(a+ip*era,b+ip)
                except: pass
            for kr,(w,t) in bkt.items():
                stats.setdefault(kr,{})
                stats[kr]["era"] = f"{w/t:.2f}" if t>0 else "-"
        except Exception as e:
            print(f"  팀ERA({lc}) 실패: {e}")
    for lc in ["c","p"]:
        try:
            r = SESS.get(f"https://npb.jp/bis/eng/{SEASON}/stats/bat_{lc}.html", timeout=12)
            soup = BeautifulSoup(r.content.decode("utf-8","ignore"), "html.parser")
            ob = {}
            for row in soup.select("table tbody tr"):
                cols = row.select("td")
                if len(cols)<15: continue
                kr = _eng_to_kr(cols[2].get_text(strip=True))
                if not kr: continue
                try: ob.setdefault(kr,[]).append(float(cols[14].get_text(strip=True)))
                except: pass
            for kr,lst in ob.items():
                stats.setdefault(kr,{})
                stats[kr]["ops"] = f"{sum(lst)/len(lst):.3f}"
        except Exception as e:
            print(f"  팀OPS({lc}) 실패: {e}")
    return stats

def _get_monthly_soup():
    """월간 일정 페이지 (경기 결과 링크 포함) — 이전 달 포함 최대 2개월 조회"""
    month     = int(NOW_KST.strftime("%m"))
    prev_month = month - 1 if month > 1 else 12
    months_to_try = [month, prev_month]

    for m in months_to_try:
        url = f"https://npb.jp/games/{SEASON}/schedule_{m:02d}_detail.html"
        try:
            r = SESS.get(url, timeout=12)
            if r.status_code != 200: continue
            html = r.content.decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            # 오늘 이전 날짜의 scores 링크만 카운트
            past_links = [
                a for a in soup.find_all("a", href=True)
                if re.search(rf"/scores/{SEASON}/(\d{{4}})/", a["href"])
                and re.search(rf"/scores/{SEASON}/(\d{{4}})/", a["href"]).group(1) < MMDD
            ]
            print(f"  월간일정: {url.split('/')[-1]} (이전결과 {len(past_links)}개)")
            if past_links:
                return soup
        except Exception as e:
            print(f"  일정페이지 실패({m:02d}): {e}")
    return _get_starter_soup()


def fetch_recent_form(team):
    """팀의 최근 5경기 폼 — 홈/원정 구분"""
    soup = _get_monthly_soup()
    score_pat = re.compile(rf"/scores/{SEASON}/(\d{{4}})/(\w+)-(\w+)-\d+/")
    seen = set()
    home_done = []
    away_done = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"): href = "https://npb.jp" + href
        m = score_pat.search(href)
        if not m: continue
        mmdd_link = m.group(1)
        if mmdd_link >= MMDD: continue  # 오늘 이후 제외
        key = mmdd_link + m.group(2) + m.group(3)
        if key in seen: continue
        seen.add(key)

        hkr = URL_CODE_KR.get(m.group(2), "")
        akr = URL_CODE_KR.get(m.group(3), "")
        if team not in (hkr, akr): continue

        text = a.get_text(separator=" ", strip=True)
        sm = re.search(r"(\d+)-(\d+)", text)
        if not sm: continue

        hs = int(sm.group(1)); vs = int(sm.group(2))
        is_home = (team == hkr)
        opp = akr if is_home else hkr
        my  = hs if is_home else vs
        op  = vs if is_home else hs

        if my > op:   icon = "✅"
        elif my < op: icon = "❌"
        else:         icon = "➖"

        entry = (icon, f"{opp}({my}:{op})")
        if is_home:
            if len(home_done) < 5: home_done.append(entry)
        else:
            if len(away_done) < 5: away_done.append(entry)

        if len(home_done) >= 5 and len(away_done) >= 5:
            break

    # 전체 최근 5경기 (홈/원정 합산)
    all_done = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"): href = "https://npb.jp" + href
        m = score_pat.search(href)
        if not m: continue
        mmdd_link = m.group(1)
        if mmdd_link >= MMDD: continue
        hkr = URL_CODE_KR.get(m.group(2), "")
        akr = URL_CODE_KR.get(m.group(3), "")
        if team not in (hkr, akr): continue
        text = a.get_text(separator=" ", strip=True)
        sm = re.search(r"(\d+)-(\d+)", text)
        if not sm: continue
        hs = int(sm.group(1)); vs = int(sm.group(2))
        is_home = (team == hkr)
        my  = hs if is_home else vs
        op  = vs if is_home else hs
        if my > op:   icon = "✅"
        elif my < op: icon = "❌"
        else:         icon = "➖"
        all_done.append(icon)
        if len(all_done) >= 5: break

    form_str = " ".join(all_done) if all_done else "-"

    # 홈/원정 폼 문자열
    h_form = " ".join(x[0] for x in home_done) if home_done else "-"
    a_form = " ".join(x[0] for x in away_done) if away_done else "-"

    return form_str, {
        "home": h_form,
        "away": a_form,
        "home_detail": [x[1] for x in home_done],
        "away_detail": [x[1] for x in away_done],
    }


def fetch_bullpen_fatigue(team):
    closer = CLOSER.get(team,"정보없음")
    soup = _get_starter_soup()
    close_count = 0; checked = set()
    score_pat = re.compile(rf"/scores/{SEASON}/(\d{{4}})/(\w+)-(\w+)-\d+/")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"): href = "https://npb.jp" + href
        m = score_pat.search(href)
        if not m: continue
        mmdd_link = m.group(1)
        if mmdd_link == MMDD: continue
        hkr = URL_CODE_KR.get(m.group(2),"")
        akr = URL_CODE_KR.get(m.group(3),"")
        if team not in (hkr, akr): continue
        text = a.get_text(separator=" ", strip=True)
        sm = re.search(r"\b(\d+)-(\d+)\b", text)
        if not sm: continue
        diff = abs(int(sm.group(1))-int(sm.group(2)))
        if mmdd_link not in checked and len(checked)<3:
            checked.add(mmdd_link)
            if diff<=2: close_count+=1
    if close_count==0: status=f"✅ {closer} 정상 예상"
    elif close_count==1: status=f"⚠️ {closer} 접전 1경기 등판 가능"
    else: status=f"🔴 {closer} {close_count}경기 접전 연속"
    return {"closer":closer,"status":status,"count":close_count}

def enrich(games, yesterday):
    print("  팀 스탯 수집...")
    all_stats = fetch_all_team_stats()
    _load_pitcher_cache()
    result = []
    for g in games:
        h,a = g["home"],g["away"]
        print(f"  📊 {a} @ {h}")
        hs  = all_stats.get(h,{})
        as_ = all_stats.get(a,{})
        hp  = fetch_pitcher_stat(g["home_pitcher"])
        ap  = fetch_pitcher_stat(g["away_pitcher"])
        hf, hf_info = fetch_recent_form(h)
        af, af_info = fetch_recent_form(a)
        hf_d = hf_info.get("home_detail", []) + hf_info.get("away_detail", [])
        af_d = af_info.get("home_detail", []) + af_info.get("away_detail", [])
        hf_home = hf_info.get("home", "-")
        hf_away = hf_info.get("away", "-")
        af_home = af_info.get("home", "-")
        af_away = af_info.get("away", "-")
        hbull = fetch_bullpen_fatigue(h)
        abull = fetch_bullpen_fatigue(a)
        h_yd = next((r for r in yesterday if r["home"]==h or r["away"]==h),None)
        a_yd = next((r for r in yesterday if r["home"]==a or r["away"]==a),None)
        result.append({**g,
            "hs":hs,"as_":as_,"hp":hp,"ap":ap,
            "hf":hf,"hf_d":hf_d,"af":af,"af_d":af_d,
            "hf_home":hf_home,"hf_away":hf_away,
            "af_home":af_home,"af_away":af_away,
            "hbull":hbull,"abull":abull,
            "h_yd":h_yd,"a_yd":a_yd,
        })
    return result

# ══════════════════════════════════════════════════
# Claude — 경기별 개별 분석 생성
# ══════════════════════════════════════════════════
def build_single_prompt(g: dict) -> str:
    h,a = g["home"],g["away"]
    hs  = g["hs"]; as_ = g["as_"]
    yd_date = (NOW_KST-timedelta(days=1)).strftime("%m월 %d일")

    def yd(data, team):
        if not data: return "경기 없음"
        return f"{data['summary']} ({'승' if data['winner']==team else '패'})"

    h_rank = f"{hs.get('rank','-')}위 {hs.get('win','-')}승{hs.get('lose','-')}패 (승률 {hs.get('wpct','-')}) ERA {hs.get('era','-')} OPS {hs.get('ops','-')}"
    a_rank = f"{as_.get('rank','-')}위 {as_.get('win','-')}승{as_.get('lose','-')}패 (승률 {as_.get('wpct','-')}) ERA {as_.get('era','-')} OPS {as_.get('ops','-')}"

    return f"""NPB 칼럼니스트로서 아래 경기 프리뷰를 300자 내외로 작성하세요.
마지막 줄은 반드시 "오늘의 예상: {{팀명}} 우세" 형식으로 끝내세요.
마크다운 기호 금지. 수치 나열 금지. 스토리텔링 우선.

경기: {a} @ {h} | {g.get('time','-')} JST | {g.get('venue','-')}
홈({h}): {h_rank}
원정({a}): {a_rank}
전날({yd_date}): 홈={yd(g['h_yd'],h)} / 원정={yd(g['a_yd'],a)}
선발:
  홈({h}) {g['home_pitcher']}: ERA {g['hp']['era']} WHIP {g['hp']['whip']} K/9 {g['hp']['k9']} BB/9 {g['hp']['bb9']} {g['hp']['w']}승{g['hp']['l']}패
  원정({a}) {g['away_pitcher']}: ERA {g['ap']['era']} WHIP {g['ap']['whip']} K/9 {g['ap']['k9']} BB/9 {g['ap']['bb9']} {g['ap']['w']}승{g['ap']['l']}패
불펜: 홈={g['hbull']['status']} / 원정={g['abull']['status']}
최근5경기: 홈={g['hf']} / 원정={g['af']}"""

def call_claude_single(prompt: str) -> str:
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_API_KEY,
                     "anthropic-version":"2023-06-01",
                     "content-type":"application/json"},
            json={"model":"claude-sonnet-4-6","max_tokens":800,
                  "messages":[{"role":"user","content":prompt}]},
            timeout=60,
        )
        if r.status_code!=200: return "분석 생성 실패"
        return r.json()["content"][0]["text"]
    except Exception as e:
        print(f"  Claude 오류: {e}")
        return "분석 생성 실패"

# ══════════════════════════════════════════════════
# 텔레그램 묶음 발송
# ══════════════════════════════════════════════════
def send_media_group(image_bytes_list: list):
    """사진 묶음 발송 (최대 10장)"""
    if not image_bytes_list:
        return

    # 텔레그램 최대 10장
    for batch_start in range(0, len(image_bytes_list), 10):
        batch = image_bytes_list[batch_start:batch_start+10]
        files = {}
        media = []
        for i, img_bytes in enumerate(batch):
            fname = f"photo{i}"
            files[fname] = (f"{fname}.jpg", img_bytes, "image/jpeg")
            media.append({"type":"photo","media":f"attach://{fname}"})

        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup",
                data={"chat_id": TELEGRAM_CHAT_ID,
                      "media": __import__('json').dumps(media)},
                files=files,
                timeout=60,
            )
            if r.status_code == 200:
                print(f"✅ 묶음 발송 완료 ({len(batch)}장)")
            else:
                print(f"⚠️ 발송 실패: {r.text[:200]}")
        except Exception as e:
            print(f"⚠️ 발송 오류: {e}")
        time.sleep(1)

def send_msg(text: str):
    """텍스트 메시지 발송 (헤더용)"""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id":TELEGRAM_CHAT_ID,"text":text},
            timeout=15)
    except Exception as e:
        print(f"⚠️ 메시지 발송 실패: {e}")

# ══════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════
def main():
    print(f"[{TODAY_KR}] NPB 프리뷰 시작...")

    print("📡 전날 결과 수집...")
    yesterday = fetch_yesterday_results()

    print("📡 오늘 경기 수집...")
    games = fetch_schedule()

    if not games:
        print("경기 없음")
        return

    print(f"  → {len(games)}경기")
    print("📊 데이터 보강...")
    enriched = enrich(games, yesterday)

    # 헤더 메시지 먼저 발송
    header = (f"⚾ NPB 데일리 프리뷰\n"
              f"📅 {TODAY_KR}\n🕐 {NOW_KR}\n"
              f"총 {len(games)}경기 분석")
    send_msg(header)
    time.sleep(0.5)

    # 경기별 이미지 카드 생성
    print("🎨 이미지 카드 생성...")
    image_list = []
    for i, g in enumerate(enriched, 1):
        print(f"  {i}/{len(enriched)} {g['away']} @ {g['home']} 분석 생성...")
        # Claude로 개별 분석 생성
        prompt  = build_single_prompt(g)
        preview = call_claude_single(prompt)
        # 이미지 카드 생성
        img_bytes = make_card(g, preview)
        image_list.append(img_bytes)
        print(f"  ✅ 카드 생성 완료")
        time.sleep(1)

    # 묶음 발송
    print("📨 이미지 묶음 발송...")
    send_media_group(image_list)
    print("🎉 완료!")

if __name__ == "__main__":
    main()
