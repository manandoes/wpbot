import client from './client'

export interface WhatsAppStatus {
  ready: boolean
  phone_number?: string
  qr_available?: boolean
}

export interface QRData {
  success: boolean
  qr?: string
}

export const getWhatsAppStatus = () =>
  client.get<WhatsAppStatus>('/admin/whatsapp/status')

export const getQR = () =>
  client.get<QRData>('/admin/whatsapp/qr')

export const reconnectWhatsApp = () =>
  client.post<{ success: boolean; message: string }>('/admin/whatsapp/reconnect')

