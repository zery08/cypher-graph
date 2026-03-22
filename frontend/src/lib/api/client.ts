import axios from 'axios'
import {
  ChatResponseSchema,
  QueryResponseSchema,
  SchemaResponseSchema,
  HealthResponseSchema,
  type ChatMessage,
  type ChatResponse,
  type QueryResponse,
  type SchemaResponse,
  type HealthResponse,
  type ChatAction,
  type ToolResult,
  type StepInfo,
} from '@/lib/schemas'

// ─── Axios 클라이언트 설정 ───────────────────────────────────────────────────

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
})

// ─── API 함수 ─────────────────────────────────────────────────────────────────

export async function sendChatMessage(
  message: string,
  history: ChatMessage[],
  context?: Record<string, unknown>,
): Promise<ChatResponse> {
  const res = await api.post('/chat', { message, history, context })
  return ChatResponseSchema.parse(res.data)
}

// ─── SSE 스트리밍 이벤트 타입 ───────────────────────────────────────────────

export type StreamEvent =
  | { type: 'step_start'; tool: string; tool_key: string; input: string }
  | { type: 'step_end'; tool_key: string; output: string }
  | { type: 'token'; content: string }
  | { type: 'done'; actions: ChatAction[]; tool_results: ToolResult; steps: StepInfo[] }
  | { type: 'error'; content: string }

export async function* streamChatMessage(
  message: string,
  history: ChatMessage[],
  context?: Record<string, unknown>,
): AsyncGenerator<StreamEvent> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history, context }),
  })

  if (!response.ok || !response.body) {
    throw new Error(`HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6).trim()
        if (data === '[DONE]') return
        try {
          yield JSON.parse(data) as StreamEvent
        } catch {
          // 파싱 실패 무시
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function executeQuery(
  query: string,
  parameters?: Record<string, unknown>,
): Promise<QueryResponse> {
  const res = await api.post('/graph/query', { query, parameters })
  return QueryResponseSchema.parse(res.data)
}

export async function fetchSchema(): Promise<SchemaResponse> {
  const res = await api.get('/graph/schema')
  return SchemaResponseSchema.parse(res.data)
}

export async function checkHealth(): Promise<HealthResponse> {
  const res = await api.get('/health')
  return HealthResponseSchema.parse(res.data)
}

export default api
