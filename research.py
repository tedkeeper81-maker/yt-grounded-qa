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
    # channel_type 근거: M=제조사 공식 채널의 자사 부스 설치 시연 → official(이해충돌 주의),
    # A=일반 사용자 채널 → general. 주인님 판정으로 뒤집을 수 있음.
    "M_DdVx4Q0AY": {"channel": "뮤지쿠스MUSICUS", "type": "official", "date": "2020-08-14"},
    "ABuZ4nqRoZk": {"channel": "가수 단보", "type": "general", "date": "2025-04-17"},
}

CLAIMS = [
    ("M_DdVx4Q0AY", "방음부스에는 에어컨이 필수다", ("에어컨이 필수",)),
    ("M_DdVx4Q0AY", "이동식 에어컨과 환기키트를 조합해 설치할 수 있다", ("환기", "설치")),
    ("ABuZ4nqRoZk", "방음부스마다 에어컨이 필요하며 이동식 에어컨을 흡배기구에 연결한다", ("이동식 에어컨",)),
]


def main() -> None:
    parsed = {vid: cues(f"{SUB_DIR}/{vid}.ko.vtt") for vid in VIDEOS}
    cands: list[Candidate] = []
    for vid, claim, pats in CLAIMS:
        s, raw = first_match(parsed[vid], *pats)
        v = VIDEOS[vid]
        cands.append(Candidate(vid, v["channel"], v["type"], v["date"],
                               "auto", True, False, claim, (s, s + 30)))
        print(f"발췌 [{vid}@{s}s] {raw[:60]}")
    # 교차언급: '에어컨' 주장을 2개 이상 영상이 공유하면 True
    kw_claims = [c for c in cands if "에어컨" in c.claim]
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
    if len({c.claim for c, _ in passed}) > 1:
        # 동일 영상 내 복수 주장은 허용, 이종 영상 충돌만 무답
        if len({c.video_id for c, _ in passed}) > 1:
            print("무답: 통과 후보 간 주장 충돌")
            return
    print("답변:")
    for c, _ in passed:
        print(f"- {c.claim} [{c.video_id}@{c.t[0]}s, {c.channel}, {c.date}]")
    print("주의: M_DdVx4Q0AY는 제조사 공식 채널이며 판매 이해관계가 있습니다")


if __name__ == "__main__":
    main()
