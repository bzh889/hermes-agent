"""
Teams Skill E2E Test Runner
Usage: python scripts/teams_skill_test.py [skill_name]
Sends a test command to Teams, waits for reply, checks output.
"""
import sys, os, time, re

# 加入 Teams skill 路徑
TEAMS_SKILL = "C:/Users/mtk12265/.claude/skills/teams"
sys.path.insert(0, TEAMS_SKILL)
sys.path.insert(0, f"{TEAMS_SKILL}/scripts")

from _common import get_teams_client

CONV_ID = "19:6e8a676c-2a6b-4d52-873d-e358f85f6ee1_d6d4a33b-60fe-49ff-b57e-baa6edbb67b8@unq.gbl.spaces"
client = get_teams_client()


def get_last_msg_id():
    msgs = client.messages.get(CONV_ID, limit=1)
    return msgs[0].get("id") if msgs else None


def send_msg(text):
    client.messages.send(CONV_ID, text)
    print(f"  SENT: {text!r}")


def wait_for_reply(after_id, timeout=60, poll=2):
    """等待 after_id 之後出現新訊息，回傳 (content, msg_id)"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        msgs = client.messages.get(CONV_ID, limit=10)
        for m in reversed(msgs):
            mid = m.get("id", "")
            if mid and mid > after_id:
                # 取 content
                body = m.get("body", {})
                if isinstance(body, dict):
                    content = body.get("content", "")
                else:
                    content = str(body)
                # 去掉 HTML tags
                clean = re.sub(r'<[^>]+>', '', content).strip()
                if clean and "Hermes" not in clean[:20]:  # 跳過 echo
                    continue
                if clean:
                    return clean, mid
        time.sleep(poll)
    return None, None


def test_skill(skill_cmd, test_phrase, wait_sec=45):
    """通用測試 — 發指令，等回覆，檢查回覆含 test_phrase"""
    last_id = get_last_msg_id()
    send_msg(skill_cmd)
    print(f"  Waiting up to {wait_sec}s for reply...")
    reply, reply_id = wait_for_reply(last_id, timeout=wait_sec)
    if reply is None:
        print(f"  FAIL: No reply within {wait_sec}s")
        return False
    if test_phrase and test_phrase.lower() not in reply.lower():
        print(f"  PARTIAL: Reply received but missing '{test_phrase}'")
        print(f"  Reply preview: {reply[:200]}")
        return "partial"
    print(f"  PASS: Got reply, length={len(reply)}")
    print(f"  Preview: {reply[:150]}")
    return True


if __name__ == "__main__":
    skill = sys.argv[1] if len(sys.argv) > 1 else "ascii-art"

    TESTS = {
        "ascii-art": ("/ascii-art 用 pyfiglet 把 HERMES 寫成大字", ""),
        "arxiv":     ("幫我搜尋 arxiv 上關於 LLM reasoning 的最新論文，列出 3 篇", "arxiv"),
        "humanizer": ("幫我把這段話人性化：The system leverages advanced AI capabilities to optimize throughput.", ""),
        "youtube":   ("幫我摘要這個 YouTube: https://www.youtube.com/watch?v=dQw4w9WgXcQ", ""),
    }

    if skill in TESTS:
        cmd, phrase = TESTS[skill]
        result = test_skill(cmd, phrase)
        sys.exit(0 if result else 1)
    else:
        print(f"Unknown skill: {skill}")
        print(f"Available: {list(TESTS.keys())}")
        sys.exit(1)
