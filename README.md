# RCP Cypher

Neo4j에 저장된 **wafer / recipe / metrology 데이터**를 그래프, 테이블, 차트, AI 채팅으로 함께 탐색하는 웹 애플리케이션입니다.

## 주요 기능

- **그래프 뷰** — Cytoscape.js 기반 노드/엣지 시각화, 노드 클릭 시 연결 관계 강조
- **테이블 뷰** — 정렬/필터/행 선택 지원 (TanStack Table)
- **차트 뷰** — step 추이, 파라미터 분포 등 분석용 차트 (Recharts)
- **AI 채팅** — LLM이 자연어 질문을 Cypher로 변환해 Neo4j를 조회하고 결과를 스트리밍으로 답변
- **Electron 앱** — 데스크톱 앱으로도 실행 가능 (화면 캡처 방지 포함)

## 기술 스택

| 영역 | 기술 |
|------|------|
| 프론트엔드 | React 19 + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| 상태 관리 | Zustand + TanStack Query |
| 백엔드 | FastAPI + Python 3.11+ (uv) |
| LLM 오케스트레이션 | LangChain + LangGraph (`create_react_agent`) |
| 데이터베이스 | Neo4j 5 (Docker) |
| LLM API | OpenRouter (`minimax/minimax-m2.5:free` 기본값) |

---

## 실행 방법

### 사전 요구사항

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (`pip install uv` 또는 `brew install uv`)
- Node.js 18+
- Docker & Docker Compose
- OpenRouter API 키 ([openrouter.ai](https://openrouter.ai) 무료 가입)

---

### 1. Neo4j 실행

```bash
docker compose up -d
```

Neo4j 브라우저: http://localhost:7474
기본 계정: `neo4j` / `wafergraph123`

---

### 2. 백엔드 실행

```bash
cd backend
```

환경변수 파일 생성:

```bash
cat > .env << 'EOF'
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=wafergraph123

OPENAI_API_KEY=sk-or-v1-여기에_openrouter_키_입력
OPENAI_BASE_URL=https://openrouter.ai/api/v1

COORDINATOR_MODEL=minimax/minimax-m2.5:free
CYPHER_MODEL=minimax/minimax-m2.5:free
ANSWER_MODEL=minimax/minimax-m2.5:free

MAX_QUERY_RESULTS=100
EOF
```

의존성 설치 및 서버 시작:

```bash
uv sync
uv run fastapi dev app/main.py
```

백엔드 API: http://localhost:8000
API 문서: http://localhost:8000/docs

---

### 3. 프론트엔드 실행 (웹)

```bash
cd frontend
npm install
npm run dev
```

앱: http://localhost:5173

---

### 4. Electron 데스크톱 앱 실행 (선택)

```bash
cd frontend
npm install
npm run dev:electron
```

> Electron 앱은 `setContentProtection(true)`로 OS 수준 화면 캡처가 차단됩니다.

---

## 환경변수 전체 목록

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j 연결 주소 |
| `NEO4J_USERNAME` | `neo4j` | Neo4j 사용자명 |
| `NEO4J_PASSWORD` | `password` | Neo4j 비밀번호 |
| `OPENAI_API_KEY` | — | OpenRouter API 키 |
| `OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` | LLM API 엔드포인트 |
| `COORDINATOR_MODEL` | `minimax/minimax-m2.5:free` | 코디네이터 LLM 모델 |
| `CYPHER_MODEL` | `minimax/minimax-m2.5:free` | Cypher 생성 LLM 모델 |
| `ANSWER_MODEL` | `minimax/minimax-m2.5:free` | 답변 정리 LLM 모델 |
| `MAX_QUERY_RESULTS` | `100` | 쿼리 결과 최대 행 수 |
| `DATABASE_URL` | — | PostgreSQL URL (대화 기록 저장, 선택) |

---

## 프로젝트 구조

```
rcp-cypher/
├── backend/                  # FastAPI 백엔드
│   ├── app/
│   │   ├── api/routes/       # 엔드포인트 (chat, graph, schema, auth)
│   │   ├── llm/              # LLM 오케스트레이션
│   │   │   ├── coordinator.py    # 에이전트 + 스트리밍
│   │   │   ├── models.py         # LLM 객체 팩토리
│   │   │   ├── prompts.py        # 프롬프트 템플릿
│   │   │   └── tools/            # 개별 tool 구현
│   │   ├── services/         # Neo4j, query guard
│   │   └── schemas/          # Pydantic 모델
│   └── pyproject.toml
├── frontend/                 # React + Electron 프론트엔드
│   ├── src/
│   │   ├── components/       # UI 컴포넌트 (graph, table, chart, chat)
│   │   ├── store/            # Zustand 상태 관리
│   │   └── lib/              # API 클라이언트, 스키마
│   └── electron/             # Electron 메인 프로세스
├── neo4j/                    # Neo4j seed 데이터
└── docker-compose.yml
```

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/chat` | 채팅 (동기) |
| `POST` | `/api/chat/stream` | 채팅 (SSE 스트리밍) |
| `POST` | `/api/graph/query` | Cypher 직접 실행 |
| `GET` | `/api/graph/schema` | Neo4j 스키마 조회 |
| `GET` | `/api/health` | 헬스체크 |
