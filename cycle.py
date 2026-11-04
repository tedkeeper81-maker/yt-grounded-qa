"""질문-답변 한 사이클 러너. 한 명령으로 수집부터 답변까지.

    python3 cycle.py "방음부스 층간소음 효과 있어?"

단계: 구조화 → 키워드 → ego-browser 검색 → yt-dlp 메타/자막 →
발췌 → v1.3 점수 → 온톨로지 → 근거 답변(또는 무답).
외부 호출: ego-browser(검색), yt-dlp(메타·자막) via subprocess.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from urllib.parse import quote

sys.path.insert(0, "/Users/tedkim/Documents/mirror-sea-project/yt-grounded-qa")
from pipeline import (  # noqa: E402
    Candidate, PASS, _recency_score, extract_keywords, score, structure,
)
from research import cues  # noqa: E402
from ontology import build as build_onto, find_terms, validate  # noqa: E402

SUB_DIR = "/tmp/ytqa"
SPACE = "yt-qa-cycle"

# 채널명에 이 문자열이 있으면 판매자로 보고 이해충돌 적용(코드 공개 목록)
VENDOR_HINTS = ["뮤지쿠스", "MUSICUS", "안주인", "ANJUIN", "WALL", "MONO",
                "쉿", "컨돌", "라흐마니노프", "SYSTEM"]


def ego_search(query: str, n: int = 6) -> list[dict]:
    url = "https://www.youtube.com/results?search_query=" + quote(query)
    js = (
        'const task = await taskSpace("' + SPACE + '");'
        'const page = task.page("p1");'
        'await page.goto("' + url + '", { timeout: 60000 });'
        'await page.waitForSelector("a#video-title", { timeout: 30000 });'
        "const rows = await page.evaluate(() => {"
        "const out = []; const seen = new Set();"
        "for (const a of document.querySelectorAll(\"a#video-title\")) {"
        "const m = (a.href || \"\").match(/[?&]v=([\\w-]{11})/);"
        "if (!m || seen.has(m[1])) continue;"
        "seen.add(m[1]);"
        "out.push({ id: m[1], title: (a.title || \"\").trim().slice(0, 80) });"
        "if (out.length >= " + str(n) + ") break;"
        "} return out;"
        "});"
        'console.log("YTQA_IDS_BEGIN");'
        "console.log(JSON.stringify(rows));"
    )
    r = subprocess.run(["ego-browser", "nodejs", "-e", js], capture_output=True,
                       text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError("ego-browser 실패: " + (r.stdout + r.stderr)[-500:])
    # 주의: ego-browser nodejs의 console.log는 stderr로 나온다
    out = r.stdout + r.stderr
    if "YTQA_IDS_BEGIN" not in out:
        raise RuntimeError("검색 결과 파싱 실패: " + out[-500:])
    try:
        payload = out.split("YTQA_IDS_BEGIN")[1].strip().splitlines()[0]
        return json.loads(payload)
    except (IndexError, ValueError):
        raise RuntimeError("검색 결과 파싱 실패: " + out[-500:])


def yt_meta(ids: list[str]) -> list[dict]:
    urls = [f"https://www.youtube.com/watch?v={i}" for i in ids]
    r = subprocess.run(["yt-dlp", "--skip-download", "--dump-json", *urls],
                       capture_output=True, text=True, timeout=240)
    out = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            out.append(json.loads(line))
    return out


def yt_subs(video_id: str) -> bool:
    r = subprocess.run(
        ["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
         "--sub-langs", "ko", "--sub-format", "vtt",
         "-o", f"{SUB_DIR}/%(id)s.%(ext)s",
         f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True, timeout=240)
    import os
    return os.path.exists(f"{SUB_DIR}/{video_id}.ko.vtt")


def best_cue(cs: list, keywords: list[str]) -> tuple[int, str] | None:
    scored = []
    for s, t in cs:
        n = sum(t.count(k) for k in keywords if len(k) >= 2)
        if n > 0:
            scored.append((n, -s, s, t))
    if not scored:
        return None
    scored.sort(reverse=True)
    _, _, s, t = scored[0]
    return s, (t[:150] if len(t) > 150 else t)


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "방음부스 층간소음 효과 있어?"
    print(f"질문: {question}")
    s = structure(question)
    kws = extract_keywords(s)
    print(f"키워드: {kws}")
    rows = ego_search(question)
    print(f"검색: {len(rows)}건")
    metas = {m["id"]: m for m in yt_meta([r["id"] for r in rows])}
    cands: list[dict] = []
    for r in rows:
        m = metas.get(r["id"])
        if not m:
            continue
        subs = list((m.get("subtitles") or {}).keys())
        auto = list((m.get("automatic_captions") or {}).keys())
        kind = "manual" if "ko" in subs else ("auto" if "ko" in auto else "none")
        if kind == "none" or not yt_subs(r["id"]):
            print(f"제외(자막 없음): {r['id']} {r['title'][:40]}")
            continue
        ch = m.get("channel", "?")
        conflict = any(h in ch.upper() for h in VENDOR_HINTS)
        if conflict:
            print(f"이해충돌 표시: {ch}")
        cs = cues(f"{SUB_DIR}/{r['id']}.ko.vtt")
        hit = best_cue(cs, kws)
        if not hit:
            print(f"제외(주장 없음): {r['id']}")
            continue
        t0, claim = hit
        idx = next(i for i, (a, _) in enumerate(cs) if a == t0)
        ctx = " ".join(t for _, t in cs[max(0, idx - 2):idx + 3])
        has_num = bool(re.search(r"\d", claim + ctx) and
                       re.search(r"만원|천원|원\b|dB|데시벨|평|미터|%|배", claim + ctx))
        cands.append({"vid": r["id"], "channel": ch,
                      "type": "official" if conflict else "general",
                      "date": m.get("upload_date", "")[:4] + "-" +
                      m.get("upload_date", "")[4:6] + "-" +
                      m.get("upload_date", "")[6:8]
                      if m.get("upload_date") else None,
                      "subs": kind, "claim": claim, "t": [t0, t0 + 30],
                      "has_num": has_num, "conflict": conflict,
                      "ctx": ctx})
    fams = [c for c in cands if find_terms(c["claim"])]
    cross = {c["vid"] for c in fams} if len({c["vid"] for c in fams}) >= 2 else set()
    print(f"교차언급: {sorted(cross) or '없음'}")
    scored = []
    for c in cands:
        cd = Candidate(c["vid"], c["channel"], c["type"], c["date"], c["subs"],
                       True, c["has_num"], c["claim"], tuple(c["t"]),
                       conflict=c["conflict"])
        sc, reason = score(cd, c["vid"] in cross)
        ok = sc > PASS
        print(f"{c['vid']}={sc}점 {'통과' if ok else '탈락(' + (reason or '미달') + ')'}")
        if ok:
            scored.append(c)
    if not scored:
        print("무답: 신뢰 가능한 유튜브 근거를 찾지 못했습니다")
        return
    onto = build_onto([{"claim": c["claim"], "video_id": c["vid"], "t": c["t"],
                        "channel": c["channel"], "date": c["date"],
                        "context": c["ctx"]} for c in scored])
    validate(onto)
    print(f"온톨로지: 개념 {len(onto['concepts'])}개, 관계 {len(onto['relations'])}개")
    for r in onto["relations"]:
        e = r["evidence"]
        print(f"- {r['from']} --{r['type']}--> {r['to']} [{e['videoId']}@{e['t'][0]}s]")
    print("답변:")
    for c in scored:
        print(f"- {c['claim']} [{c['vid']}@{c['t'][0]}s, {c['channel']}, {c['date']}]")


if __name__ == "__main__":
    main()
