"""임베딩이 주제를 구분할 신호를 갖고 있는지 직접 측정.

threshold 튜닝이 가능하려면 '같은 주제 쌍'의 유사도가 '다른 주제 쌍'보다
일관되게 높아야 한다. 두 분포가 겹치면 어떤 경계값도 통하지 않는다.
"""

import os
from itertools import combinations

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

from app.service.utterance.embedding_service import EmbeddingService

MEETING = [
    ("자전거 거치대를 어디에 세울지부터 정하자.", "위치", False),
    ("운동장 옆은 공이 날아와서 위험할 것 같아.", "위치", False),
    ("후문 쪽이 그늘도 지고 지나다니기도 편해.", "위치", False),
    ("응 그게 낫겠다.", "위치", True),
    ("그럼 후문 쪽으로 하자.", "위치", False),
    ("근데 비 오면 자전거가 다 젖잖아.", "지붕", False),
    ("지붕을 씌우는 건 어때?", "지붕", False),
    ("투명한 아크릴로 하면 안이 환하게 보일 거야.", "지붕", False),
    ("아크릴은 한 장에 이만 원쯤 한대.", "지붕", False),
    ("그건 좀 비싼데.", "지붕", True),
    ("그러면 천막 천으로 하는 게 싸지 않을까?", "지붕", False),
    ("좋아 천막으로 가자.", "지붕", False),
    ("자물쇠는 어떻게 걸게 할지도 정해야 해.", "잠금", False),
    ("고리를 위쪽에 하나 더 달면 편할 것 같아.", "잠금", False),
    ("맞아 그거 좋다.", "잠금", True),
    ("체인 자물쇠도 걸리게 고리를 굵게 만들자.", "잠금", False),
    ("고리가 굵으면 작은 자물쇠는 안 들어갈 수도 있어.", "잠금", False),
    ("그럼 굵은 고리랑 얇은 고리를 하나씩 달자.", "잠금", False),
]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb)


def auc(positives, negatives):
    """같은 주제 쌍이 다른 주제 쌍보다 높게 나올 확률. 0.5면 신호 없음."""
    wins = ties = 0
    for p in positives:
        for n in negatives:
            if p > n:
                wins += 1
            elif p == n:
                ties += 1
    total = len(positives) * len(negatives)
    return (wins + 0.5 * ties) / total if total else 0.0


def describe(name, values):
    values = sorted(values)
    n = len(values)
    return (
        f"  {name:24s} n={n:4d}  평균={sum(values)/n:.3f}  "
        f"최소={values[0]:.3f}  중앙={values[n//2]:.3f}  최대={values[-1]:.3f}"
    )


service = EmbeddingService()
embeddings = [service.embed_text(text) for text, _l, _r in MEETING]
labels = [label for _t, label, _r in MEETING]
reactions = [reaction for _t, _l, reaction in MEETING]

same, diff = [], []
same_no_reaction, diff_no_reaction = [], []
for i, j in combinations(range(len(MEETING)), 2):
    score = cosine(embeddings[i], embeddings[j])
    if labels[i] == labels[j]:
        same.append(score)
        if not (reactions[i] or reactions[j]):
            same_no_reaction.append(score)
    else:
        diff.append(score)
        if not (reactions[i] or reactions[j]):
            diff_no_reaction.append(score)

print("=" * 82)
print("발화 쌍 유사도 분포")
print("=" * 82)
print(describe("같은 주제", same))
print(describe("다른 주제", diff))
print(f"\n  분리도 AUC = {auc(same, diff):.3f}   (1.0=완벽, 0.5=신호 없음)")

print("\n" + "=" * 82)
print("리액션 발화를 뺀 경우")
print("=" * 82)
print(describe("같은 주제", same_no_reaction))
print(describe("다른 주제", diff_no_reaction))
print(f"\n  분리도 AUC = {auc(same_no_reaction, diff_no_reaction):.3f}")

print("\n" + "=" * 82)
print("리액션 발화가 같은 주제의 직전 발화와 얼마나 닮았나")
print("=" * 82)
for index, (text, label, reaction) in enumerate(MEETING):
    if reaction:
        prev = cosine(embeddings[index], embeddings[index - 1])
        print(f"  '{text}' vs 직전 발화 = {prev:.3f}   (주제={label})")

print("\n" + "=" * 82)
print("직전 발화와의 유사도: 주제가 이어질 때 vs 바뀔 때")
print("=" * 82)
cont, shift = [], []
for index in range(1, len(MEETING)):
    score = cosine(embeddings[index], embeddings[index - 1])
    (cont if labels[index] == labels[index - 1] else shift).append(score)
print(describe("주제 계속", cont))
print(describe("주제 전환", shift))
print(f"\n  분리도 AUC = {auc(cont, shift):.3f}")
