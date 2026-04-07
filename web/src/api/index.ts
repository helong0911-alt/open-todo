/**
 * Axios-based API client for Open-Todo (OTD).
 * All mutations use POST with IDs in the request body (never in URLs).
 * All payloads and responses use camelCase.
 *
 * Web auth uses X-SESSION-TOKEN (session-based login).
 * Programmatic / resource routes still use X-API-KEY on the server side,
 * but the web client always sends X-SESSION-TOKEN for its own requests —
 * resource routes are accessed via X-API-KEY which is irrelevant to the
 * web client (users manage API keys through the key management UI).
 *
 * NOTE: The API resource routes (projects, todos, schemas, webhooks,
 * automation, mcp) require X-API-KEY. The web client must prompt users to
 * create an API key after login and store it for resource requests.
 */
import axios from 'axios'
import type {
  CaptchaResponse,
  LoginResponse,
  RegisterResponse,
  LogoutResponse,
  MeResponse,
  ChangePasswordResponse,
  KeyCreateResponse,
  KeyListResponse,
  KeyUpdateResponse,
  KeyDeleteResponse,
  KeyRefreshResponse,
  Project,
  ProjectSchema,
  FieldDefinition,
  Todo,
  TodoDeleteResult,
  WebhookRule,
  WebhookLogsResponse,
  WebhookRetryResponse,
  NotificationRule,
  ProjectMember,
  MemberRemoveResult,
} from '@/types'

const http = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// ---------------------------------------------------------------------------
// Global 401 interceptor callback
// ---------------------------------------------------------------------------
let _onUnauthorized: (() => void) | null = null

/**
 * Register a callback that fires when any API response returns 401.
 * App.vue uses this to clear tokens and show the login overlay.
 */
export function onUnauthorized(cb: () => void) {
  _onUnauthorized = cb
}

// Attach session token AND api key from localStorage on every request
http.interceptors.request.use((config) => {
  const sessionToken = localStorage.getItem('otd_session_token')
  if (sessionToken) {
    config.headers['X-SESSION-TOKEN'] = sessionToken
  }
  const apiKey = localStorage.getItem('otd_api_key')
  if (apiKey) {
    config.headers['X-API-KEY'] = apiKey
  }
  return config
})

// Global 401 response interceptor — trigger forced logout
http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && _onUnauthorized) {
      _onUnauthorized()
    }
    return Promise.reject(error)
  },
)

// ---- Auth ----
export const authCaptcha = () =>
  http.post<CaptchaResponse>('/auth/captcha').then((r) => r.data)

export const authLogin = (email: string, password: string, captchaId: string, captchaCode: string) =>
  http.post<LoginResponse>('/auth/login', { email, password, captchaId, captchaCode }).then((r) => r.data)

export const authRegister = (email: string, password: string, captchaId: string, captchaCode: string) =>
  http.post<RegisterResponse>('/auth/register', { email, password, captchaId, captchaCode }).then((r) => r.data)

export const authLogout = (sessionToken: string) =>
  http.post<LogoutResponse>('/auth/logout', { sessionToken }).then((r) => r.data)

export const authVerify = (token: string) =>
  http.get<{ userId: string; email: string; isActive: boolean }>('/auth/verify', { params: { token } }).then((r) => r.data)

export const authMe = () =>
  http.post<MeResponse>('/auth/me').then((r) => r.data)

export const authChangePassword = (oldPassword?: string, newPassword?: string) =>
  http.post<ChangePasswordResponse>('/auth/change-password', { oldPassword, newPassword }).then((r) => r.data)

// ---- API Keys ----
export const keysCreate = (keyName: string = 'Default') =>
  http.post<KeyCreateResponse>('/keys/create', { keyName }).then((r) => r.data)

export const keysList = () =>
  http.post<KeyListResponse>('/keys/list').then((r) => r.data)

export const keysUpdate = (keyId: string, opts: { keyName?: string; isEnabled?: boolean }) =>
  http.post<KeyUpdateResponse>('/keys/update', { keyId, ...opts }).then((r) => r.data)

export const keysDelete = (keyId: string) =>
  http.post<KeyDeleteResponse>('/keys/delete', { keyId }).then((r) => r.data)

export const keysRefresh = (keyId: string) =>
  http.post<KeyRefreshResponse>('/keys/refresh', { keyId }).then((r) => r.data)

// ---- Projects ----
export const projectsList = () =>
  http.get<Project[]>('/projects').then((r) => r.data)

export const projectsCreate = (
  projectName: string,
  projectDescription?: string,
  projectDirectory?: string,
  gitUrl?: string
) =>
  http.post<Project>('/projects/create', { projectName, projectDescription, projectDirectory, gitUrl }).then((r) => r.data)

export const projectsUpdate = (
  projectId: string,
  data: {
    projectName?: string
    projectDescription?: string
    projectDirectory?: string
    gitUrl?: string
  }
) =>
  http.post<Project>('/projects/update', { projectId, ...data }).then((r) => r.data)

// ---- Schema ----
export const schemaGet = (projectId: string) =>
  http.post<ProjectSchema>('/projects/schema/get', { projectId }).then((r) => r.data)

export const schemaUpdate = (projectId: string, fieldsDefinition: FieldDefinition[]) =>
  http.post<ProjectSchema>('/projects/schema/update', { projectId, fieldsDefinition }).then((r) => r.data)

// ---- Todos ----
export const todosList = (projectId: string) =>
  http.post<Todo[]>('/todos/list', { projectId }).then((r) => r.data)

export const todosCreate = (projectId: string, content: Record<string, any>, parentId?: string) =>
  http.post<Todo>('/todos/create', { projectId, parentId: parentId ?? null, content }).then((r) => r.data)

export const todosUpdate = (
  todoId: string,
  content: Record<string, any>,
  opts?: { isCompleted?: boolean; version?: number }
) =>
  http.post<Todo>('/todos/update', { todoId, content, ...opts }).then((r) => r.data)

export const todosDelete = (todoId: string) =>
  http.post<TodoDeleteResult>('/todos/delete', { todoId }).then((r) => r.data)

// ---- Webhooks ----
export const webhooksCreate = (
  projectId: string,
  eventType: string,
  webhookUrl: string,
  targetField: string = '*'
) =>
  http.post<WebhookRule>('/webhooks/create', { projectId, eventType, targetField, webhookUrl }).then((r) => r.data)

export const webhooksList = (projectId: string) =>
  http.post<WebhookRule[]>('/webhooks/list', { projectId }).then((r) => r.data)

// ---- Automation ----
export const webhookLogs = (projectId: string, todoId?: string) =>
  http.post<WebhookLogsResponse>('/automation/webhook/logs', { projectId, todoId: todoId ?? null }).then((r) => r.data)

export const webhookRetry = (taskId: string) =>
  http.post<WebhookRetryResponse>('/automation/webhook/retry', { taskId }).then((r) => r.data)

// ---- Notifications ----
export const notificationRulesCreate = (eventType: string) =>
  http.post<NotificationRule>('/notifications/rules/create', { eventType }).then((r) => r.data)

export const notificationRulesList = () =>
  http.post<NotificationRule[]>('/notifications/rules/list').then((r) => r.data)

export const notificationRulesDelete = (ruleId: string) =>
  http.post<{ detail: string; ruleId: string }>('/notifications/rules/delete', { ruleId }).then((r) => r.data)


// ---- Members ----
export const membersList = (projectId: string) =>
  http.post<ProjectMember[]>('/members/list', { projectId }).then((r) => r.data)

export const membersAdd = (
  projectId: string,
  agentId: string,
  displayName?: string,
  description?: string
) =>
  http.post<ProjectMember>('/members/add', { projectId, agentId, displayName, description }).then((r) => r.data)

export const membersRemove = (memberId: string) =>
  http.post<MemberRemoveResult>('/members/remove', { memberId }).then((r) => r.data)
