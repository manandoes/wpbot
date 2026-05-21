import client from './client'

export interface BulkContact {
  phone_number: string
  name?: string
}

export interface BulkSendResultItem {
  phone_number: string
  success: boolean
  error?: string
}

export interface BulkSendResult {
  total: number
  sent: number
  failed: number
  results: BulkSendResultItem[]
}

export function sendSingleMessage(phone_number: string, message: string) {
  return client.post<{ success: boolean; phone_number: string }>('/admin/send-message', {
    phone_number,
    message,
  })
}

export function sendBulkMessages(contacts: BulkContact[], message: string) {
  return client.post<BulkSendResult>('/admin/bulk-send', { contacts, message })
}

export function updateContactStatus(phone_number: string, status: string) {
  return client.patch<{ success: boolean; phone_number: string; status: string }>(
    `/admin/contacts/${phone_number}/status`,
    { status }
  )
}
