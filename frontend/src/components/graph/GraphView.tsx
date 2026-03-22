import { useEffect, useRef, useCallback } from 'react'
import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import type { Core, NodeSingular, EdgeSingular } from 'cytoscape'
import { Maximize2, ZoomIn, ZoomOut, LocateFixed } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useWorkspaceStore } from '@/store/useWorkspaceStore'

cytoscape.use(fcose)

// ─── 레이블별 색상 ────────────────────────────────────────────────────────────

const LABEL_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  Wafer:     { bg: '#4c8edd', border: '#6aadff', text: '#ffffff' },
  Recipe:    { bg: '#8b5cf6', border: '#a78bfa', text: '#ffffff' },
  Lot:       { bg: '#10b981', border: '#34d399', text: '#ffffff' },
  Step:      { bg: '#f59e0b', border: '#fcd34d', text: '#1c1917' },
  Chamber:   { bg: '#ef4444', border: '#fca5a5', text: '#ffffff' },
  Metrology: { bg: '#ec4899', border: '#f9a8d4', text: '#ffffff' },
  Parameter: { bg: '#06b6d4', border: '#67e8f9', text: '#ffffff' },
}
const DEFAULT_COLOR = { bg: '#64748b', border: '#94a3b8', text: '#ffffff' }

function getColor(labels: string[]) {
  for (const l of labels) if (LABEL_COLORS[l]) return LABEL_COLORS[l]
  return DEFAULT_COLOR
}

function getIcon(labels: string[]): string {
  const icons: Record<string, string> = {
    Wafer: '⬡', Recipe: '⚙', Lot: '📦', Step: '▶',
    Chamber: '⬤', Metrology: '◈', Parameter: '◆',
  }
  for (const l of labels) if (icons[l]) return icons[l]
  return '●'
}

function getNodeLabel(labels: string[], props: Record<string, unknown>): string {
  const pick = (...keys: string[]) => {
    for (const k of keys) { const v = props[k]; if (v != null && v !== '') return String(v) }
    return null
  }
  switch (labels[0]) {
    case 'Wafer':     return pick('wafer_id', 'name') ?? 'Wafer'
    case 'Lot':       return pick('lot_id', 'name') ?? 'Lot'
    case 'Recipe':    return pick('recipe_id', 'name') ?? 'Recipe'
    case 'Step':      return pick('step_name', 'name', 'step_id') ?? 'Step'
    case 'Chamber':   return pick('chamber_id', 'name') ?? 'Chamber'
    case 'Metrology': return pick('param_name', 'name') ?? 'Metrology'
    case 'Parameter': return pick('param_name', 'name') ?? 'Param'
    default:          return pick('name', 'id') ?? (labels[0] ?? 'Node')
  }
}

// ─── 스타일 (타입 어서션 없이 plain object) ──────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const CY_STYLE: any[] = [
  {
    selector: 'node',
    style: {
      'shape': 'ellipse',
      'background-color': 'data(bg)',
      'border-color': 'data(border)',
      'border-width': 3,
      'border-opacity': 0.6,
      'width': 68,
      'height': 68,
      'label': 'data(label)',
      'color': 'data(textColor)',
      'font-size': 11,
      'font-weight': 600,
      'font-family': 'ui-sans-serif, system-ui, sans-serif',
      'text-valign': 'center',
      'text-halign': 'center',
      'text-max-width': 60,
      'text-wrap': 'wrap',
      'min-zoomed-font-size': 6,
      'overlay-opacity': 0,
    },
  },
  {
    selector: 'node:selected',
    style: {
      'border-width': 4,
      'border-color': '#f8fafc',
      'border-opacity': 1,
      'overlay-opacity': 0,
      'shadow-blur': 16,
      'shadow-color': 'data(border)',
      'shadow-opacity': 0.9,
      'shadow-offset-x': 0,
      'shadow-offset-y': 0,
    },
  },
  {
    selector: 'edge',
    style: {
      'line-color': '#475569',
      'target-arrow-color': '#64748b',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 1,
      'curve-style': 'bezier',
      'width': 1.5,
      'line-opacity': 0.6,
      'label': 'data(label)',
      'font-size': 9,
      'font-family': 'ui-sans-serif, system-ui, sans-serif',
      'color': '#94a3b8',
      'text-rotation': 'autorotate',
      'text-background-color': '#1e293b',
      'text-background-opacity': 0.9,
      'text-background-padding': '3px',
      'text-background-shape': 'roundrectangle',
      'min-zoomed-font-size': 8,
      'overlay-opacity': 0,
    },
  },
  {
    selector: 'edge:selected',
    style: {
      'line-color': '#38bdf8',
      'target-arrow-color': '#38bdf8',
      'width': 2.5,
      'line-opacity': 1,
      'overlay-opacity': 0,
    },
  },
  {
    selector: '.faded',
    style: { 'opacity': 0.08 },
  },
  {
    selector: '.highlighted',
    style: {
      'line-color': 'data(sourceColor)',
      'target-arrow-color': 'data(sourceColor)',
      'width': 2.5,
      'line-opacity': 1,
      'overlay-opacity': 0,
    },
  },
  {
    selector: '.neighbor',
    style: {
      'border-width': 3,
      'border-color': '#f8fafc',
      'border-opacity': 0.5,
      'overlay-opacity': 0,
    },
  },
]

// ─── GraphView ────────────────────────────────────────────────────────────────

export function GraphView() {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)
  const { graphResult, setSelection, focusNodeId, setFocusNodeId } = useWorkspaceStore()

  // 컨테이너 크기 변화 감지 → cy.resize() 호출
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      cyRef.current?.resize()
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    if (!containerRef.current) return
    const el = containerRef.current
    // 부모 체인 전체 높이 진단
    let node: HTMLElement | null = el
    let depth = 0
    while (node && depth < 10) {
      console.log(`[GraphView] depth=${depth} tag=${node.tagName} class="${node.className.toString().slice(0,60)}" clientH=${node.clientHeight} offsetH=${node.offsetHeight}`)
      node = node.parentElement
      depth++
    }
    const cy = cytoscape({
      container: containerRef.current,
      style: CY_STYLE,
      layout: { name: 'grid' },
      wheelSensitivity: 0.25,
      minZoom: 0.1,
      maxZoom: 5,
      boxSelectionEnabled: false,
      // 배경 투명 (부모 bg 그대로)
      styleEnabled: true,
    })

    cy.on('tap', 'node', (e) => {
      const node = e.target as NodeSingular
      cy.elements().addClass('faded').removeClass('highlighted neighbor')
      node.removeClass('faded')
      node.neighborhood().removeClass('faded')
      // 연결된 엣지 강조 (노드 색상으로)
      const borderColor = node.data('border') as string
      node.connectedEdges().removeClass('faded').addClass('highlighted').data('sourceColor', borderColor)
      // 이웃 노드 강조
      node.neighborhood('node').addClass('neighbor')
      const d = node.data() as { id: string; labels: string[]; properties: Record<string, unknown> }
      setSelection({ kind: 'node', node: { id: d.id, labels: d.labels ?? [], properties: d.properties ?? {} } })
    })

    cy.on('tap', 'edge', (e) => {
      const edge = e.target as EdgeSingular
      cy.elements().addClass('faded').removeClass('highlighted neighbor')
      edge.removeClass('faded')
      edge.connectedNodes().removeClass('faded')
      const d = edge.data() as { id: string; type: string; source: string; target: string; properties: Record<string, unknown> }
      setSelection({ kind: 'edge', edge: { id: d.id, type: d.type ?? '', source: d.source, target: d.target, properties: d.properties ?? {} } })
    })

    cy.on('tap', (e) => {
      if (e.target !== cy) return
      cy.elements().removeClass('faded highlighted neighbor')
      setSelection(null)
    })

    cyRef.current = cy
    return () => { cy.destroy(); cyRef.current = null }
  }, [setSelection])

  useEffect(() => {
    const cy = cyRef.current
    console.log('[GraphView] graphResult 변경 - cy:', !!cy, 'nodes:', graphResult?.nodes.length ?? 0)
    if (!cy || !graphResult) return

    cy.elements().remove()
    cy.elements().removeClass('faded')

    const elements: cytoscape.ElementDefinition[] = []

    for (const node of graphResult.nodes) {
      const c = getColor(node.labels)
      elements.push({
        group: 'nodes',
        data: {
          id: node.id,
          label: getNodeLabel(node.labels, node.properties),
          bg: c.bg,
          border: c.border,
          textColor: c.text,
          bgHover: c.border + '33',
          labels: node.labels,
          properties: node.properties,
        },
      })
    }

    for (const edge of graphResult.edges) {
      elements.push({
        group: 'edges',
        data: { id: edge.id, source: edge.source, target: edge.target, label: edge.type, type: edge.type, properties: edge.properties },
      })
    }

    cy.add(elements)
    console.log('[GraphView] 엘리먼트 추가 완료 - cy 컨테이너 크기:', cy.width(), 'x', cy.height())

    const n = graphResult.nodes.length
    const layoutOpts = n <= 1
      ? { name: 'grid' }
      : {
          name: 'fcose',
          animate: n < 100,
          animationDuration: 350,
          quality: 'default',
          randomize: true,
          nodeSeparation: 100,
          idealEdgeLength: 90,
          nodeRepulsion: 5500,
          numIter: 2000,
          tile: true,
        }

    cy.resize()
    const layout = cy.layout(layoutOpts as Parameters<typeof cy.layout>[0])
    layout.run()
    layout.one('layoutstop', () => { cy.fit(undefined, 50) })
  }, [graphResult])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy || !focusNodeId) return
    const node = cy.getElementById(focusNodeId)
    if (node.length > 0) {
      cy.elements().addClass('faded')
      node.removeClass('faded')
      node.neighborhood().removeClass('faded')
      cy.animate({ center: { eles: node }, zoom: 2 }, { duration: 400 })
      node.select()
    }
    setFocusNodeId(null)
  }, [focusNodeId, setFocusNodeId])

  const fit     = useCallback(() => { cyRef.current?.fit(undefined, 50); cyRef.current?.elements().removeClass('faded') }, [])
  const zoomIn  = useCallback(() => { const cy = cyRef.current; if (!cy) return; cy.zoom({ level: cy.zoom() * 1.3, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }) }, [])
  const zoomOut = useCallback(() => { const cy = cyRef.current; if (!cy) return; cy.zoom({ level: cy.zoom() * 0.77, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }) }, [])

  const isEmpty = !graphResult || graphResult.nodes.length === 0
  const activeLabels = graphResult ? [...new Set(graphResult.nodes.flatMap(n => n.labels))] : []

  return (
    <div style={{ position: 'absolute', inset: 0 }} className="bg-card">
      {/* 점 그리드 */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle, #334155 1px, transparent 1px)',
          backgroundSize: '28px 28px',
          opacity: 0.4,
        }}
      />

      <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />

      {/* 빈 상태 */}
      {isEmpty && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground pointer-events-none">
          <svg className="w-14 h-14 mb-3 opacity-10" viewBox="0 0 64 64" fill="none">
            <circle cx="16" cy="32" r="8" stroke="currentColor" strokeWidth="2"/>
            <circle cx="48" cy="16" r="8" stroke="currentColor" strokeWidth="2"/>
            <circle cx="48" cy="48" r="8" stroke="currentColor" strokeWidth="2"/>
            <line x1="24" y1="29" x2="40" y2="19" stroke="currentColor" strokeWidth="1.5"/>
            <line x1="24" y1="35" x2="40" y2="45" stroke="currentColor" strokeWidth="1.5"/>
          </svg>
          <p className="text-sm">그래프 결과가 없습니다</p>
          <p className="text-xs mt-1 opacity-50">쿼리를 실행하거나 채팅으로 질문해보세요</p>
        </div>
      )}

      {/* 컨트롤 */}
      {!isEmpty && (
        <div className="absolute bottom-3 right-3 flex flex-col gap-1">
          {[
            { icon: <Maximize2 className="w-3.5 h-3.5"/>, fn: fit },
            { icon: <ZoomIn className="w-3.5 h-3.5"/>,   fn: zoomIn },
            { icon: <ZoomOut className="w-3.5 h-3.5"/>,  fn: zoomOut },
          ].map(({ icon, fn }, i) => (
            <Button key={i} variant="outline" size="icon" className="h-7 w-7" onClick={fn}>
              {icon}
            </Button>
          ))}
        </div>
      )}

      {/* 카운트 */}
      {!isEmpty && (
        <div className="absolute bottom-3 left-3 text-xs text-muted-foreground bg-background/80 px-2 py-1 rounded border border-border">
          {graphResult!.nodes.length}N · {graphResult!.edges.length}E
        </div>
      )}

      {/* 범례 */}
      {!isEmpty && activeLabels.length > 0 && (
        <div className="absolute top-3 right-3 bg-background/90 border border-border rounded-lg px-3 py-2.5 text-xs space-y-1.5 backdrop-blur-sm shadow-lg">
          {activeLabels.map(label => {
            const c = LABEL_COLORS[label] ?? DEFAULT_COLOR
            return (
              <div key={label} className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full shrink-0 border" style={{ backgroundColor: c.bg, borderColor: c.border }}/>
                <span className="text-foreground/80 font-medium">{label}</span>
              </div>
            )
          })}
        </div>
      )}

      {/* 힌트 */}
      {!isEmpty && (
        <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-background/80 border border-border rounded px-2 py-1 text-xs text-muted-foreground">
          <LocateFixed className="w-3 h-3"/>
          클릭으로 이웃 강조
        </div>
      )}
    </div>
  )
}
