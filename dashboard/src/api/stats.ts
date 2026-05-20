import client from './client'

export interface StatusBreakdown {
  not_contacted: number
  first_message_sent: number
  in_conversation: number
  booked: number
  not_interested: number
  follow_up_sent: number
}

export interface StatsData {
  total_contacts: number
  status_breakdown: StatusBreakdown
  conversion_rate: number
  total_conversations: number
  contacts_last_24h: number
}

export const getStats = () => client.get<StatsData>('/admin/stats')
