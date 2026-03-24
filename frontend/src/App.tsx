import { useQuery } from '@tanstack/react-query'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { QueryPanel } from '@/components/query/QueryPanel'
import { GraphView } from '@/components/graph/GraphView'
import { TableView } from '@/components/table/TableView'
import { ChartView } from '@/components/chart/ChartView'
import { DetailPanel } from '@/components/detail/DetailPanel'
import { ChatPanel } from '@/components/chat/ChatPanel'
import { useWorkspaceStore } from '@/store/useWorkspaceStore'
import { checkHealth } from '@/lib/api/client'

// ─── 헬스 상태 뱃지 ───────────────────────────────────────────────────────────

function HealthBadge() {
  const { data, isError } = useQuery({
    queryKey: ['health'],
    queryFn: checkHealth,
    refetchInterval: 30000,
    retry: false,
  })

  if (isError) return <Badge variant="destructive" className="text-xs">백엔드 오프라인</Badge>
  if (!data) return <Badge variant="secondary" className="text-xs">연결 중...</Badge>

  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${data.neo4j_connected ? 'bg-green-500' : 'bg-yellow-500'}`} />
      <span className="text-xs text-muted-foreground">
        {data.neo4j_connected ? 'Neo4j 연결됨' : 'Neo4j 미연결'}
      </span>
    </div>
  )
}

// ─── 탭 헤더 ─────────────────────────────────────────────────────────────────

const HEADER_H = 40    // px
const DETAIL_H = 280   // px
const TAB_HDR_H = 38   // px (탭 버튼 헤더)

// ─── App 컴포넌트 ─────────────────────────────────────────────────────────────

export default function App() {
  const { activeTab, setActiveTab, queryResponse, tableRows } = useWorkspaceStore()

  return (
    // 전체 화면 컨테이너
    <div style={{ position: 'fixed', inset: 0, display: 'flex', flexDirection: 'column' }}
         className="bg-background text-foreground">

      {/* ── 헤더 (40px 고정) ── */}
      <header
        style={{ height: HEADER_H, flexShrink: 0 }}
        className="flex items-center justify-between px-4 border-b border-border bg-card"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold tracking-tight">RCP Cypher</span>
          <Separator orientation="vertical" className="h-4" />
          <span className="text-xs text-muted-foreground">Wafer · Recipe · Metrology 분석 워크스페이스</span>
        </div>
        <HealthBadge />
      </header>

      {/* ── 메인 영역 (나머지 전체 높이, relative로 absolute children 앵커) ── */}
      <div style={{ position: 'relative', flex: 1, overflow: 'hidden' }}>

        {/* 좌측 62% */}
        <div
          style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '62%', display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--border)' }}
          className="bg-background"
        >
          {/* 쿼리 패널 */}
          <QueryPanel />

          {/* 탭 헤더 + 콘텐츠 (flex-1 → 사이 공간 전부) */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>

            {/* 탭 버튼 줄 (38px 고정) */}
            <div
              style={{ height: TAB_HDR_H, flexShrink: 0 }}
              className="flex items-center gap-0.5 px-3 border-b border-border bg-card"
            >
              {([
                { value: 'graph', label: '그래프', badge: queryResponse ? `${queryResponse.result.nodes.length}N·${queryResponse.result.edges.length}E` : null },
                { value: 'table', label: '테이블', badge: tableRows.length > 0 ? String(tableRows.length) : null },
                { value: 'chart',  label: '차트',   badge: null },
              ] as const).map(({ value, label, badge }) => (
                <button
                  key={value}
                  onClick={() => setActiveTab(value)}
                  className={`text-xs px-3 h-6 rounded transition-colors ${
                    activeTab === value
                      ? 'bg-background text-foreground font-medium shadow-sm border border-border'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {label}
                  {badge && <span className="ml-1 opacity-60">{badge}</span>}
                </button>
              ))}
            </div>

            {/* 탭 콘텐츠 영역 — absolute로 나머지 공간을 완전히 채움 */}
            <div style={{ position: 'absolute', top: TAB_HDR_H, left: 0, right: 0, bottom: DETAIL_H, overflow: 'hidden' }}>
              {activeTab === 'graph' && <GraphView />}
              {activeTab === 'table' && <TableView />}
              {activeTab === 'chart' && <ChartView />}
            </div>

            {/* 하단 상세 패널 (280px 고정) */}
            <div
              style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: DETAIL_H }}
              className="border-t border-border"
            >
              <div className="px-3 py-1.5 border-b border-border bg-muted/30">
                <span className="text-xs font-medium">상세 정보</span>
              </div>
              <div style={{ height: DETAIL_H - 30, overflow: 'auto' }}>
                <DetailPanel />
              </div>
            </div>
          </div>
        </div>

        {/* 우측 38% — 채팅 */}
        <div
          style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: '38%' }}
          className="bg-background"
        >
          <ChatPanel />
        </div>
      </div>
    </div>
  )
}
