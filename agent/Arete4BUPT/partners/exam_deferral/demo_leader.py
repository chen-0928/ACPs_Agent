"""
简易 Leader 模拟器 - 用于演示 ADP + AIP 完整流程
1. 通过 /discover 发现 Partner
2. 读取 /acs 检查能力
3. 构造 TaskCommand 调用 /rpc
4. 解析 TaskResult
"""

import sys
import time
import httpx


PARTNER_URL = "http://localhost:8001"


def discover():
    print(f"\n{'─' * 60}")
    print("STEP 1: ADP 发现 Partner")
    print(f"{'─' * 60}")
    r = httpx.get(f"{PARTNER_URL}/discover", timeout=5)
    data = r.json()
    print(f"  ✓ 发现 Agent: {data['name']} ({data['agent_id']})")
    print(f"  ✓ AIC:       {data.get('aic', 'N/A')}")
    print(f"  ✓ 状态:      {data['status']}")
    print(f"  ✓ 技能:      {', '.join(data['skills'][:3])}...")
    return data


def fetch_acs():
    print(f"\n{'─' * 60}")
    print("STEP 2: 拉取 ACS 能力描述")
    print(f"{'─' * 60}")
    r = httpx.get(f"{PARTNER_URL}/acs", timeout=5)
    acs = r.json()
    print(f"  ✓ Agent:     {acs['name']}  v{acs['version']}")
    print(f"  ✓ 技能数:    {len(acs['skills'])}")
    for s in acs["skills"]:
        print(f"     - [{s['id']}] {s['name']}")
    return acs


def send_task(query: str, task_id: str, session_id: str = "leader-demo"):
    print(f"\n{'─' * 60}")
    print(f"STEP 3: AIP 发送 TaskCommand")
    print(f"{'─' * 60}")
    print(f"  📤 query: {query}")

    payload = {
        "task_id": task_id,
        "sender_id": "leader-demo",
        "receiver_id": "deferred-exam-partner",
        "query": query,
        "context": {"session_id": session_id},
    }
    start = time.perf_counter()
    r = httpx.post(f"{PARTNER_URL}/rpc", json=payload, timeout=30)
    elapsed = (time.perf_counter() - start) * 1000
    result = r.json()
    print(f"  📥 status:   {result['status']}")
    print(f"  📥 耗时:     {elapsed:.0f} ms")
    print(f"  📥 source:   {result.get('metadata', {}).get('source')}")
    print(f"  📥 skills:   {result.get('metadata', {}).get('skills_used')}")
    print(f"\n  ─── 回复内容 ───")
    print(result["answer"])
    return result


def main():
    try:
        httpx.get(f"{PARTNER_URL}/health", timeout=2)
    except Exception:
        print(f"❌ 无法连接到 Partner ({PARTNER_URL})")
        print(f"   请先在另一个终端运行: python main.py")
        sys.exit(1)

    print("=" * 60)
    print("  🤝  Leader → Partner 演示")
    print("=" * 60)

    discover()
    fetch_acs()

    queries = [
        "因病无法参加考试，怎么申请缓考？",
        "需要哪些材料？",
        "我有三门课要缓考",
    ]
    for i, q in enumerate(queries, 1):
        send_task(q, task_id=f"demo-{i:03d}")
        time.sleep(0.3)

    print(f"\n{'=' * 60}")
    print(f"  ✅ 演示完成。查看 Footprint: {PARTNER_URL}/footprint")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
