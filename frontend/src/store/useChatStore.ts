import { create } from 'zustand'
import type { ChatAction, ToolResult, StepInfo } from '@/lib/schemas'

// ─── 채팅 메시지 타입 ─────────────────────────────────────────────────────────

export interface ChatEntry {
  id: string
  role: 'user' | 'assistant'
  content: string
  preContent?: string         // 툴 호출 전 LLM이 내뱉은 텍스트 (비thinking 모델)
  actions?: ChatAction[]
  steps?: StepInfo[]
  toolResults?: ToolResult
  reasoning?: string | null   // 스트리밍 중 실시간 reasoning 토큰 (live only)
  finalReasoning?: string     // 모든 tool 완료 후 최종 추론 (영구 보존)
  finalReasoningDurationMs?: number
  timestamp: number
}

// ─── 스토어 상태 타입 ─────────────────────────────────────────────────────────

interface ChatState {
  messages: ChatEntry[]
  isLoading: boolean
  contextSnapshot: string | null

  addMessage: (entry: Omit<ChatEntry, 'id' | 'timestamp'>) => string
  addStreamingMessage: () => string
  appendToken: (id: string, token: string) => void
  appendPreToken: (id: string, token: string) => void
  updateMessage: (id: string, updates: Partial<Omit<ChatEntry, 'id' | 'timestamp'>>) => void
  setLoading: (loading: boolean) => void
  setContextSnapshot: (snapshot: string | null) => void
  clearMessages: () => void
}

// ─── 유틸 ─────────────────────────────────────────────────────────────────────

let _idCounter = 0
function genId() {
  return `msg-${Date.now()}-${_idCounter++}`
}

// ─── 스토어 생성 ──────────────────────────────────────────────────────────────

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isLoading: false,
  contextSnapshot: null,

  addMessage: (entry) => {
    const id = genId()
    set((state) => ({
      messages: [...state.messages, { ...entry, id, timestamp: Date.now() }],
    }))
    return id
  },

  addStreamingMessage: () => {
    const id = genId()
    set((state) => ({
      messages: [
        ...state.messages,
        { id, role: 'assistant', content: '', timestamp: Date.now() },
      ],
    }))
    return id
  },

  appendToken: (id, token) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + token } : m
      ),
    })),

  appendPreToken: (id, token) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, preContent: (m.preContent ?? '') + token } : m
      ),
    })),

  updateMessage: (id, updates) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, ...updates } : m
      ),
    })),

  setLoading: (loading) => set({ isLoading: loading }),

  setContextSnapshot: (snapshot) => set({ contextSnapshot: snapshot }),

  clearMessages: () => set({ messages: [] }),
}))
