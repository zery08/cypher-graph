import { useWorkspaceStore } from '@/store/useWorkspaceStore'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'

// ─── 속성 렌더러 ──────────────────────────────────────────────────────────────

function PropertyRow({ name, value }: { name: string; value: unknown }) {
  const str = value === null || value === undefined
    ? '—'
    : typeof value === 'object'
    ? JSON.stringify(value)
    : String(value)

  return (
    <div className="flex gap-2 py-1 border-b border-border/50 last:border-0">
      <span className="text-xs text-muted-foreground shrink-0 w-32 truncate">{name}</span>
      <span className="text-xs font-mono break-all">{str}</span>
    </div>
  )
}

// ─── 도메인 레이블 설명 매핑 ──────────────────────────────────────────────────

const DOMAIN_DESCRIPTION: Record<string, string> = {
  Wafer: '반도체 웨이퍼 (기판)',
  Lot: '생산 로트 단위',
  Recipe: '공정 레시피',
  Step: '레시피 내 공정 단계',
  Chamber: '공정 챔버 장비',
  Metrology: '계측 측정 결과',
  Parameter: '계측 파라미터',
}

// ─── DetailPanel 컴포넌트 ─────────────────────────────────────────────────────

export function DetailPanel() {
  const { selection } = useWorkspaceStore()

  if (!selection) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-4">
        <div className="text-2xl mb-2 opacity-20">↖</div>
        <p className="text-xs text-center">그래프 노드, 엣지, 테이블 행 또는<br />차트 포인트를 선택하면 상세 정보가 표시됩니다</p>
      </div>
    )
  }

  // ── 노드 상세 ────────────────────────────────────────────────────────────
  if (selection.kind === 'node') {
    const { node } = selection
    const primaryLabel = node.labels[0] ?? 'Node'
    const desc = DOMAIN_DESCRIPTION[primaryLabel]

    return (
      <ScrollArea className="h-full">
        <div className="p-3 space-y-3">
          {/* 헤더 */}
          <div>
            <div className="flex flex-wrap gap-1 mb-1">
              {node.labels.map((l) => (
                <Badge key={l} variant="secondary" className="text-xs">{l}</Badge>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">{desc ?? '그래프 노드'}</p>
            <p className="text-xs text-muted-foreground font-mono mt-0.5">ID: {node.id}</p>
          </div>

          {/* 속성 */}
          <div>
            <p className="text-xs font-medium mb-1.5">속성</p>
            <div>
              {Object.entries(node.properties).map(([k, v]) => (
                <PropertyRow key={k} name={k} value={v} />
              ))}
              {Object.keys(node.properties).length === 0 && (
                <p className="text-xs text-muted-foreground">속성 없음</p>
              )}
            </div>
          </div>
        </div>
      </ScrollArea>
    )
  }

  // ── 엣지 상세 ────────────────────────────────────────────────────────────
  if (selection.kind === 'edge') {
    const { edge } = selection

    return (
      <ScrollArea className="h-full">
        <div className="p-3 space-y-3">
          <div>
            <Badge variant="outline" className="text-xs mb-1">{edge.type}</Badge>
            <p className="text-xs text-muted-foreground font-mono">ID: {edge.id}</p>
            <p className="text-xs text-muted-foreground font-mono">
              {edge.source} → {edge.target}
            </p>
          </div>

          <div>
            <p className="text-xs font-medium mb-1.5">속성</p>
            <div>
              {Object.entries(edge.properties).map(([k, v]) => (
                <PropertyRow key={k} name={k} value={v} />
              ))}
              {Object.keys(edge.properties).length === 0 && (
                <p className="text-xs text-muted-foreground">속성 없음</p>
              )}
            </div>
          </div>
        </div>
      </ScrollArea>
    )
  }

  // ── 행 상세 ──────────────────────────────────────────────────────────────
  if (selection.kind === 'row') {
    const { rowIndex, rowData } = selection

    return (
      <ScrollArea className="h-full">
        <div className="p-3 space-y-3">
          <div>
            <Badge variant="secondary" className="text-xs mb-1">행 #{rowIndex + 1}</Badge>
          </div>
          <div>
            {Object.entries(rowData).map(([k, v]) => (
              <PropertyRow key={k} name={k} value={v} />
            ))}
          </div>
        </div>
      </ScrollArea>
    )
  }

  // ── 포인트 상세 ──────────────────────────────────────────────────────────
  if (selection.kind === 'point') {
    return (
      <div className="p-3">
        <Badge variant="secondary" className="text-xs mb-2">차트 포인트</Badge>
        <p className="text-xs text-muted-foreground">시리즈: {selection.seriesId}</p>
        <p className="text-xs text-muted-foreground">인덱스: {selection.pointIndex}</p>
      </div>
    )
  }

  return null
}
