import { useState, useRef, useEffect } from 'react'
import { History, Trash2, Loader2 } from 'lucide-react'
import {
  fetchConversations,
  fetchConversationMessages,
  deleteConversation,
  type ConversationSummary,
} from '@/lib/api/client'
import { useChatStore } from '@/store/useChatStore'

interface Props {
  onLoad: (conversationId: string) => void
}

export function ConversationHistory({ onLoad }: Props) {
  const [open, setOpen] = useState(false)
  const [list, setList] = useState<ConversationSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  // 외부 클릭 시 닫기
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  async function handleOpen() {
    if (open) { setOpen(false); return }
    setOpen(true)
    setLoading(true)
    try {
      setList(await fetchConversations())
    } catch {
      setList([])
    } finally {
      setLoading(false)
    }
  }

  async function handleLoad(id: string) {
    setOpen(false)
    onLoad(id)
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    setDeletingId(id)
    try {
      await deleteConversation(id)
      setList(prev => prev.filter(c => c.id !== id))
    } finally {
      setDeletingId(null)
    }
  }

  function formatDate(iso: string) {
    const d = new Date(iso)
    const now = new Date()
    const diff = now.getTime() - d.getTime()
    if (diff < 86400000) return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
    if (diff < 604800000) return d.toLocaleDateString('ko-KR', { weekday: 'short' })
    return d.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={handleOpen}
        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        title="대화 기록"
      >
        <History className="w-3.5 h-3.5" />
        <span>기록</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-64 bg-popover border border-border rounded-lg shadow-lg z-50 overflow-hidden">
          <div className="px-3 py-2 border-b border-border">
            <span className="text-xs font-medium text-muted-foreground">이전 대화</span>
          </div>

          <div className="max-h-72 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
              </div>
            ) : list.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-6">저장된 대화가 없습니다</p>
            ) : (
              list.map(conv => (
                <div
                  key={conv.id}
                  onClick={() => handleLoad(conv.id)}
                  className="group flex items-center justify-between px-3 py-2 hover:bg-muted cursor-pointer"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-foreground truncate">{conv.title}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">{formatDate(conv.updated_at)}</p>
                  </div>
                  <button
                    onClick={(e) => handleDelete(e, conv.id)}
                    className="ml-2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive transition-all shrink-0"
                  >
                    {deletingId === conv.id
                      ? <Loader2 className="w-3 h-3 animate-spin" />
                      : <Trash2 className="w-3 h-3" />
                    }
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
