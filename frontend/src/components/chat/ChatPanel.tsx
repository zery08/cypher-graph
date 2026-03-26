import { useRef, useEffect, useState, Fragment } from 'react'
import { Send, Loader2, ChevronRight, X, Sparkles } from 'lucide-react'
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

// ─── 추론 항목 (타이머 + 개별 접기) ─────────────────────────────────────────

function ThoughtItem({ text, isStreaming }: { text: string; isStreaming: boolean }) {
  const [open, setOpen] = useState(true)
  const [seconds, setSeconds] = useState(0)
  const frozenRef = useRef(false)

  // 스트리밍 중 초 카운트, 완료 시 freeze
  useEffect(() => {
    if (!isStreaming) {
      frozenRef.current = true
      setOpen(false)
      return
    }
    const id = setInterval(() => {
      if (!frozenRef.current) setSeconds(s => s + 1)
    }, 1000)
    return () => clearInterval(id)
  }, [isStreaming])

  return (
    <div className="flex gap-2 items-start">
      <span className="mt-[5px] w-1.5 h-1.5 rounded-full bg-foreground/60 shrink-0" />
      <div className="flex-1 min-w-0">
        <button
          onClick={() => setOpen(o => !o)}
          className="flex items-center gap-1 text-foreground/75 hover:text-foreground transition-colors text-left"
        >
          <span className="font-medium">Thought for {seconds}s</span>
          <ChevronRight className={`w-3 h-3 shrink-0 transition-transform ${open ? 'rotate-90' : ''}`} />
          {isStreaming && <Loader2 className="w-2.5 h-2.5 animate-spin text-muted-foreground/50 ml-0.5 shrink-0" />}
        </button>
        {open && (
          <div className="mt-1 text-muted-foreground/60 whitespace-pre-wrap break-words leading-relaxed">
            {text}
            {isStreaming && (
              <span className="inline-block w-1 h-3 bg-muted-foreground/40 rounded-sm animate-pulse ml-0.5 align-middle" />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── 도구 항목 (접기/펼치기) ─────────────────────────────────────────────────

function ToolItem({ step, isStreaming }: { step: StepInfo; isStreaming: boolean }) {
  const [open, setOpen] = useState(false)
  const isPending = step.output === '...'

  // 완료되면 접힌 채로 유지
  useEffect(() => {
    if (!isPending) setOpen(false)
  }, [isPending])

  const inputPreview = step.input ? ` ${step.input.slice(0, 50)}${step.input.length > 50 ? '…' : ''}` : ''

  return (
    <div className="flex gap-2 items-start">
      <span className="mt-[5px] w-1.5 h-1.5 rounded-full bg-green-500/80 shrink-0" />
      <div className="flex-1 min-w-0">
        <button
          onClick={() => setOpen(o => !o)}
          className="flex items-center gap-1 text-left hover:opacity-80 transition-opacity"
        >
          <span className="font-semibold text-green-600">{step.tool}</span>
          {inputPreview && !open && (
            <span className="text-muted-foreground/50 font-normal truncate">{inputPreview}</span>
          )}
          {!isPending && (
            <ChevronRight className={`w-3 h-3 shrink-0 text-muted-foreground/40 transition-transform ${open ? 'rotate-90' : ''}`} />
          )}
          {isPending && isStreaming && (
            <Loader2 className="w-2.5 h-2.5 animate-spin text-green-500/60 ml-0.5" />
          )}
        </button>
        {open && step.output && step.output !== '...' && (
          <div className="mt-1 text-muted-foreground/55 whitespace-pre-wrap break-words leading-relaxed">
            {step.output}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── 중간 단계 표시 ───────────────────────────────────────────────────────────

function StepsList({ steps, isStreaming = false }: { steps: StepInfo[]; isStreaming?: boolean }) {
  if (!steps.length) return null

  return (
    <div className="text-xs flex flex-col gap-2 mb-1 w-full">
      {steps.map((step, i) => (
        <Fragment key={i}>
          {step.reasoning && (
            <ThoughtItem
              text={step.reasoning}
              isStreaming={isStreaming && step.output === '...'}
            />
          )}
          <ToolItem step={step} isStreaming={isStreaming} />
        </Fragment>
      ))}
    </div>
  )
}

// ─── 메시지 버블 ─────────────────────────────────────────────────────────────

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  actions?: ChatAction[]
  steps?: StepInfo[]
  isStreaming?: boolean
  streamingStatus?: string | null
  onAction: (action: ChatAction) => void
}

function MessageBubble({ role, content, actions, steps, isStreaming, streamingStatus, onAction }: MessageBubbleProps) {
  const isUser = role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-lg px-3 py-2 text-sm leading-relaxed bg-muted text-muted-foreground">
          <p className="whitespace-pre-wrap break-words">{content}</p>
        </div>
      </div>
    )
  }

  // assistant
  return (
    <div className="flex flex-col gap-1">
        {/* 추론/도구 단계 */}
        {(steps?.length ?? 0) > 0 && (
          <StepsList steps={steps ?? []} isStreaming={isStreaming} />
        )}

        {/* 상태 표시 — 주황색 아이콘 + 텍스트, 답변 시작 후 사라짐 */}
        {isStreaming && !content && streamingStatus && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
            <Sparkles className="w-3 h-3 shrink-0 animate-pulse text-orange-400/70" />
            <span>{streamingStatus}</span>
          </div>
        )}

        {/* 답변 버블 */}
        {content && (
          <div className="max-w-[95%] rounded-lg px-3 py-2 text-sm leading-relaxed bg-background border border-border/40 text-foreground">
            <div className="prose prose-sm prose-neutral max-w-none break-words
              prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5
              prose-headings:text-foreground prose-p:text-foreground prose-strong:text-foreground
              prose-li:text-foreground prose-blockquote:text-muted-foreground
              prose-code:text-foreground prose-code:bg-muted prose-code:px-1 prose-code:rounded prose-code:text-xs prose-code:font-mono prose-code:before:content-none prose-code:after:content-none
              prose-pre:bg-muted prose-pre:text-foreground prose-pre:text-xs prose-pre:overflow-x-auto
              prose-a:text-primary prose-blockquote:border-l-2 prose-blockquote:pl-2
              prose-h1:text-base prose-h2:text-sm prose-h3:text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            </div>
          </div>
        )}

        {/* 액션 chip */}
        {actions && actions.filter(a => a.type !== 'apply_query' && a.type !== 'open_tab').length > 0 && (
          <div className="flex flex-wrap gap-1">
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
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null)
  const [streamingStatus, setStreamingStatus] = useState<string | null>(null)
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
    setStreamingMessageId(assistantId)
    setStreamingStatus('생각 중...')
    const liveSteps: StepInfo[] = []
    let liveReasoning = ''
    let pendingStepReasoning = ''

    try {
      for await (const event of streamChatMessage(text, history, context)) {
        if (event.type === 'reasoning_token') {
          liveReasoning += event.content
          updateMessage(assistantId, { reasoning: liveReasoning })
        } else if (event.type === 'token') {
          setStreamingStatus(null)  // 답변 시작하면 상태 표시 제거
          appendToken(assistantId, event.content)
        } else if (event.type === 'step_start') {
          setStreamingStatus(`도구 호출 중: ${event.tool}`)
          pendingStepReasoning = liveReasoning
          liveReasoning = ''  // 다음 step을 위해 초기화
          const step: StepInfo = {
            tool: event.tool,
            tool_key: event.tool_key,
            input: event.input,
            output: '...',
            reasoning: pendingStepReasoning || undefined,
          }
          liveSteps.push(step)
          updateMessage(assistantId, { steps: [...liveSteps], reasoning: null })
        } else if (event.type === 'step_end') {
          setStreamingStatus('생각 중...')
          let idx = -1
          for (let i = liveSteps.length - 1; i >= 0; i--) {
            if (liveSteps[i].tool_key === event.tool_key && liveSteps[i].output === '...') { idx = i; break }
          }
          if (idx !== -1) liveSteps[idx] = { ...liveSteps[idx], output: event.output }
          updateMessage(assistantId, { steps: [...liveSteps] })
        } else if (event.type === 'done') {
          const toolResults = event.tool_results
          const actions = event.actions ?? []

          // liveSteps를 유지해 per-step reasoning 보존
          // event.steps의 output으로만 업데이트
          if (event.steps) {
            event.steps.forEach((s: StepInfo, i: number) => {
              if (liveSteps[i]) liveSteps[i] = { ...liveSteps[i], output: s.output }
            })
          }

          updateMessage(assistantId, {
            actions,
            steps: [...liveSteps],
            toolResults: toolResults ?? undefined,
            reasoning: null,
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
      setStreamingMessageId(null)
      setStreamingStatus(null)
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
                '최근 wafer 10개 알려줘',
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
              actions={msg.actions}
              steps={msg.steps}
              isStreaming={msg.id === streamingMessageId}
              streamingStatus={msg.id === streamingMessageId ? streamingStatus : null}
              onAction={handleAction}
            />
          ))}

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
