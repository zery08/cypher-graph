import { useMemo } from 'react'
import {
  LineChart,
  Line,
  ScatterChart,
  Scatter,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { useWorkspaceStore } from '@/store/useWorkspaceStore'

// ─── 색상 팔레트 ──────────────────────────────────────────────────────────────

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899']

// ─── 숫자 컬럼 추출 ───────────────────────────────────────────────────────────

function getNumericColumns(rows: Record<string, unknown>[]): string[] {
  if (rows.length === 0) return []
  const keys = Object.keys(rows[0])
  return keys.filter((k) => rows.every((r) => typeof r[k] === 'number' || !isNaN(Number(r[k]))))
}

function getStringColumns(rows: Record<string, unknown>[]): string[] {
  if (rows.length === 0) return []
  const keys = Object.keys(rows[0])
  return keys.filter((k) => !getNumericColumns(rows).includes(k))
}

// ─── ChartView 컴포넌트 ───────────────────────────────────────────────────────

export function ChartView() {
  const { tableRows, chartConfig } = useWorkspaceStore()

  const numericCols = useMemo(() => getNumericColumns(tableRows), [tableRows])
  const stringCols = useMemo(() => getStringColumns(tableRows), [tableRows])

  const xKey = chartConfig?.xKey as string | undefined ?? stringCols[0] ?? numericCols[0]
  const chartType = chartConfig?.chartType as string | undefined ?? 'line'

  // ── 빈 상태 ──────────────────────────────────────────────────────────────
  if (tableRows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <div className="text-4xl mb-3 opacity-20">📊</div>
        <p className="text-sm">차트로 시각화할 데이터가 없습니다</p>
        <p className="text-xs mt-1 opacity-60">쿼리 결과가 있으면 자동으로 차트를 그립니다</p>
      </div>
    )
  }

  if (numericCols.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <p className="text-sm">수치형 컬럼이 없어 차트를 그릴 수 없습니다</p>
      </div>
    )
  }

  // ── 차트 데이터 변환 ──────────────────────────────────────────────────────
  const data = tableRows.map((row, i) => {
    const point: Record<string, unknown> = { _index: i }
    for (const key of [...numericCols, ...(xKey ? [xKey] : [])]) {
      point[key] = typeof row[key] === 'number' ? row[key] : Number(row[key])
    }
    if (xKey && stringCols.includes(xKey)) {
      point[xKey] = row[xKey]
    }
    return point
  })

  const yKeys = numericCols.filter((k) => k !== xKey).slice(0, 5)

  // ── 차트 렌더 ─────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full p-3 gap-3">
      {/* 요약 카드 */}
      <div className="flex gap-2 overflow-x-auto shrink-0">
        {yKeys.map((key) => {
          const vals = data.map((d) => d[key] as number).filter(isFinite)
          const min = Math.min(...vals)
          const max = Math.max(...vals)
          const avg = vals.reduce((a, b) => a + b, 0) / vals.length
          return (
            <div key={key} className="bg-card border border-border rounded p-2 shrink-0 min-w-[120px]">
              <div className="text-xs text-muted-foreground mb-1 truncate">{key}</div>
              <div className="flex gap-2 text-xs">
                <span>최소: <strong>{min.toFixed(2)}</strong></span>
                <span>최대: <strong>{max.toFixed(2)}</strong></span>
              </div>
              <div className="text-xs mt-0.5">평균: <strong>{avg.toFixed(2)}</strong></div>
            </div>
          )
        })}
      </div>

      {/* 차트 */}
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          {chartType === 'scatter' ? (
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey={xKey} tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', fontSize: 11 }} />
              <Scatter data={data} fill={COLORS[0]} />
            </ScatterChart>
          ) : chartType === 'bar' ? (
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey={xKey} tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', fontSize: 11 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {yKeys.map((key, i) => (
                <Bar key={key} dataKey={key} fill={COLORS[i % COLORS.length]} />
              ))}
            </BarChart>
          ) : (
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey={xKey} tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', fontSize: 11 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {yKeys.map((key, i) => {
                const color = COLORS[i % COLORS.length]
                return (
                  <Line
                    key={key}
                    type="linear"
                    dataKey={key}
                    stroke={color}
                    dot={{ r: 5, strokeWidth: 0, fill: color }}
                    activeDot={{ r: 7 }}
                    strokeWidth={1.5}
                  />
                )
              })}
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  )
}
