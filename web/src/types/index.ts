// ---------- API response types (camelCase, matching api) ----------

export interface CaptchaResponse {
  captchaId: string
  imageBase64: string
}

export interface LoginResponse {
  userId: string
  email: string
  isActive: boolean
  sessionToken: string
  apiKey?: string
}

export interface RegisterResponse {
  userId: string
  email: string
  isActive: boolean
  message: string
}

export interface LogoutResponse {
  detail: string
}

export interface MeResponse {
  userId: string
  email: string
  isActive: boolean
}

export interface ChangePasswordRequest {
  oldPassword?: string
  newPassword?: string
}

export interface ChangePasswordResponse {
  detail: string
}

// ---------- API Key management ----------

export interface KeyCreateResponse {
  keyId: string
  keyName: string
  keyValue: string
  isEnabled: boolean
  createdAt: string
}

export interface KeySummary {
  keyId: string
  keyName: string
  keyValueMasked: string
  isEnabled: boolean
  isSystem: boolean
  createdAt: string
}

export interface KeyListResponse {
  keys: KeySummary[]
}

export interface KeyUpdateResponse {
  keyId: string
  keyName: string
  isEnabled: boolean
}

export interface KeyDeleteResponse {
  detail: string
  keyId: string
}

export interface KeyRefreshResponse {
  keyId: string
  keyName: string
  keyValue: string
}

// ---------- Project ----------

export interface Project {
  projectId: string
  userId: string
  projectName: string
  projectDescription: string | null
}

export interface FieldDefinition {
  fieldName: string
  fieldType: 'text' | 'number' | 'date' | 'enum' | 'link' | 'assignee'
  fieldDescription?: string
  enumValues?: string[]
}

export interface ProjectSchema {
  schemaId: string
  projectId: string
  fieldsDefinition: FieldDefinition[]
  schemaVersion: number
}

export interface Todo {
  todoId: string
  projectId: string
  parentId: string | null
  content: Record<string, any>
  isCompleted: boolean
  updatedAt: string
  version: number
  schemaVersion: number
}

export interface TodoDeleteResult {
  detail: string
  todoId: string
  deletedCount: number
}

// ---------- Tree node (augmented Todo for UI) ----------

export interface TodoTreeNode extends Todo {
  children: TodoTreeNode[]
  expanded: boolean
}

// ---------- Webhook ----------

export interface WebhookRule {
  ruleId: string
  projectId: string
  eventType: 'Create' | 'Update' | 'Delete'
  targetField: string
  webhookUrl: string
}

export interface WebhookLogEntry {
  taskId: string
  ruleId: string
  todoId: string
  webhookUrl: string
  eventType: string
  payload: Record<string, any>
  status: 'pending' | 'success' | 'failed'
  retryCount: number
  nextRetryAt: string | null
  lastError: string | null
  createdAt: string
}

export interface WebhookLogsResponse {
  total: number
  logs: WebhookLogEntry[]
}

export interface WebhookRetryResponse {
  detail: string
  taskId: string
  status: string
  retryCount: number
}

// ---------- Notification Rules ----------

export interface NotificationRule {
  ruleId: string
  userId: string
  eventType: string
  enabled: boolean
  createdAt: string
}


// ---------- Project Members ----------

export interface ProjectMember {
  memberId: string
  projectId: string
  agentId: string
  displayName?: string
  description?: string
  createdAt: string
}

export interface MemberRemoveResult {
  detail: string
  memberId: string
}