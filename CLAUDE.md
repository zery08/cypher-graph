# CLAUDE.md

이 저장소는 **Neo4j에 저장된 wafer별 recipe data / 계측 data를 그래프, 테이블, 차트, 채팅으로 함께 탐색하는 웹 앱**이다.

이 문서는 Claude가 이 저장소에서 코드를 생성하거나 수정할 때 반드시 따라야 하는 **구현 계약서**다.

---

## 1. 기본 원칙

### 언어 규칙
- **이 저장소에서 생성하는 설명, 주석, 문서, 예시 응답은 모두 한글로 작성한다.**
- **Claude의 대답도 항상 한글로 작성한다.**
- UI 라벨은 한글 우선으로 작성하되, 데이터베이스/도메인 용어(`wafer`, `recipe`, `metrology`, `lot`, `step`, `chamber`)는 필요 시 영문을 병기할 수 있다.

### 제품 성격
- 이 앱은 일반 소비자용 챗 UI가 아니라 **반도체 공정/계측 데이터 탐색용 분석 워크스페이스**다.
- 사용자는 단순 채팅보다 **데이터 확인, 관계 추적, 패턴 비교, 쿼리 검증**을 더 중요하게 여긴다.
- 따라서 시각적으로는 화려함보다 **밀도, 정확성, 재현성, 선택 상태의 일관성**이 중요하다.

---

## 2. 기술 스택

### 프론트엔드
프론트엔드는 다음 기준을 따른다.

- **React**
- **TypeScript**
- **Vite**
- **Tailwind CSS**
- **shadcn/ui**
- **Zustand**: 로컬 UI 상태 / 선택 상태 / 패널 상태
- **TanStack Query**: 서버 상태
- **TanStack Table**: 테이블 뷰
- **Cytoscape.js**: 그래프 시각화
- **Recharts**: 차트 시각화
- **Zod**: API 응답 검증

### 백엔드
백엔드는 다음 기준을 따른다.

- **FastAPI**
- **uv**로 프로젝트/의존성 관리
- Python 3.11+
- LangChain 기반 오케스트레이션
- Neo4j Python Driver + `langchain_neo4j`

`uv`는 FastAPI 프로젝트 관리에 사용할 수 있도록 공식 가이드가 제공된다. citeturn895270search2turn895270search11

### 모델
기본 모델은 다음을 사용한다.

- **`minimax/minimax-m2.5:free`**

OpenRouter에는 `minimax/minimax-m2.5:free` 모델 페이지가 존재하며, 무료 변형으로 제공된다. citeturn262413search0turn262413search6

---

## 3. 반드시 지켜야 할 아키텍처

앱은 아래의 **3계층 구조**로 만든다.

1. **Frontend (React)**
   - 화면 렌더링
   - 탭 전환
   - 선택 상태 공유
   - 채팅 입력/출력
   - 그래프/테이블/차트 표시

2. **Backend API (FastAPI)**
   - 프론트의 요청 수신
   - coordinator LLM 실행
   - tool 호출
   - Neo4j 질의
   - 응답 정규화

3. **Data/LLM Layer**
   - Neo4jGraph
   - GraphCypherQAChain
   - coordinator LLM
   - cypher 생성 전용 LLM
   - 필요 시 answer 정리용 LLM

### 중요한 제약
- **브라우저에서 Neo4j에 직접 연결하지 않는다.**
- 모든 DB 접근은 FastAPI 백엔드를 통해서만 수행한다.
- 프론트엔드는 raw Cypher를 직접 실행하지 않고, 항상 백엔드 API를 통해 실행한다.
- LLM이 만든 Cypher는 그대로 실행하지 말고, **허용 범위 검증 / 읽기 전용 제한 / 결과 행 수 제한**을 둔다.

---

## 4. LLM 구조

이 프로젝트의 핵심은 **coordinator가 tool을 호출하는 구조**다.

### 필수 역할 분리
최소한 아래 역할을 분리 가능하게 구현한다.

1. **Coordinator LLM**
   - 사용자 질문을 해석
   - 어떤 tool을 호출할지 결정
   - 필요한 경우 여러 tool 결과를 종합
   - 최종 답변을 생성

2. **Cypher Tool LLM**
   - 자연어를 Cypher로 변환
   - Neo4j schema를 기반으로 안전한 조회 쿼리 생성
   - 이 모델은 coordinator와 **별도로 지정 가능해야 한다**

3. **Answer/Formatter LLM (선택)**
   - tool 결과를 사람이 읽기 쉬운 설명으로 정리
   - 초기에는 coordinator와 동일 모델을 재사용해도 된다.

### 기본 설정
- 기본적으로 coordinator LLM = `minimax/minimax-m2.5:free`
- 기본적으로 cypher LLM = `minimax/minimax-m2.5:free`
- 단, 환경변수 또는 설정 파일로 **cypher LLM만 별도로 교체 가능**해야 한다.

예시:
- `COORDINATOR_MODEL=minimax/minimax-m2.5:free`
- `CYPHER_MODEL=minimax/minimax-m2.5:free`
- 추후 `CYPHER_MODEL`만 다른 모델로 바꿀 수 있게 한다.

---

## 5. Neo4j / LangChain 구현 규칙

반드시 아래 import 기준을 사용한다.

```python
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
```

`langchain_neo4j` 패키지에서 `Neo4jGraph`, `GraphCypherQAChain`를 사용하는 방식은 Neo4j/LangChain 자료에서 안내되고 있다. citeturn895270search24turn895270search0turn895270search12

### 그래프 연결
백엔드에서 다음 역할의 객체를 만든다.

- `Neo4jGraph`: schema 조회 + graph query 실행
- `GraphCypherQAChain`: 자연어 -> Cypher -> 결과 -> 답변 흐름 처리

### 구현 원칙
- `Neo4jGraph`는 앱 시작 시 1회 초기화하거나, lazy singleton 형태로 관리한다.
- schema refresh 비용이 크면 매 요청마다 새로 만들지 않는다.
- `GraphCypherQAChain`는 다음 요구사항을 충족해야 한다.
  - `cypher_llm`을 별도로 받을 수 있어야 함
  - `qa_llm` 또는 응답 정리용 LLM을 분리 가능해야 함
  - dangerous request 방지용 설정을 둬야 함
  - read-only 쿼리만 허용하는 래퍼를 추가해야 함

### 금지 사항
- `CREATE`, `MERGE`, `DELETE`, `SET`, `DROP`, `CALL dbms`, `CALL apoc.periodic` 등 변경/관리성 쿼리는 기본적으로 금지
- 결과 row 수 제한 없이 대량 조회 금지
- 사용자가 요청했다고 해도 DB 전체 dump 형태 응답 금지

---

## 6. 권장 백엔드 구조

```text
backend/
  pyproject.toml
  uv.lock
  app/
    main.py
    core/
      config.py
      logging.py
    api/
      routes/
        health.py
        chat.py
        graph.py
        schema.py
    llm/
      models.py
      prompts.py
      coordinator.py
      tools/
        graph_cypher_tool.py
        graph_schema_tool.py
        table_query_tool.py
        chart_tool.py
    services/
      neo4j_service.py
      chat_service.py
      query_guard.py
      result_formatter.py
    schemas/
      chat.py
      graph.py
      common.py
```

### 백엔드 책임 분리
- `api/routes`: FastAPI 엔드포인트만 담당
- `llm/coordinator.py`: tool 선택 로직 담당
- `llm/tools/*`: 실제 tool 단위 구현
- `services/neo4j_service.py`: graph 연결 및 query 실행 담당
- `services/query_guard.py`: 허용 쿼리 검사 담당
- `schemas/*`: 입출력 모델 정의

---

## 7. 권장 프론트엔드 구조

```text
frontend/
  package.json
  src/
    main.tsx
    app/
      App.tsx
      providers.tsx
    components/
      layout/
      query/
      graph/
      table/
      chart/
      detail/
      chat/
    features/
      workspace/
      conversation/
    lib/
      api/
      schemas/
      utils/
    store/
      useWorkspaceStore.ts
      useChatStore.ts
    types/
```

### 프론트엔드 원칙
- 페이지 단일 컴포넌트에 모든 로직을 몰아넣지 않는다.
- 그래프/테이블/차트는 각각 독립 컴포넌트로 분리한다.
- 공통 선택 상태는 store에서 관리한다.
- 서버 상태는 React Query로 관리한다.
- API 응답은 Zod로 파싱한다.

---

## 8. 화면 레이아웃 계약

전체 화면은 **좌측 분석 영역 + 우측 채팅 영역**의 2열 구조다.

- 좌측: 약 62%
- 우측: 약 38%

### 좌측 상단
**그래프 쿼리 패널**
- 접기/펼치기 가능
- Cypher 입력창
- preset query 버튼
- 실행 버튼
- 최근 실행 쿼리 요약
- 현재 filter 표시

### 좌측 중단
**메인 결과 패널**
탭 전환 가능:
- 그래프 탭
- 테이블 탭
- 차트 탭

#### 그래프 탭
- 노드/엣지 시각화
- 줌 / 팬 / fit / focus
- 노드 선택 가능
- 엣지 선택 가능
- node type별 시각 구분

#### 테이블 탭
- 정렬
- 컬럼 필터
- sticky header
- row selection
- pagination 또는 virtualization

#### 차트 탭
- line
- scatter
- histogram 유사 분포 차트
- box summary 카드 또는 box plot 유사 요약 뷰

### 좌측 하단
**상세 정보 패널**
- 현재 선택된 node / edge / row / point의 자세한 정보
- 관련 recipe / metrology / wafer / lot 정보를 구조적으로 표시
- raw properties + 사람이 읽는 설명을 함께 제공

### 우측
**LLM 채팅 패널**
- 채팅 헤더
- 현재 컨텍스트 배너
- 메시지 리스트
- assistant action chip
- 입력창

---

## 9. 공통 상태 모델

반드시 공유 탐색 상태를 둔다.

최소 필수 상태:
- 현재 활성 탭
- 현재 Cypher query
- query panel 접힘 여부
- 활성 filter
- 그래프 결과
- 테이블 결과
- 차트 결과
- 현재 selection
- chat context snapshot
- query 실행 상태
- 마지막 tool 실행 결과 요약

### selection 규칙
다음 이벤트는 모두 같은 shared selection을 갱신해야 한다.
- 그래프에서 node 클릭
- 그래프에서 edge 클릭
- 테이블 row 선택
- 차트 point 선택
- 채팅 action 클릭

즉, 어느 패널에서 선택해도 다른 패널이 같은 대상을 인지해야 한다.

---

## 10. 백엔드 API 계약

최소한 아래 엔드포인트를 만든다.

### 1) `POST /api/chat`
역할:
- 사용자 메시지 수신
- coordinator 실행
- tool 호출
- 최종 답변 + UI action 반환

응답 예시:
```json
{
  "message": "선택한 wafer의 recipe step과 계측 결과를 찾았습니다.",
  "actions": [
    {"type": "open_tab", "tab": "graph"},
    {"type": "focus_node", "nodeId": "wafer-001"},
    {"type": "apply_query", "query": "MATCH ... RETURN ... LIMIT 50"}
  ],
  "tool_results": {
    "graph": {...},
    "table": {...},
    "chart": {...}
  }
}
```

### 2) `POST /api/graph/query`
역할:
- 사용자가 직접 입력한 Cypher 실행
- 읽기 전용 검증 후 결과 반환

### 3) `GET /api/graph/schema`
역할:
- node label / relationship type / property 요약 제공

### 4) `POST /api/chart/build`
역할:
- 테이블 결과를 차트용 구조로 변환
- 필요 시 서버에서 aggregation 수행

### 5) `GET /api/health`
역할:
- 서비스 상태 점검

---

## 11. Tool 설계 규칙

coordinator는 아래 tool들을 호출할 수 있어야 한다.

### 필수 tool
1. `graph_schema_tool`
   - 현재 Neo4j schema 요약 조회
   - Cypher 생성 전에 schema grounding 용도로 사용

2. `graph_cypher_qa_tool`
   - 자연어 질문을 받아 Cypher 생성/실행/정리
   - 내부적으로 `GraphCypherQAChain` 사용

3. `graph_query_tool`
   - 프론트에서 직접 작성한 Cypher를 실행
   - query guard 통과 시에만 실행

4. `table_summary_tool`
   - 반환된 표 형식 데이터를 요약

5. `chart_recommendation_tool`
   - 어떤 차트가 적절한지 추천
   - 예: step trend, parameter distribution, wafer comparison

### 중요한 구현 포인트
- coordinator는 **직접 Cypher를 생성하지 않아도 된다.**
- Cypher 생성이 필요하면 `graph_cypher_qa_tool` 또는 별도 cypher tool LLM을 호출한다.
- 이 구조는 “coordinator가 tool을 호출하는 에이전트처럼 동작”해야 한다.

---

## 12. LLM 객체 생성 규칙

LLM 객체 생성은 한 군데에서 관리한다.

예를 들어 `backend/app/llm/models.py` 같은 파일에서 다음을 제공한다.

- `get_coordinator_llm()`
- `get_cypher_llm()`
- `get_answer_llm()`

### 요구사항
- 세 함수는 각각 **환경변수 기반으로 다른 모델을 선택 가능**해야 한다.
- 기본값은 `minimax/minimax-m2.5:free`
- OpenAI 호환 API 레이어를 사용할 경우 base URL과 API key를 환경변수로 받는다.

예시 환경변수:
```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
COORDINATOR_MODEL=minimax/minimax-m2.5:free
CYPHER_MODEL=minimax/minimax-m2.5:free
ANSWER_MODEL=minimax/minimax-m2.5:free
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
```

---

## 13. GraphCypherQAChain 사용 방식

가능하면 아래 방향으로 구현한다.

```python
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain

graph = Neo4jGraph(
    url=settings.NEO4J_URI,
    username=settings.NEO4J_USERNAME,
    password=settings.NEO4J_PASSWORD,
)

cypher_chain = GraphCypherQAChain.from_llm(
    cypher_llm=get_cypher_llm(),
    qa_llm=get_answer_llm(),
    graph=graph,
    verbose=True,
    allow_dangerous_requests=False,
)
```

### 추가 요구사항
- chain 실행 전 질문을 schema-aware prompt로 보강한다.
- chain이 생성한 Cypher를 로깅한다.
- 실제 실행 전 `query_guard`로 2차 검증한다.
- 응답에는 아래를 분리해서 담는다.
  - 생성된 Cypher
  - raw query result
  - 사용자 친화 설명
  - graph/table/chart 변환 결과

Neo4j 측 자료에서는 `GraphCypherQAChain`가 Text2Cypher 워크플로우의 추상화로 소개되며, 관계 방향 교정 등 검증/보정 레이어를 제공한다고 설명한다. citeturn895270search12turn895270search24

---

## 14. FastAPI 구현 규칙

### 실행/개발
백엔드는 `uv` 기준으로 구성한다.

예시:
```bash
uv init backend
uv add fastapi uvicorn langchain langchain-openai langchain-neo4j neo4j pydantic pydantic-settings
uv run fastapi dev app/main.py
```

### FastAPI 원칙
- route는 얇게 유지
- 비즈니스 로직은 service로 이동
- request/response는 Pydantic 모델 사용
- 예외는 공통 handler에서 변환
- 스트리밍 채팅이 필요하면 SSE 또는 chunked response 구조 고려

---

## 15. 프론트엔드 구현 규칙

### 시각 디자인
- 데스크톱 우선
- 최소 너비 1440px 기준
- 패널형 레이아웃
- 기술 분석 도구처럼 보여야 함
- consumer chat 앱처럼 보이면 안 됨

### Query 패널
- 접힘/펼침 가능
- 접힌 상태에서도 현재 query 요약이 보여야 함
- 실행 중 상태 표시 필요

### Graph 탭
- graph가 비었을 때 empty state 필요
- selection/focus/fitting 동작 필수
- node/edge에 따라 detail panel이 다른 내용을 보여야 함

### Table 탭
- 대량 row 대응 고려
- 정렬/필터/행 선택 제공
- 컬럼 수가 많아도 usable 해야 함

### Chart 탭
- 단순 예쁜 차트보다 **분석 가능한 차트** 우선
- wafer 비교 / step trend / parameter distribution 시나리오를 먼저 고려

### Chat 패널
- assistant message는 단순 텍스트 외에 action chip을 가질 수 있다.
- 예: “그래프 보기”, “이 wafer 선택”, “이 쿼리 적용”, “차트 탭으로 전환”

---

## 16. 프론트 액션 계약

assistant 응답에는 아래 action type을 포함할 수 있다.

- `apply_query`
- `open_tab`
- `focus_node`
- `select_row`
- `set_filters`
- `create_chart`
- `highlight_series`

### 중요한 규칙
- action은 타입 안전하게 파싱한다.
- action은 프론트 store를 업데이트하는 방식으로만 반영한다.
- action을 통해 임의 코드 실행 금지
- action을 통해 무검증 Cypher 자동 실행 금지

즉:
- `apply_query`는 편집기에 query를 채워 넣을 수는 있지만,
- **자동 실행은 별도 사용자 액션 또는 명시적 안전 조건이 있을 때만 허용**한다.

---

## 17. 도메인 특화 UX 규칙

이 앱은 wafer / recipe / metrology 데이터용이므로 아래를 우선 지원한다.

### 주요 탐색 흐름
1. 특정 wafer 선택
2. 관련 recipe step 확인
3. 관련 metrology parameter 확인
4. step별 추이 확인
5. wafer 간 비교
6. 특정 이상치가 어느 step / chamber / lot과 연관되는지 확인

### 따라서 UI는 다음 질문에 강해야 한다.
- 이 wafer는 어떤 recipe 흐름을 탔는가?
- 특정 계측값 이상치는 어떤 step과 연관되는가?
- 같은 lot의 다른 wafer와 비교하면 어떤 차이가 있는가?
- 어떤 parameter가 특정 조건에서 치우치는가?

---

## 18. 안전장치

### Query Guard
반드시 구현한다.

최소 기능:
- 금지 키워드 차단
- multi-statement 차단
- limit 강제
- explain/profile 남용 제한
- schema에 없는 label/property 사용 시 경고

### 응답 안전성
- 존재하지 않는 데이터는 추측하지 않는다.
- LLM 설명보다 실제 query result를 우선한다.
- 불확실할 때는 “데이터에서 확인된 범위만” 설명한다.

---

## 19. 구현 순서

반드시 아래 순서로 진행한다.

1. 백엔드/프론트엔드 모노레포 구조 생성
2. FastAPI + uv 기본 실행 환경 구성
3. React + Vite + Tailwind + shadcn/ui 셸 구성
4. 메인 레이아웃 구현
5. 좌측 query panel / tabs / detail panel 구현
6. 우측 chat panel 구현
7. Zustand 기반 shared selection store 구현
8. FastAPI health/chat/schema/query 엔드포인트 구현
9. Neo4jGraph 연결
10. GraphCypherQAChain 기반 graph_cypher_qa_tool 구현
11. coordinator -> tool 호출 흐름 구현
12. 프론트 action dispatcher 연결
13. mock 데이터 제거 후 실제 API 연결
14. empty/loading/error 상태 정리

---

## 20. 1차 완료 기준

아래가 되면 1차 milestone 완료다.

- 좌/우 2열 레이아웃이 동작한다.
- 좌상단 query panel이 접히고 펼쳐진다.
- 그래프/테이블/차트 탭이 모두 렌더링된다.
- shared selection이 detail panel에 반영된다.
- 우측 chat panel에서 메시지를 보내고 응답을 볼 수 있다.
- coordinator가 tool을 호출하는 구조가 있다.
- `GraphCypherQAChain` 기반 질의가 가능하다.
- cypher 생성용 LLM을 별도로 설정할 수 있다.
- Claude가 생성하는 설명/주석/문서는 모두 한글이다.

---

## 21. Claude에게 내리는 최종 작업 지시

이 파일을 읽은 뒤에는 아래 원칙으로 구현을 진행한다.

1. **항상 한글로 대답한다.**
2. 먼저 모노레포 구조를 만들고, backend와 frontend를 분리한다.
3. backend는 FastAPI + uv로 구성한다.
4. frontend는 React + TypeScript + Vite로 구성한다.
5. LLM 구조는 coordinator + tool 호출 방식으로 만든다.
6. Cypher 생성용 LLM은 coordinator와 별도로 설정 가능하게 만든다.
7. Neo4j 연동은 반드시 `Neo4jGraph`, `GraphCypherQAChain`를 사용한다.
8. 프론트에서 Neo4j로 직접 연결하지 않는다.
9. 모든 구현은 타입 안전성, 유지보수성, 한글 문서화를 우선한다.

이제 구현을 시작할 때는 먼저 **폴더 구조와 초기 파일들**부터 생성한다.
