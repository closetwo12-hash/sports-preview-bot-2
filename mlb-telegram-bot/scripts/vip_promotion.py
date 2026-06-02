"""
VIP 조합상담 홍보 메시지
- 1시간마다 발송
- 20분 후 자동 삭제
"""

import os, time, requests

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

MESSAGE = """🔥 VIP 조합상담 문의

⚾ KBO · NPB · MLB
⚽ EPL · 월드컵

📩 VIP 조합상담 문의는
👉 @HC_VV77 클릭 후 문의"""

def send_message(text: str) -> int:
    """메시지 발송 후 message_id 반환"""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=15
        )
        if r.status_code == 200:
            msg_id = r.json()["result"]["message_id"]
            print(f"✅ 메시지 발송 완료 (id: {msg_id})")
            return msg_id
        else:
            print(f"⚠️ 발송 실패: {r.text[:100]}")
            return None
    except Exception as e:
        print(f"⚠️ 발송 오류: {e}")
        return None


def delete_message(message_id: int):
    """메시지 삭제"""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "message_id": message_id},
            timeout=15
        )
        if r.status_code == 200:
            print(f"✅ 메시지 삭제 완료 (id: {message_id})")
        else:
            print(f"⚠️ 삭제 실패: {r.text[:100]}")
    except Exception as e:
        print(f"⚠️ 삭제 오류: {e}")


def main():
    print("📢 VIP 홍보 메시지 발송...")
    msg_id = send_message(MESSAGE)

    if msg_id:
        print("⏳ 20분 대기...")
        time.sleep(20 * 60)  # 20분
        delete_message(msg_id)

    print("🎉 완료!")


if __name__ == "__main__":
    main()
