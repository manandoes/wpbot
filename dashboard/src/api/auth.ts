import client from './client'

export const login = (password: string) =>
  client.post<{ access_token: string; token_type: string }>('/admin/login', { password })
