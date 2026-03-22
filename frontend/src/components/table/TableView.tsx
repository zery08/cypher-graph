import { useMemo, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
  type RowSelectionState,
} from '@tanstack/react-table'
import { ArrowUpDown, ArrowUp, ArrowDown, Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useWorkspaceStore } from '@/store/useWorkspaceStore'

// ─── TableView 컴포넌트 ───────────────────────────────────────────────────────

export function TableView() {
  const { tableRows, setSelection } = useWorkspaceStore()

  const [sorting, setSorting] = useState<SortingState>([])
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [globalFilter, setGlobalFilter] = useState('')
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})

  // ── 컬럼 자동 생성 ────────────────────────────────────────────────────────
  const columns = useMemo<ColumnDef<Record<string, unknown>>[]>(() => {
    if (tableRows.length === 0) return []

    const keys = Array.from(
      new Set(tableRows.flatMap((row) => Object.keys(row)))
    )

    return keys.map((key) => ({
      id: key,
      accessorFn: (row: Record<string, unknown>) => row[key],
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-1 text-xs font-medium -ml-1"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
        >
          {key}
          {column.getIsSorted() === 'asc' ? (
            <ArrowUp className="ml-1 w-3 h-3" />
          ) : column.getIsSorted() === 'desc' ? (
            <ArrowDown className="ml-1 w-3 h-3" />
          ) : (
            <ArrowUpDown className="ml-1 w-3 h-3 opacity-40" />
          )}
        </Button>
      ),
      cell: ({ getValue }) => {
        const val = getValue()
        if (val === null || val === undefined) return <span className="text-muted-foreground/40">—</span>
        const str = typeof val === 'object' ? JSON.stringify(val) : String(val)
        return (
          <span className="font-mono text-xs truncate max-w-[320px] block text-foreground" title={str}>
            {str}
          </span>
        )
      },
    }))
  }, [tableRows])

  const table = useReactTable({
    data: tableRows,
    columns,
    state: { sorting, columnFilters, globalFilter, rowSelection },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: (updater) => {
      const next = typeof updater === 'function' ? updater(rowSelection) : updater
      setRowSelection(next)
      const selectedIndex = Object.keys(next).map(Number)[0]
      if (selectedIndex !== undefined && tableRows[selectedIndex]) {
        setSelection({ kind: 'row', rowIndex: selectedIndex, rowData: tableRows[selectedIndex] })
      }
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 50 } },
    enableRowSelection: true,
  })

  // ── 빈 상태 ──────────────────────────────────────────────────────────────
  if (tableRows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <div className="text-4xl mb-3 opacity-20">⊟</div>
        <p className="text-sm">표시할 데이터가 없습니다</p>
        <p className="text-xs mt-1 opacity-60">쿼리를 실행하면 결과가 여기에 표시됩니다</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* 검색 */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border shrink-0">
        <Search className="w-3.5 h-3.5 text-muted-foreground" />
        <Input
          placeholder="전체 검색..."
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="h-7 text-xs"
        />
        <span className="text-xs text-muted-foreground shrink-0">
          {table.getFilteredRowModel().rows.length}건
        </span>
      </div>

      {/* 테이블 */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs border-collapse text-foreground">
          <thead className="sticky top-0 bg-muted/80 backdrop-blur-sm z-10">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                <th className="w-8 px-2 py-1.5 border-b border-border text-left">
                  <input
                    type="checkbox"
                    checked={table.getIsAllRowsSelected()}
                    onChange={table.getToggleAllRowsSelectedHandler()}
                    className="w-3 h-3"
                  />
                </th>
                {hg.headers.map((h) => (
                  <th key={h.id} className="px-1 py-1 border-b border-border text-left whitespace-nowrap">
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className={`border-b border-border/50 cursor-pointer hover:bg-muted/30 ${
                  row.getIsSelected() ? 'bg-primary/10' : ''
                }`}
                onClick={() => row.toggleSelected(!row.getIsSelected())}
              >
                <td className="px-2 py-1">
                  <input
                    type="checkbox"
                    checked={row.getIsSelected()}
                    onChange={row.getToggleSelectedHandler()}
                    onClick={(e) => e.stopPropagation()}
                    className="w-3 h-3"
                  />
                </td>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-2 py-2 max-w-[320px]">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 페이지네이션 */}
      <div className="flex items-center justify-between px-3 py-1.5 border-t border-border shrink-0">
        <div className="flex gap-1">
          <Button
            variant="outline"
            size="sm"
            className="h-6 text-xs px-2"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            이전
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-6 text-xs px-2"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            다음
          </Button>
        </div>
        <span className="text-xs text-muted-foreground">
          {table.getState().pagination.pageIndex + 1} / {table.getPageCount()} 페이지
        </span>
      </div>
    </div>
  )
}
