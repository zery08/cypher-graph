import { useRef, useEffect, useState } from 'react'
import { Send, Loader2, ChevronRight, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatStore } from '@/store/useChatStore'
import { useWorkspaceStore } from '@/store/useWorkspaceStore'
import { streamChatMessage, fetchConversationMessages } from '@/lib/api/client'
import type { ChatMessage, ChatAction, StepInfo } from '@/lib/schemas'
import { ConversationHistory } from './ConversationHistory'

// ─── 액션 chip 렌더러 ─────────────────────────────────────────────────────────

const ACTION_LABEL: Record<string, string> = {
  apply_query: '쿼리 적용',
  open_tab: '탭 열기',
  focus_node: '노드 보기',
  select_row: '행 선택',
  set_filters: '필터 적용',
  create_chart: '차트 생성',
  highlight_series: '시리즈 강조',
}

function ActionChip({ action, onApply }: { action: ChatAction; onApply: () => void }) {
  const label = ACTION_LABEL[action.type] ?? action.type
  const detail = action.type === 'open_tab'
    ? action.tab
    : action.type === 'apply_query'
    ? '...'
    : ''

  return (
    <button
      onClick={onApply}
      className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded border border-primary/30 bg-primary/5 hover:bg-primary/15 text-primary transition-colors"
    >
      <ChevronRight className="w-3 h-3" />
      {label}
      {detail && <span className="text-primary/60 ml-0.5">{detail}</span>}
    </button>
  )
}

// ─── 중간 단계 표시 ───────────────────────────────────────────────────────────

function StepsList({ steps }: { steps: StepInfo[] }) {
  const [open, setOpen] = useState(false)
  if (!steps || steps.length === 0) return null

  return (
    <div className="max-w-[90%] text-xs">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-muted-foreground/70 hover:text-muted-foreground transition-colors mb-1"
      >
        <ChevronRight className={`w-3 h-3 transition-transform ${open ? 'rotate-90' : ''}`} />
        <span>{steps.length}개 도구 사용됨 — {steps.map(s => s.tool).join(', ')}</span>
      </button>

      {open && (
        <div className="flex flex-col gap-2 pl-4 border-l border-border/50">
          {steps.map((step, i) => (
            <div key={i} className="bg-muted/30 rounded p-2 space-y-1">
              <div className="font-medium text-muted-foreground flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-primary/60 shrink-0" />
                {step.tool}
              </div>
              {step.input && (
                <div className="text-muted-foreground/60 whitespace-pre-wrap break-words">
                  입력: {step.input}
                </div>
              )}
              <div className="text-muted-foreground/80 whitespace-pre-wrap break-words">
                {step.output}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── 메시지 버블 ─────────────────────────────────────────────────────────────

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  actions?: ChatAction[]
  steps?: StepInfo[]
  onAction: (action: ChatAction) => void
}

function MessageBubble({ role, content, thinking, actions, steps, onAction }: MessageBubbleProps) {
  const isUser = role === 'user'

  return (
    <div className={`flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
      {!isUser && thinking && (
        <div className="max-w-[90%] text-xs text-muted-foreground bg-muted/20 border border-border/50 rounded px-3 py-2 whitespace-pre-wrap break-words">
          <div className="font-medium text-[11px] uppercase tracking-wide mb-1 opacity-70">Thinking</div>
          {thinking}
        </div>
      )}
      {!isUser && <StepsList steps={steps ?? []} />}
      <div
        className={`max-w-[90%] rounded-lg px-3 py-2 text-sm leading-relaxed ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-foreground'
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words">{content}</p>
        ) : (
          <div className="prose prose-sm prose-invert max-w-none break-words
            [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0.5
            [&_code]:bg-background/60 [&_code]:px-1 [&_code]:rounded [&_code]:text-xs [&_code]:font-mono
            [&_pre]:bg-background/60 [&_pre]:p-2 [&_pre]:rounded [&_pre]:overflow-x-auto [&_pre]:text-xs
            [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_h1]:font-bold [&_h2]:font-semibold
            [&_strong]:font-semibold [&_a]:text-primary [&_blockquote]:border-l-2 [&_blockquote]:pl-2 [&_blockquote]:opacity-70">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>

      {/* 액션 chip — 자동 실행되는 apply_query, open_tab은 표시하지 않음 */}
      {actions && actions.filter(a => a.type !== 'apply_query' && a.type !== 'open_tab').length > 0 && (
        <div className="flex flex-wrap gap-1 max-w-[90%]">
          {actions
            .filter(a => a.type !== 'apply_query' && a.type !== 'open_tab')
            .map((action, i) => (
              <ActionChip key={i} action={action} onApply={() => onAction(action)} />
            ))}
        </div>
      )}
    </div>
  )
}

// ─── ChatPanel 컴포넌트 ───────────────────────────────────────────────────────

export function ChatPanel() {
  const {
    messages,
    isLoading,
    addMessage,
    addStreamingMessage,
    appendToken,
    appendThinking,
    updateMessage,
    setLoading,
    contextSnapshot,
    setContextSnapshot,
  } = useChatStore()
  const {
    setActiveTab,
    setCurrentQuery,
    setFocusNodeId,
    setGraphResult,
    setTableRows,
    setChartConfig,
    setLastToolSummary,
    selection,
    currentQuery,
  } = useWorkspaceStore()

  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // ── 스크롤 자동 이동 ──────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // ── 컨텍스트 스냅샷 업데이트 ──────────────────────────────────────────────
  useEffect(() => {
    if (selection) {
      const kind = selection.kind
      const label =
        kind === 'node'
          ? `노드: ${selection.node.labels.join(', ')} (${selection.node.id})`
          : kind === 'edge'
          ? `엣지: ${selection.edge.type}`
          : kind === 'row'
          ? `행 #${selection.rowIndex + 1}`
          : ''
      setContextSnapshot(label || null)
    } else {
      setContextSnapshot(null)
    }
  }, [selection, setContextSnapshot])

  // ── 액션 처리기 ──────────────────────────────────────────────────────────
  function handleAction(action: ChatAction) {
    switch (action.type) {
      case 'open_tab':
        if (action.tab === 'graph' || action.tab === 'table' || action.tab === 'chart') {
          setActiveTab(action.tab)
        }
        break
      case 'apply_query':
        if (action.query) setCurrentQuery(action.query)
        break
      case 'focus_node':
        setActiveTab('graph')
        if (action.node_id) setFocusNodeId(action.node_id)
        break
      case 'create_chart':
        setActiveTab('chart')
        setChartConfig(action.chart_config ?? {})
        break
      case 'set_filters':
        break
      default:
        break
    }
  }

  // ── 메시지 전송 ──────────────────────────────────────────────────────────
  async function handleSend() {
    const text = input.trim()
    if (!text || isLoading) return

    setInput('')

    addMessage({ role: 'user', content: text })
    setLoading(true)

    // 히스토리 구성 (최근 12개)
    const history: ChatMessage[] = messages.slice(-12).map((m) => ({
      role: m.role,
      content: m.content,
    }))

    // 컨텍스트 구성
    const context: Record<string, unknown> = {}
    if (currentQuery) context.current_query = currentQuery
    if (selection) {
      if (selection.kind === 'node') context.selected_node = selection.node.id
      if (selection.kind === 'row') context.selected_row = selection.rowIndex
    }

    // 스트리밍 메시지 자리 생성
    const assistantId = addStreamingMessage()
    const liveSteps: StepInfo[] = []

    try {
      for await (const event of streamChatMessage(text, history, context)) {
        if (event.type === 'token') {
          appendToken(assistantId, event.content)
        } else if (event.type === 'thinking_token') {
          appendThinking(assistantId, event.content)
        } else if (event.type === 'step_start') {
          // 진행 중인 step을 임시로 표시
          const step: StepInfo = { tool: event.tool, tool_key: event.tool_key, input: event.input, output: '...' }
          liveSteps.push(step)
          updateMessage(assistantId, { steps: [...liveSteps] })
        } else if (event.type === 'step_end') {
          // 해당 step의 output 갱신
          let idx = -1
          for (let i = liveSteps.length - 1; i >= 0; i--) {
            if (liveSteps[i].tool_key === event.tool_key && liveSteps[i].output === '...') { idx = i; break }
          }
          if (idx !== -1) liveSteps[idx] = { ...liveSteps[idx], output: event.output }
          updateMessage(assistantId, { steps: [...liveSteps] })
        } else if (event.type === 'done') {
          const toolResults = event.tool_results
          const actions = event.actions ?? []

          updateMessage(assistantId, {
            actions,
            steps: event.steps,
            toolResults: toolResults ?? undefined,
            thinking: event.thinking ?? undefined,
          })

          // tool 결과 반영
          const graph = toolResults?.graph
          if (graph) {
            setGraphResult(graph)
            setTableRows(graph.raw)
          }
          if (toolResults?.table) setTableRows(toolResults.table)
          if (toolResults?.cypher) setCurrentQuery(toolResults.cypher)
          if (toolResults?.summary) setLastToolSummary(toolResults.summary)
          if (toolResults?.chart) setChartConfig(toolResults.chart)

          // 자동 액션 실행
          for (const action of actions) {
            if (action.type === 'apply_query' && action.query) {
              setCurrentQuery(action.query)
            } else if (action.type === 'open_tab') {
              handleAction(action)
            }
          }

          // 그래프 노드가 있으면 자동으로 그래프 탭으로 전환
          if (graph && graph.nodes.length > 0) {
            setActiveTab('graph')
          }
        } else if (event.type === 'error') {
          updateMessage(assistantId, { content: `오류가 발생했습니다: ${event.content}` })
        }
      }
    } catch (err) {
      console.error('채팅 오류:', err)
      updateMessage(assistantId, { content: '오류가 발생했습니다. 백엔드 서버를 확인해주세요.' })
    } finally {
      setLoading(false)
    }
  }

  async function handleLoadConversation(conversationId: string) {
    try {
      const msgs = await fetchConversationMessages(conversationId)
      useChatStore.getState().clearMessages()
      for (const m of msgs) {
        addMessage({
          role: m.role as 'user' | 'assistant',
          content: m.content,
          actions: (m.actions ?? []) as ChatAction[],
        })
      }
    } catch (err) {
      console.error('대화 불러오기 실패:', err)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full bg-card">
      {/* 채팅 헤더 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
        <div>
          <h2 className="text-sm font-medium">AI 분석 어시스턴트</h2>
          <p className="text-xs text-muted-foreground">wafer / recipe / metrology 데이터 탐색</p>
        </div>
        <div className="flex items-center gap-1">
          <ConversationHistory onLoad={handleLoadConversation} />
          {messages.length > 0 && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => useChatStore.getState().clearMessages()}
            >
              <X className="w-3 h-3" />
            </Button>
          )}
        </div>
      </div>

      {/* 컨텍스트 배너 */}
      {contextSnapshot && (
        <div className="px-3 py-1.5 bg-primary/5 border-b border-primary/10 shrink-0">
          <p className="text-xs text-primary/80">현재 선택: {contextSnapshot}</p>
        </div>
      )}

      {/* 메시지 목록 */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="flex flex-col gap-3 p-3">
          {messages.length === 0 && (
            <div className="flex flex-col gap-2 mt-4">
              <p className="text-xs text-muted-foreground text-center">질문 예시</p>
              {[
                '이 데이터셋에서 어떤 wafer 종류가 있나요?',
                'wafer와 recipe 관계를 그래프로 보여주세요',
                '특정 lot의 계측 결과 이상치가 있는지 확인해주세요',
                'step별 파라미터 추이를 차트로 보여주세요',
              ].map((q) => (
                <button
                  key={q}
                  onClick={() => { setInput(q); textareaRef.current?.focus() }}
                  className="text-xs text-left px-2 py-1.5 rounded border border-border/60 hover:border-primary/40 hover:bg-primary/5 transition-colors text-muted-foreground"
                >
                  {q}
                </button>
              ))}
            </div>
          )}

          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              role={msg.role}
              content={msg.content}
              thinking={msg.thinking}
              actions={msg.actions}
              steps={msg.steps}
              onAction={handleAction}
            />
          ))}

          {isLoading && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-xs">분석 중...</span>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* 입력창 */}
      <div className="px-3 pt-2 pb-3 border-t border-border shrink-0">
        <div className="flex gap-2">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="질문을 입력하세요 (Enter 전송, Shift+Enter 줄바꿈)"
            className="text-sm resize-none min-h-[60px] max-h-[120px]"
            disabled={isLoading}
          />
          <Button
            size="icon"
            className="h-auto w-10 shrink-0"
            onClick={() => void handleSend()}
            disabled={isLoading || !input.trim()}
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
