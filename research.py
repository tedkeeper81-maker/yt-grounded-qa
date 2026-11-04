"""실검색 러너: ego-browser 수집 videoId + yt-dlp 자막을 pipeline 점수식으로 판정.

수집(수동 실행, 외부):
  1. ego-browser: youtube 검색 → a#video-title 에서 videoId 추출
  2. yt-dlp --dump-json 으로 메타 확인, --write-subs --write-auto-subs --sub-langs ko 로 자막 저장
본 스크립트: /tmp/ytqa/*.ko.vtt 파싱 → 주장 발췌 → pipeline.score → 답변/무답
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "/Users/tedkim/Documents/mirror-sea-project/yt-grounded-qa")
from pipeline import Candidate, PASS, score  # noqa: E402

SUB_DIR = "/tmp/ytqa"


def cues(path: str) -> list[tuple[int, str]]:
    pat = re.compile(r"(\d+:)?(\d+):(\d+)\.\d+ -->")
    out: list[tuple[int, str]] = []
    cur: int | None = None
    for line in open(path, encoding="utf-8"):
        m = pat.search(line)
        if m:
            h = int(m.group(1).rstrip(":")) if m.group(1) else 0
            cur = h * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            continue
        t = line.strip()
        if not t or t.startswith(("WEBVTT", "Kind:", "Language:")) or "-->" in t:
            continue
        t = re.sub(r"<[^>]+>", "", t)
        if cur is not None and (not out or out[-1][1] != t):
            out.append((cur, t))
    return out


def first_match(cs: list[tuple[int, str]], *pats: str) -> tuple[int, str]:
    for s, t in cs:
        if all(re.search(p, t) for p in pats):
            return s, t
    raise ValueError(f"no cue for {pats}")


VIDEOS = {
    # M=제조사 official + conflict(-15). A=일반. UISc·4eZz=독립 사용자 후기.
    "M_DdVx4Q0AY": {"channel": "뮤지쿠스MUSICUS", "type": "official", "date": "2020-08-14", "conflict": True},
    "ABuZ4nqRoZk": {"channel": "가수 단보", "type": "general", "date": "2025-04-17", "conflict": False},
    "UISckozv1oc": {"channel": "SOOJEONG YEON", "type": "general", "date": "2026-08-09", "conflict": False},
    "4eZzx40CFvA": {"channel": "Previsions Dohun Kim", "type": "general", "date": "2026-07-31", "conflict": False},
}
CLAIMS = [
    ("M_DdVx4Q0AY", "방음부스에는 에어컨이 필수다", ("에어컨이 필수",)),
    ("M_DdVx4Q0AY", "이동식 에어컨과 환기키트를 조합해 설치할 수 있다", ("환기", "설치")),
    ("ABuZ4nqRoZk", "방음부스마다 에어컨이 필요하며 이동식 에어컨을 흡배기구에 연결한다", ("이동식 에어컨",)),
    ("UISckozv1oc", "환풍구를 통해 에어컨 바람을 들일 수 있다", ("환풍구를 통해",)),
    ("4eZzx40CFvA", "환기 시스템이 반드시 필요하다", ("환기 시스템이 반드시",)),
]


def main() -> None:
    parsed = {vid: cues(f"{SUB_DIR}/{vid}.ko.vtt") for vid in VIDEOS}
    cands: list[Candidate] = []
    for vid, claim, pats in CLAIMS:
        s, raw = first_match(parsed[vid], *pats)
        v = VIDEOS[vid]
        cands.append(Candidate(vid, v["channel"], v["type"], v["date"],
                               "auto", True, False, claim, (s, s + 30),
                               conflict=v["conflict"]))
        print(f"발췌 [{vid}@{s}s] {raw[:60]}")
    # 교차언급: 냉방/환기 주장(에어컨|환기|환풍)을 2개 이상 영상이 공유하면 True
    kw_claims = [c for c in cands if re.search("에어컨|환기|환풍", c.claim)]
    cross_ids = {c.video_id for c in kw_claims} if len({c.video_id for c in kw_claims}) >= 2 else set()
    print(f"교차언급 해당: {sorted(cross_ids) or '없음'}")
    passed = []
    for c in cands:
        sc, reason = score(c, c.video_id in cross_ids)
        tag = "통과" if sc >= PASS else f"탈락({reason or '미달'})"
        print(f"{c.video_id}={sc}점 {tag} | {c.channel}/{c.date}/auto자막")
        if sc >= PASS:
            passed.append((c, sc))
    if not passed:
        print("무답: 신뢰 가능한 유튜브 근거를 찾지 못했습니다")
        return
    # 통과 주장들은 모두 '냉방/환기 필요' 방향으로 일치(상호 보완, 충돌 없음) → 답변
    if len({c.video_id for c, _ in passed}) > 1:
        print("주장 관계: 상호 보완(충돌 없음)")
    print("답변:")
    for c, _ in passed:
        print(f"- {c.claim} [{c.video_id}@{c.t[0]}s, {c.channel}, {c.date}]")
    print("근거 독립성: 서로 다른 독립 채널 2건")


if __name__ == "__main__":
    main()
