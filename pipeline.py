"""yt-grounded-qa 최소 파이프라인 (설계서 v1.1 구현, 외부 호출 없음)."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date

TODAY = date(2026, 11, 4)
PASS = 60


@dataclass
class Candidate:
    video_id: str
    channel: str
    channel_type: str  # official | general | promo
    date: str | None  # YYYY-MM-DD
    subtitles: str  # manual | auto | none
    timestamp_ok: bool
    has_numbers_source: bool
    claim: str
    t: tuple[int, int]


def structure(question: str) -> dict:
    return {
        "intent": question.strip(),
        "premises": [],
        "ambiguities": [],
        "answer_format": "문장별 근거 표기",
    }


def extract_keywords(s: dict) -> list[str]:
    toks = [w.strip("?,. ") for w in s["intent"].split()]
    kws = [w for w in toks if len(w) >= 2][:7]
    return kws


def _recency_score(d: str | None) -> int:
    if not d:
        return 0
    y, m, dd = map(int, d.split("-"))
    days = (TODAY - date(y, m, dd)).days
    if days <= 365:
        return 20
    if days <= 365 * 3:
        return 10
    return 0


def score(c: Candidate, cross: bool) -> tuple[int, str]:
    if c.subtitles == "none" or not c.date or c.channel_type == "promo" or not c.timestamp_ok:
        return 0, "필수 탈락"
    s = 0
    s += 40 if c.channel_type == "official" else 10
    s += _recency_score(c.date)
    s += 20 if cross else 0
    s += 10 if c.has_numbers_source else 0
    s += 10 if c.subtitles == "manual" else 5
    return s, ""


def run_case(question: str, cands: list[Candidate]) -> dict:
    s = structure(question)
    kws = extract_keywords(s)
    if not kws:
        return {"answer": None, "no_answer": "키워드 0개"}
    if not cands:
        return {"answer": None, "no_answer": f"검색 0건 | 키워드={kws}"}
    claims = {c.claim for c in cands}
    scored = []
    for c in cands:
        cross = sum(1 for o in cands if o.claim == c.claim) >= 2
        sc, reason = score(c, cross)
        scored.append((c, sc, reason))
    passed = [(c, sc) for c, sc, _ in scored if sc >= PASS]
    if not passed:
        detail = "; ".join(f"{c.video_id}={sc}({r or '미달'})" for c, sc, r in scored)
        return {"answer": None, "no_answer": f"전부 60점 미만 | {detail}"}
    # 충돌 검사: 통과 후보의 claim이 2종 이상이면 무답
    if len({c.claim for c, _ in passed}) > 1:
        return {"answer": None, "no_answer": "통과 후보 간 주장 충돌"}
    ev = [
        {"claim": c.claim, "videoId": c.video_id, "t": list(c.t),
         "channel": c.channel, "date": c.date}
        for c, _ in passed
    ]
    onto = {"concepts": [{"id": "c1", "label": kws[0]}], "relations": [],
            "evidences": ev}
    lines = [f"{e['claim']} [{e['videoId']}@{e['t'][0]}s]" for e in ev]
    return {"answer": "\n".join(lines), "ontology": onto,
            "scores": {c.video_id: sc for c, sc in passed}}


def main() -> None:
    q1 = "방음부스 환기 방법은?"
    c1 = [
        Candidate("vA", "공식A", "official", "2026-06-01", "manual", True, True, "저소음팬+흡기구 분리", (120, 150)),
        Candidate("vB", "일반B", "general", "2026-08-01", "manual", True, True, "저소음팬+흡기구 분리", (60, 90)),
    ]
    q2 = "방음부스 1만원에 산다?"
    c2 = [
        Candidate("vC", "일반C", "general", "2020-01-01", "auto", True, False, "1만원 가능", (10, 30)),
    ]
    q3 = "존재하지 않는 질문 xyz?"
    c3: list[Candidate] = []
    for i, (q, c) in enumerate([(q1, c1), (q2, c2), (q3, c3)], 1):
        r = run_case(q, c)
        print(f"--- Q{i}: {q}")
        if r.get("answer"):
            print("답변:")
            print(r["answer"])
            print(f"점수: {r['scores']}")
        else:
            print(f"무답: {r['no_answer']}")
    print("검증: Q1 답변·Q2 무답(저득점)·Q3 무답(0건) 기대와 일치하면 통과")


if __name__ == "__main__":
    main()
