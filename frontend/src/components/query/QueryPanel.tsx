import { useState, useEffect } from 'react'
import { ChevronDown, ChevronUp, Play, Loader2, Database } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { useWorkspaceStore } from '@/store/useWorkspaceStore'
import { executeQuery } from '@/lib/api/client'

// ─── 프리셋 쿼리 ──────────────────────────────────────────────────────────────

const PRESET_QUERIES = [
  {
    label: 'Wafer 목록',
    query: 'MATCH (w:Wafer) RETURN w LIMIT 20',
  },
  {
    label: 'Recipe 목록',
    query: 'MATCH (r:Recipe) RETURN r LIMIT 20',
  },
  {
    label: 'Wafer-Recipe 관계',
    query: 'MATCH (w:Wafer)-[r]->(recipe:Recipe) RETURN w, r, recipe LIMIT 30',
  },
  {
    label: 'Lot별 Wafer',
    query: 'MATCH (l:Lot)-[:CONTAINS]->(w:Wafer) RETURN l, w LIMIT 30',
  },
  {
    label: 'Step 흐름',
    query: 'MATCH (s:Step)-[r]->(next:Step) RETURN s, r, next LIMIT 30',
  },
]

// ─── QueryPanel 컴포넌트 ──────────────────────────────────────────────────────

export function QueryPanel() {
  const {
    currentQuery,
    setCurrentQuery,
    isQueryPanelCollapsed,
    toggleQueryPanel,
    isQueryRunning,
    setQueryRunning,
    setQueryResponse,
    setGraphResult,
    setTableRows,
    setActiveTab,
    activeFilters,
  } = useWorkspaceStore()

  const [localQuery, setLocalQuery] = useState(currentQuery)

  // store의 currentQuery가 외부(채팅 등)에서 변경되면 입력창에 반영
  useEffect(() => {
    setLocalQuery(currentQuery)
  }, [currentQuery])

  const filterCount = Object.keys(activeFilters).length

  async function handleRun() {
    const trimmed = localQuery.trim()
    if (!trimmed || isQueryRunning) return

    setCurrentQuery(trimmed)
    setQueryRunning(true)
    try {
      const res = await executeQuery(trimmed)
      setQueryResponse(res)
      setGraphResult(res.result)
      setTableRows(res.result.raw)
      if (res.result.nodes.length > 0) {
        setActiveTab('graph')
      }
    } catch (err) {
      console.error('쿼리 실행 오류:', err)
    } finally {
      setQueryRunning(false)
    }
  }

  function handlePreset(query: string) {
    setLocalQuery(query)
    setCurrentQuery(query)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      void handleRun()
    }
  }

  // ── 접힌 상태 ──────────────────────────────────────────────────────────────
  if (isQueryPanelCollapsed) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-card border-b border-border">
        <Database className="w-4 h-4 text-muted-foreground shrink-0" />
        <span className="text-xs text-muted-foreground truncate flex-1">
          {currentQuery || '쿼리 없음'}
        </span>
        {filterCount > 0 && (
          <Badge variant="secondary" className="text-xs">
            필터 {filterCount}
          </Badge>
        )}
        {isQueryRunning && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={toggleQueryPanel}>
          <ChevronDown className="w-4 h-4" />
        </Button>
      </div>
    )
  }

  // ── 펼친 상태 ──────────────────────────────────────────────────────────────
  return (
    <div className="bg-card border-b border-border">
      {/* 헤더 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium">Cypher 쿼리</span>
          {filterCount > 0 && (
            <Badge variant="secondary" className="text-xs">
              필터 {filterCount}
            </Badge>
          )}
        </div>
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={toggleQueryPanel}>
          <ChevronUp className="w-4 h-4" />
        </Button>
      </div>

      {/* 프리셋 버튼 + 실행 버튼 */}
      <div className="flex items-start justify-between gap-2 px-3 pt-2">
        <div className="flex flex-wrap gap-1">
          {PRESET_QUERIES.map((p) => (
            <Button
              key={p.label}
              variant="outline"
              size="sm"
              className="h-6 text-xs px-2"
              onClick={() => handlePreset(p.query)}
            >
              {p.label}
            </Button>
          ))}
        </div>
        <Button
          size="sm"
          className="h-7 text-xs gap-1 shrink-0"
          onClick={() => void handleRun()}
          disabled={isQueryRunning || !localQuery.trim()}
        >
          {isQueryRunning ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Play className="w-3 h-3" />
          )}
          실행
        </Button>
      </div>

      {/* 쿼리 입력 */}
      <div className="px-3 pt-2 pb-3">
        <Textarea
          value={localQuery}
          onChange={(e) => setLocalQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Cypher 쿼리를 입력하세요 (Ctrl+Enter 실행)"
          className="font-mono text-xs min-h-[80px] resize-none bg-muted/30"
          spellCheck={false}
        />
      </div>
    </div>
  )
}
