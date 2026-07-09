"""Batch E2E skill test via Teams — C class (MTK internal tools)."""
import sys, re, time, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'C:/Users/mtk12265/.claude/skills/teams')
sys.path.insert(0, 'C:/Users/mtk12265/.claude/skills/teams/scripts')
from _common import get_teams_client

CONV_ID = '19:6e8a676c-2a6b-4d52-873d-e358f85f6ee1_d6d4a33b-60fe-49ff-b57e-baa6edbb67b8@unq.gbl.spaces'

# Test prompts — concise to avoid context bloat
TESTS = [
    ("C5", "ims_volte_vonr_analysis", "用 ims_volte_vonr_analysis skill 說明 SIP 403 Forbidden 的常見原因"),
    ("C6", "nas_registration_and_security", "用 nas_registration_and_security skill 說明 5G Registration Reject 常見 cause value"),
    ("C7", "rrc_mobility_and_configuration", "用 rrc_mobility_and_configuration skill 說明 RRC Connection Setup 失敗的常見原因"),
    ("C8", "ps_gai_sop", "用 ps_gai_sop skill 說明 PS Lv1 System Analysis 的第一步驟"),
    ("C9", "trace_analysis", "用 trace_analysis skill 列出 MTK modem trace 的主要類型"),
    ("C10", "l1_l2_hw_performance", "用 l1_l2_hw_performance skill 列出 L1/L2 performance 常見問題類型"),
    ("C11", "nlt_trace", "用 nlt_trace skill 說明如何透過 NLT IPC 讀取 L1 trace"),
    ("C12", "nlt_log_cr", "用 nlt_log_cr skill 說明 NLT 直連 CR 資訊的用途"),
    ("C13", "nlt_index", "用 nlt_index skill 說明 timestamp 轉 FRC index 的流程"),
    ("C14", "modem_highlighted_log_analysis", "用 modem_highlighted_log_analysis skill 說明 highlighted log 的分析步驟概述"),
    ("C15", "log_analysis_methodology", "用 log_analysis_methodology skill 說明 modem log 分析方法論的核心步驟"),
]

def wait_for_reply(client, since_id, timeout=120):
    """Poll until we get a bot reply with id > since_id, or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        msgs = client.messages.get(CONV_ID, limit=5)
        for m in msgs:
            mid = m.get('id', '0')
            if mid > since_id and '**🤖' in m.get('content', ''):
                raw = m.get('content', '')
                clean = re.sub(r'<[^>]+>', ' ', raw).strip()
                clean = re.sub(r'\s+', ' ', clean)
                return mid, clean
        time.sleep(5)
    return None, "TIMEOUT"

def run_test(client, label, skill, prompt, last_id):
    print(f"\n--- {label} {skill} ---")
    client.messages.send(CONV_ID, prompt)
    print(f"  SENT, waiting...")
    mid, reply = wait_for_reply(client, last_id, timeout=120)
    if mid is None:
        print(f"  ❌ TIMEOUT (no reply in 120s)")
        return last_id, "TIMEOUT"
    # Check if reply mentions skill or relevant content
    if len(reply) > 80:
        print(f"  ✅ PASS (reply {len(reply)} chars)")
        print(f"  preview: {reply[:200]}")
        return mid, "PASS"
    else:
        print(f"  ⚠️ Short reply: {reply[:200]}")
        return mid, "SHORT"

def main():
    client = get_teams_client()
    # Get current last msg id
    msgs = client.messages.get(CONV_ID, limit=1)
    last_id = msgs[0].get('id', '0') if msgs else '0'
    print(f"Starting from msg id={last_id}")
    
    results = {}
    for label, skill, prompt in TESTS:
        last_id, status = run_test(client, label, skill, prompt, last_id)
        results[label] = (skill, status)
        time.sleep(2)  # small gap between tests
    
    print("\n\n=== RESULTS ===")
    for label in sorted(results):
        skill, status = results[label]
        emoji = "✅" if status == "PASS" else "⏭️" if status == "SHORT" else "❌"
        print(f"  {emoji} {label} {skill} — {status}")

if __name__ == '__main__':
    main()
