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
  Wafer:     { bg: '#cfe8ff', border: '#a8d4ff', text: '#334155' },
  Recipe:    { bg: '#ddd6fe', border: '#c4b5fd', text: '#4338ca' },
  Lot:       { bg: '#d7f5e7', border: '#a7ebc9', text: '#166534' },
  Step:      { bg: '#fee8bd', border: '#f6cf7a', text: '#92400e' },
  Chamber:   { bg: '#ffd9d6', border: '#ffb5ae', text: '#991b1b' },
  Metrology: { bg: '#f8c5d8', border: '#f2a7c4', text: '#831843' },
  Parameter: { bg: '#cff5f8', border: '#9fe7ee', text: '#155e75' },
}
const DEFAULT_COLOR = { bg: '#e2e8f0', border: '#cbd5e1', text: '#334155' }

function getColor(labels: string[]) {
  for (const l of labels) if (LABEL_COLORS[l]) return LABEL_COLORS[l]
  return DEFAULT_COLOR
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
      'border-width': 0,
      'border-opacity': 0,
      'width': 92,
      'height': 92,
      'label': 'data(label)',
      'color': 'data(textColor)',
      'font-size': 10,
      'font-weight': 500,
      'font-family': 'Geist Variable, ui-sans-serif, system-ui, sans-serif',
      'text-valign': 'center',
      'text-halign': 'center',
      'text-max-width': 74,
      'text-wrap': 'wrap',
      'min-zoomed-font-size': 6,
      'overlay-opacity': 0,
      'shadow-blur': 0,
      'shadow-color': '#64748b',
      'shadow-opacity': 0,
      'shadow-offset-x': 0,
      'shadow-offset-y': 0,
    },
  },
  {
    selector: 'node:selected',
    style: {
      'border-width': 0,
      'border-color': 'data(textColor)',
      'border-opacity': 0,
      'overlay-opacity': 0,
      'shadow-blur': 16,
      'shadow-color': '#64748b',
      'shadow-opacity': 0.14,
      'shadow-offset-x': 0,
      'shadow-offset-y': 6,
    },
  },
  {
    selector: 'edge',
    style: {
      'line-color': '#a8b2c2',
      'target-arrow-color': '#a8b2c2',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.85,
      'curve-style': 'bezier',
      'width': 1.35,
      'line-opacity': 0.9,
      'label': 'data(label)',
      'font-size': 8,
      'font-weight': 500,
      'font-family': 'Geist Variable, ui-sans-serif, system-ui, sans-serif',
      'color': '#7c8798',
      'text-rotation': 'autorotate',
      'text-background-opacity': 0.9,
      'text-background-color': '#ffffff',
      'text-background-shape': 'roundrectangle',
      'text-background-padding': 2,
      'min-zoomed-font-size': 8,
      'overlay-opacity': 0,
      'source-endpoint': 'outside-to-node',
      'target-endpoint': 'outside-to-node',
    },
  },
  {
    selector: 'edge:selected',
    style: {
      'line-color': '#64748b',
      'target-arrow-color': '#64748b',
      'width': 2.2,
      'line-opacity': 0.9,
      'overlay-opacity': 0,
    },
  },
  {
    selector: '.faded',
    style: { 'opacity': 0.07 },
  },
  {
    selector: '.highlighted',
    style: {
      'line-color': '#64748b',
      'target-arrow-color': '#64748b',
      'width': 2.2,
      'line-opacity': 0.85,
      'overlay-opacity': 0,
    },
  },
  {
    selector: '.neighbor',
    style: {
      'border-width': 0,
      'border-color': 'data(textColor)',
      'border-opacity': 0,
      'overlay-opacity': 0,
      'shadow-blur': 14,
      'shadow-color': '#64748b',
      'shadow-opacity': 0.1,
      'shadow-offset-x': 0,
      'shadow-offset-y': 5,
    },
  },
]

// ─── GraphView ────────────────────────────────────────────────────────────────

export function GraphView() {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)
  const { graphResult, setSelection, focusNodeId, setFocusNodeId } = useWorkspaceStore()

  // HMR이나 스타일 수정 시 기존 cytoscape 인스턴스에도 최신 스타일을 다시 적용
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    ;(cy.style() as any).fromJson(CY_STYLE).update()
  })

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
      // 연결된 엣지 강조
      node.connectedEdges().removeClass('faded').addClass('highlighted')
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
