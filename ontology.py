"""규칙 기반 온톨로지 빌더 (외부 호출 없음, 결정적).

입력: 발췌 목록 {claim, video_id, t, channel, date, context}
출력: 설계서 §3 스키마 {concepts, relations, evidences}
관계 3종: 필요 / 방법 / 원인. 패턴에 매칭된 것만 생성하며,
근거 없는 관계는 만들지 않습니다.
"""
from __future__ import annotations

import re

DOMAIN_SEEDS = [
    "방음부스", "에어컨", "이동식에어컨", "환기", "환기키트", "환풍구",
    "흡배기구", "선풍기", "곰팡이", "결로", "습기", "실외기",
]

PARTICLES = re.compile(r"(은|는|이|가|을|를|에|에서|으로|로|과|와|의|도|만|밖에|부터|까지)$")


def norm(w: str) -> str:
    w = w.strip(" .,·…?!\"'()")
    for _ in range(2):
        nw = PARTICLES.sub("", w)
        if nw == w or len(nw) < 2:
            break
        w = nw
    return w


def find_terms(text: str) -> list[str]:
    found = []
    for seed in DOMAIN_SEEDS:
        base = seed.replace("이동식에어컨", "이동식.?에어컨")
        if re.search(base, text):
            found.append(seed)
    return found


def split_nouns(text: str) -> list[str]:
    toks = re.findall(r"[가-힣]{2,}", text)
    out = []
    for t in toks:
        n = norm(t)
        if len(n) >= 2 and n not in out:
            out.append(n)
    return out


def extract_relations(claim: str, ev: dict) -> list[dict]:
    rels = []
    terms = find_terms(claim)
    # 필요: "X 필요/필수"
    if re.search(r"필요|필수", claim):
        for x in terms:
            if x != "방음부스":
                rels.append({"from": x, "type": "필요", "to": "방음부스",
                             "evidence": ev})
    # 방법: "X로/으로 Y(설치|연결|공급|활용)"
    m = re.search(r"(\S+?)(?:으로|로)\s*(\S+?)(?:을|를)?\s*(설치|연결|공급|활용)", claim)
    if m:
        a, b = norm(m.group(1)), norm(m.group(2)) + m.group(3)
        if len(a) >= 2:
            rels.append({"from": a, "type": "방법", "to": b, "evidence": ev})
    # 원인: "X 때문에/해서/으로 Y" + 부정 결과(안 돼/곰팡이/더위)
    if re.search(r"안 |못 |곰팡이|더위|답답", claim) and re.search(r"환기", claim):
        rels.append({"from": "환기 부족", "type": "원인", "to": "곰팡이·더위",
                     "evidence": ev})
    return rels


def build(excerpts: list[dict]) -> dict:
    concepts: dict[str, dict] = {}
    relations: list[dict] = []
    evidences: list[dict] = []
    for ex in excerpts:
        blob = ex["claim"] + " " + ex.get("context", "")
        for n in split_nouns(blob):
            concepts.setdefault(n, {"id": f"c{len(concepts) + 1}", "label": n,
                                    "aliases": []})
        ev = {"claim": ex["claim"], "videoId": ex["video_id"], "t": ex["t"],
              "channel": ex["channel"], "date": ex["date"]}
        evidences.append(ev)
        relations.extend(extract_relations(ex["claim"], ev))
    # 관계에 등장하는 개념이 concepts에 없으면 추가
    labels = {c["label"] for c in concepts.values()}
    for r in relations:
        for k in ("from", "to"):
            if r[k] not in labels:
                concepts[r[k]] = {"id": f"c{len(concepts) + 1}", "label": r[k],
                                  "aliases": []}
                labels.add(r[k])
    # 관계·주장에 등장하지 않는 명사는 버림(고아 개념 제거)
    used = {r["from"] for r in relations} | {r["to"] for r in relations}
    for ex in excerpts:
        used.update(find_terms(ex["claim"]))
    concepts = {k: v for k, v in concepts.items() if v["label"] in used}
    return {"concepts": list(concepts.values()), "relations": relations,
            "evidences": evidences}


def validate(onto: dict) -> None:
    labels = {c["label"] for c in onto["concepts"]}
    assert onto["relations"], "관계 0건: 온톨로지 아님"
    for r in onto["relations"]:
        assert r["from"] in labels and r["to"] in labels, f"고아 관계: {r}"
        assert r["evidence"]["videoId"], "근거 없는 관계"
    for e in onto["evidences"]:
        assert e["videoId"] and e["t"], "근거 미연결 발췌"


def demo() -> None:
    import sys
    sys.path.insert(0, "/Users/tedkim/Documents/mirror-sea-project/yt-grounded-qa")
    from research import cues  # noqa: E402
    pool = [
        ("M_DdVx4Q0AY", "방음부스에는 에어컨이 필수다", ("에어컨이 필수",),
         "뮤지쿠스MUSICUS", "2020-08-14"),
        ("ABuZ4nqRoZk", "방음부스마다 에어컨이 필요하며 이동식 에어컨을 흡배기구에 연결한다", ("이동식 에어컨",),
         "가수 단보", "2025-04-17"),
        ("UISckozv1oc", "환풍구를 통해 에어컨 바람을 들일 수 있다", ("환풍구를 통해",),
         "SOOJEONG YEON", "2026-08-09"),
        ("4eZzx40CFvA", "환기 시스템이 반드시 필요하다", ("환기 시스템이 반드시",),
         "Previsions Dohun Kim", "2026-07-31"),
    ]
    excerpts = []
    for vid, claim, pats, ch, dt in pool:
        cs = cues(f"/tmp/ytqa/{vid}.ko.vtt")
        idx = next(i for i, (_, t) in enumerate(cs)
                   if all(re.search(p, t) for p in pats))
        s, _ = cs[idx]
        ctx = " ".join(t for _, t in cs[max(0, idx - 2):idx + 3])
        excerpts.append({"claim": claim, "video_id": vid, "t": [s, s + 30],
                         "channel": ch, "date": dt, "context": ctx})
    onto = build(excerpts)
    validate(onto)
    print(f"개념 {len(onto['concepts'])}개, 관계 {len(onto['relations'])}개, "
          f"근거 {len(onto['evidences'])}건")
    for r in onto["relations"]:
        e = r["evidence"]
        print(f"- {r['from']} --{r['type']}--> {r['to']}  "
              f"[{e['videoId']}@{e['t'][0]}s]")


if __name__ == "__main__":
    demo()
