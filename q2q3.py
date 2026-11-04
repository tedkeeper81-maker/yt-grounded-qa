"""질문2(결로)·질문3(가격) 검증 러너. research.py와 같은 판정 로직을 재사용."""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "/Users/tedkim/Documents/mirror-sea-project/yt-grounded-qa")
from pipeline import Candidate, PASS, score  # noqa: E402
from research import cues  # noqa: E402

SUB_DIR = "/tmp/ytqa"


def judge(question: str, videos: dict, claims: list) -> None:
    print(f"### 질문: {question}")
    parsed = {vid: cues(f"{SUB_DIR}/{vid}.ko.vtt") for vid in videos}
    cands: list[Candidate] = []
    for vid, claim, pats, has_num in claims:
        v = videos[vid]
        s = None
        for t, text in parsed[vid]:
            if all(re.search(p, text) for p in pats):
                s = t
                break
        if s is None:
            print(f"발췌 실패(제외): {vid} {pats}")
            continue
        cands.append(Candidate(vid, v["channel"], v["type"], v["date"],
                               v["subs"], True, has_num, claim, (s, s + 30),
                               conflict=v["conflict"]))
        print(f"발췌 [{vid}@{s}s] {claim[:50]}")
    fams = [c for c in cands if re.search("결로|습기|곰팡이|환기|가격|만원|견적|비용", c.claim)]
    cross = {c.video_id for c in fams} if len({c.video_id for c in fams}) >= 2 else set()
    passed = []
    for c in cands:
        sc, reason = score(c, c.video_id in cross)
        tag = "통과" if sc >= PASS and not (sc == PASS) else (f"탈락(경계값 보수판정)" if sc == PASS else f"탈락({reason or '미달'})")
        # 경계값(60)은 보수적으로 탈락 취급
        print(f"{c.video_id}={sc}점 {tag}")
        if sc > PASS:
            passed.append(c)
    if not passed:
        print("무답: 신뢰 가능한 유튜브 근거를 찾지 못했습니다\n")
        return
    print("답변:")
    for c in passed:
        print(f"- {c.claim} [{c.video_id}@{c.t[0]}s, {c.channel}, {c.date}]")
    print()


Q2_VIDEOS = {
    "jbBzVoVBmYE": {"channel": "종빈허", "type": "general", "date": "2026-08-23", "subs": "manual", "conflict": False},
}
Q2_CLAIMS = [
    ("jbBzVoVBmYE", "환기가 안 되면 곰팡이가 슨다", ("환기가 안 돼서",), False),
]

Q3_VIDEOS = {
    "FeauDNhUYiY": {"channel": "미친감성", "type": "general", "date": "2026-04-05", "subs": "auto", "conflict": False},
    "NwmQaA9xdpY": {"channel": "MONO SYSTEM WALLs", "type": "official", "date": "2026-06-25", "subs": "auto", "conflict": True},
}
Q3_CLAIMS = [
    ("FeauDNhUYiY", "여러 업체 견적을 비교하면 100만원대에도 가능하다", ("100만원",), True),
    ("NwmQaA9xdpY", "평균 시공 견적은 대략 300만원이며 견적서를 교차검증해야 한다", ("300만",), True),
]


def main() -> None:
    judge("방음부스 결로 어떻게 막나?", Q2_VIDEOS, Q2_CLAIMS)
    judge("방음부스 가격 얼마?", Q3_VIDEOS, Q3_CLAIMS)


if __name__ == "__main__":
    main()
