import client from './client'

export interface ContactItem {
  id: number
  name: string | null
  phone_number: string
  status: string
  created_at: string
  last_contacted_at: string
}

export interface ContactsData {
  total: number
  page: number
  page_size: number
  contacts: ContactItem[]
}

export interface MessageItem {
  id: number
  role: string
  message: string
  timestamp: string
}

export interface ConversationData {
  phone_number: string
  contact_name: string | null
  contact_status: string
  messages: MessageItem[]
}

export const getContacts = (params: {
  page?: number
  page_size?: number
  search?: string
  status?: string
}) => client.get<ContactsData>('/admin/contacts', { params })

export const getConversation = (phone: string) =>
  client.get<ConversationData>(`/admin/contacts/${phone}/conversation`)
