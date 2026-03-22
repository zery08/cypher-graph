import { create } from 'zustand'
import type { GraphNode, GraphEdge, GraphResult, QueryResponse } from '@/lib/schemas'

// ─── 선택 상태 타입 ───────────────────────────────────────────────────────────

export type SelectionTarget =
  | { kind: 'node'; node: GraphNode }
  | { kind: 'edge'; edge: GraphEdge }
  | { kind: 'row'; rowIndex: number; rowData: Record<string, unknown> }
  | { kind: 'point'; seriesId: string; pointIndex: number }
  | null

export type ActiveTab = 'graph' | 'table' | 'chart'

// ─── 스토어 상태 타입 ─────────────────────────────────────────────────────────

interface WorkspaceState {
  // 탭 상태
  activeTab: ActiveTab
  setActiveTab: (tab: ActiveTab) => void

  // 쿼리 패널
  currentQuery: string
  setCurrentQuery: (query: string) => void
  isQueryPanelCollapsed: boolean
  toggleQueryPanel: () => void
  isQueryRunning: boolean
  setQueryRunning: (running: boolean) => void

  // 쿼리 결과
  queryResponse: QueryResponse | null
  setQueryResponse: (response: QueryResponse | null) => void

  // 그래프 결과
  graphResult: GraphResult | null
  setGraphResult: (result: GraphResult | null) => void

  // 테이블 결과
  tableRows: Record<string, unknown>[]
  setTableRows: (rows: Record<string, unknown>[]) => void

  // 차트 설정
  chartConfig: Record<string, unknown> | null
  setChartConfig: (config: Record<string, unknown> | null) => void

  // 공유 선택 상태
  selection: SelectionTarget
  setSelection: (target: SelectionTarget) => void
  clearSelection: () => void

  // 마지막 tool 실행 요약
  lastToolSummary: string | null
  setLastToolSummary: (summary: string | null) => void

  // 필터
  activeFilters: Record<string, unknown>
  setActiveFilters: (filters: Record<string, unknown>) => void

  // 포커스 노드 ID (그래프 탭 포커스용)
  focusNodeId: string | null
  setFocusNodeId: (id: string | null) => void
}

// ─── 스토어 생성 ──────────────────────────────────────────────────────────────

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  // 탭 상태
  activeTab: 'graph',
  setActiveTab: (tab) => set({ activeTab: tab }),

  // 쿼리 패널
  currentQuery: '',
  setCurrentQuery: (query) => set({ currentQuery: query }),
  isQueryPanelCollapsed: false,
  toggleQueryPanel: () =>
    set((state) => ({ isQueryPanelCollapsed: !state.isQueryPanelCollapsed })),
  isQueryRunning: false,
  setQueryRunning: (running) => set({ isQueryRunning: running }),

  // 쿼리 결과
  queryResponse: null,
  setQueryResponse: (response) => set({ queryResponse: response }),

  // 그래프 결과
  graphResult: null,
  setGraphResult: (result) => set({ graphResult: result }),

  // 테이블 결과
  tableRows: [],
  setTableRows: (rows) => set({ tableRows: rows }),

  // 차트 설정
  chartConfig: null,
  setChartConfig: (config) => set({ chartConfig: config }),

  // 공유 선택 상태
  selection: null,
  setSelection: (target) => set({ selection: target }),
  clearSelection: () => set({ selection: null }),

  // 마지막 tool 요약
  lastToolSummary: null,
  setLastToolSummary: (summary) => set({ lastToolSummary: summary }),

  // 필터
  activeFilters: {},
  setActiveFilters: (filters) => set({ activeFilters: filters }),

  // 포커스 노드
  focusNodeId: null,
  setFocusNodeId: (id) => set({ focusNodeId: id }),
}))
