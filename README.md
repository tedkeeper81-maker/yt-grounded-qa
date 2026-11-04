# yt-grounded-qa

질문 → 구조화 → 키워드 → 유튜브 검색 → 자막 → 신뢰도 점수(v1.3) → 온톨로지 → 근거 답변. 미달이면 무답.

Question → structure → keywords → YouTube search → subtitles → trust rubric (v1.3) → ontology → cited answer. Below 60: no answer.

## 실행 / Run

```sh
python3 pipeline.py    # 모의 3건 / mock cases
python3 research.py    # 실자막 판정 / real-subtitle verdict
python3 ontology.py    # 온톨로지 빌드 / ontology build
python3 cycle.py "질문" # 한 사이클 / full cycle (needs ego-browser + yt-dlp)
```

- 수집: ego-browser(검색) + yt-dlp(자막). API 키 불필요.
- Collection: ego-browser (search) + yt-dlp (subtitles). No API key.
- 근거 없는 문장은 답에 포함 금지. 판매자 채널은 -15점.
- No claim without evidence. Seller channels get -15.
