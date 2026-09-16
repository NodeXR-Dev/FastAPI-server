"""Memory Guard 판정 벤치마크.

시나리오 전체를 돌리면 회당 $0.24가 든다. Guard 판정 LLM만 떼어 내면
케이스당 $0.001 수준이라 프롬프트를 반복해서 비교할 수 있다.

케이스는 시나리오(텃밭)와 다른 도메인으로 만든다. 같은 도메인을 쓰면
프롬프트 예시가 답을 흘려 비교가 무의미해진다.
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")
os.environ.setdefault("LANGCHAIN_CALLBACKS_BACKGROUND", "false")

from langchain_community.callbacks.manager import get_openai_callback

from app.agent.llm.provider import get_agent_llm
from app.agent.prompt.memory_guard_prompt import MEMORY_GUARD_PROMPT
from app.agent.schema.realtime_agent_schema import GuardResult

# 회의에서 이미 정해진 것들 (검색되어 Guard에 제시되는 fact)
FACTS = """- id=f1; type=DesignFactType.DECISION; status=ACTIVE; content=교실 사물함은 나무 합판으로 만들고 철제는 쓰지 않기로 결정한다
- id=f2; type=DesignFactType.CONSTRAINT; status=ACTIVE; content=사물함 한 칸의 폭은 30센티미터를 넘기면 안 된다
- id=f3; type=DesignFactType.CONSTRAINT; status=ACTIVE; content=전체 제작비는 십만 원 이하여야 한다
- id=f4; type=DesignFactType.DECISION; status=ACTIVE; content=문에는 자물쇠를 달지 않고 열린 선반 구조로 간다
- id=f5; type=DesignFactType.RATIONALE; status=ACTIVE; content=철제는 무겁고 가공이 어려워서 배제했다"""


@dataclass
class Case:
    text: str
    violated: bool
    kind: str      # 라벨 근거
    note: str = ""


CASES = [
    # ── 진짜 위반: 결정/제약이 배제한 것을 채택한다 ───────────────────────
    Case("사물함은 튼튼하게 철제 프레임으로 만들자.", True, "결정 배제 항목 채택"),
    Case("한 칸 폭을 40센티로 넓히자.", True, "제약 초과 값 채택"),
    Case("문마다 번호 자물쇠를 달자.", True, "결정 배제 항목 채택"),
    Case("좋은 원목으로 가면 십오만 원쯤 드는데 그렇게 하자.", True, "제약 초과 값 채택"),
    Case("그냥 스테인리스 판으로 통째로 짜자.", True, "결정 배제 항목 채택"),

    # ── 준수: 결정을 따르는 발화 ──────────────────────────────────────────
    Case("합판을 얇은 걸로 쓰면 무게가 더 줄겠다.", False, "결정 준수"),
    Case("자물쇠가 없으니까 칸마다 이름표를 붙이자.", False, "결정 준수"),
    Case("폭은 28센티로 하면 딱 맞겠다.", False, "제약 준수"),
    Case("합판이라 가공이 쉬워서 우리끼리 만들 수 있어.", False, "결정 지지"),

    # ── 집행: 제약을 지키라고 말하는 발화 (이전 오탐 유형) ────────────────
    Case("그건 십이만 원이라 예산을 넘어. 다른 걸 찾자.", False, "제약 집행"),
    Case("40센티는 기준을 넘으니까 줄이자.", False, "제약 집행"),
    Case("철제는 안 쓰기로 했으니까 그 방안은 빼자.", False, "결정 집행"),

    # ── 같은 주제지만 위반이 아닌 발화 ────────────────────────────────────
    Case("사물함 색은 흰색으로 칠하자.", False, "무관한 제안"),
    Case("합판은 어디서 사지?", False, "질문"),
    Case("응 그게 좋겠다.", False, "리액션"),
    Case("사물함을 교실 뒤쪽 벽에 붙이자.", False, "무관한 제안"),

    # ── 간접 추론이 필요한 발화 (가정을 더해야만 위반) ────────────────────
    Case("경첩이랑 손잡이는 금속으로 사 오자.", False, "부품 금속은 프레임 결정과 별개"),
    Case("더 튼튼하게 만들 방법을 찾아보자.", False, "가정을 더해야 위반"),
]


async def run(label: str) -> dict:
    chain = MEMORY_GUARD_PROMPT | get_agent_llm().with_structured_output(GuardResult)
    rows = []
    for case in CASES:
        result = await chain.ainvoke(
            {"normalized_text": case.text, "facts_context": FACTS},
        )
        guard = (
            result if isinstance(result, GuardResult)
            else GuardResult.model_validate(result)
        )
        rows.append({
            "text": case.text, "expected": case.violated, "kind": case.kind,
            "actual": bool(guard.violated), "confidence": guard.confidence,
            "type": guard.violation_type, "reason": guard.reason,
        })

    tp = sum(1 for r in rows if r["expected"] and r["actual"])
    fp = sum(1 for r in rows if not r["expected"] and r["actual"])
    fn = sum(1 for r in rows if r["expected"] and not r["actual"])
    tn = sum(1 for r in rows if not r["expected"] and not r["actual"])
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print(f"\n{'='*80}\n[{label}]  {len(CASES)}건\n{'='*80}")
    for r in rows:
        ok = "O" if r["actual"] == r["expected"] else "X"
        print(f"  {ok} 판정={str(r['actual']):5s} 기대={str(r['expected']):5s} "
              f"conf={r['confidence']:.2f} [{r['kind']}] {r['text']}")
        if r["actual"] != r["expected"]:
            print(f"      → {r['reason'][:88]}")
    print(f"\n  정확도={(tp + tn) / len(rows):.3f}  정밀도={precision:.3f}  "
          f"재현율={recall:.3f}  F1={f1:.3f}")
    print(f"  TP={tp} FP={fp} FN={fn} TN={tn}")

    # 스스로 충돌이 없다고 쓰면서 경고를 내는 경우
    contradictory = [
        r for r in rows
        if r["actual"] and ("충돌하지 않" in r["reason"] or "위반하지 않" in r["reason"])
    ]
    if contradictory:
        print(f"  ⚠️ 이유문이 스스로 '충돌 없음'이라고 말하면서 경고: {len(contradictory)}건")

    return {"label": label, "precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn, "rows": rows}


async def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "current"
    with get_openai_callback() as tracker:
        result = await run(label)
        cost = (tracker.prompt_tokens / 1e6 * 0.40
                + tracker.completion_tokens / 1e6 * 1.60)
        print(f"\n  비용: ${cost:.4f} "
              f"(in {tracker.prompt_tokens:,} / out {tracker.completion_tokens:,})")
    path = f"artifacts/agent-scenarios/guard-bench-{label}.json"
    os.makedirs("artifacts/agent-scenarios", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(f"  저장: {path}")


asyncio.run(main())
