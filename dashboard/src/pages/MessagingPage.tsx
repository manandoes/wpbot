import { useState } from 'react'
import { sendSingleMessage, sendBulkMessages } from '../api/messaging'
import type { BulkContact, BulkSendResultItem } from '../api/messaging'

type Tab = 'single' | 'bulk'

const ALL_STATUSES = [
  'not_contacted', 'first_message_sent', 'in_conversation',
  'follow_up_sent', 'booked', 'not_interested',
]

function parseContactsText(raw: string): BulkContact[] {
  return raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [phone, name] = line.split(',').map((s) => s.trim())
      return { phone_number: phone, name: name || undefined }
    })
    .filter((c) => c.phone_number)
}

export default function MessagingPage() {
  const [tab, setTab] = useState<Tab>('single')

  // Single message state
  const [singlePhone, setSinglePhone] = useState('')
  const [singleMessage, setSingleMessage] = useState('')
  const [singleLoading, setSingleLoading] = useState(false)
  const [singleToast, setSingleToast] = useState<{ ok: boolean; text: string } | null>(null)

  // Bulk send state
  const [bulkContacts, setBulkContacts] = useState('')
  const [bulkMessage, setBulkMessage] = useState('')
  const [bulkLoading, setBulkLoading] = useState(false)
  const [bulkResults, setBulkResults] = useState<BulkSendResultItem[] | null>(null)
  const [bulkStats, setBulkStats] = useState<{ total: number; sent: number; failed: number } | null>(null)

  const parsedContacts = parseContactsText(bulkContacts)

  const handleSingleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    setSingleLoading(true)
    setSingleToast(null)
    try {
      await sendSingleMessage(singlePhone.trim(), singleMessage.trim())
      setSingleToast({ ok: true, text: `Message sent to ${singlePhone.trim()}` })
      setSingleMessage('')
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? 'Failed to send message'
      setSingleToast({ ok: false, text: detail })
    } finally {
      setSingleLoading(false)
    }
  }

  const handleBulkSend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (parsedContacts.length === 0) return
    setBulkLoading(true)
    setBulkResults(null)
    setBulkStats(null)
    try {
      const { data } = await sendBulkMessages(parsedContacts, bulkMessage.trim())
      setBulkResults(data.results)
      setBulkStats({ total: data.total, sent: data.sent, failed: data.failed })
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? 'Bulk send failed'
      setBulkStats({ total: parsedContacts.length, sent: 0, failed: parsedContacts.length })
      setBulkResults(
        parsedContacts.map((c) => ({ phone_number: c.phone_number, success: false, error: detail }))
      )
    } finally {
      setBulkLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-3xl">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Messaging</h2>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit mb-6">
        {(['single', 'bulk'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {t === 'single' ? 'Single Message' : 'Bulk Send'}
          </button>
        ))}
      </div>

      {/* Single Message */}
      {tab === 'single' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">Send a Single Message</h3>
          <form onSubmit={handleSingleSend} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Phone Number
              </label>
              <input
                type="text"
                value={singlePhone}
                onChange={(e) => setSinglePhone(e.target.value)}
                placeholder="e.g. 919876543210"
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <p className="mt-1 text-xs text-gray-400">Include country code, no + or spaces</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Message</label>
              <textarea
                value={singleMessage}
                onChange={(e) => setSingleMessage(e.target.value)}
                placeholder="Type your message…"
                required
                rows={4}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              />
            </div>
            {singleToast && (
              <div
                className={`rounded-lg px-4 py-3 text-sm ${
                  singleToast.ok
                    ? 'bg-green-50 text-green-700 border border-green-200'
                    : 'bg-red-50 text-red-700 border border-red-200'
                }`}
              >
                {singleToast.ok ? '✓ ' : '✗ '}{singleToast.text}
              </div>
            )}
            <button
              type="submit"
              disabled={singleLoading || !singlePhone.trim() || !singleMessage.trim()}
              className="bg-indigo-600 text-white rounded-lg px-5 py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {singleLoading ? 'Sending…' : 'Send Message'}
            </button>
          </form>
        </div>
      )}

      {/* Bulk Send */}
      {tab === 'bulk' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 space-y-5">
          <h3 className="text-base font-semibold text-gray-900">Bulk Send</h3>
          <form onSubmit={handleBulkSend} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Contact List
              </label>
              <textarea
                value={bulkContacts}
                onChange={(e) => setBulkContacts(e.target.value)}
                placeholder={`One per line:\n919876543210\n919876543211,John\n919876543212,Priya`}
                rows={8}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
              />
              <p className="mt-1 text-xs text-gray-400">
                Format: <code className="bg-gray-100 px-1 rounded">phone_number</code> or{' '}
                <code className="bg-gray-100 px-1 rounded">phone_number,name</code> — one per line.{' '}
                {parsedContacts.length > 0 && (
                  <span className="text-indigo-600 font-medium">
                    {parsedContacts.length} contact{parsedContacts.length !== 1 ? 's' : ''} parsed
                  </span>
                )}
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Message</label>
              <textarea
                value={bulkMessage}
                onChange={(e) => setBulkMessage(e.target.value)}
                placeholder="Type your message…"
                required
                rows={4}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              />
            </div>
            <button
              type="submit"
              disabled={bulkLoading || parsedContacts.length === 0 || !bulkMessage.trim()}
              className="bg-indigo-600 text-white rounded-lg px-5 py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {bulkLoading
                ? `Sending… (${parsedContacts.length} contacts)`
                : `Send to ${parsedContacts.length} Contact${parsedContacts.length !== 1 ? 's' : ''}`}
            </button>
          </form>

          {/* Results */}
          {bulkStats && (
            <div className="space-y-3">
              <div className="flex gap-4">
                <div className="flex-1 bg-gray-50 rounded-lg p-3 text-center">
                  <div className="text-lg font-bold text-gray-900">{bulkStats.total}</div>
                  <div className="text-xs text-gray-500">Total</div>
                </div>
                <div className="flex-1 bg-green-50 rounded-lg p-3 text-center">
                  <div className="text-lg font-bold text-green-700">{bulkStats.sent}</div>
                  <div className="text-xs text-green-600">Sent</div>
                </div>
                <div className="flex-1 bg-red-50 rounded-lg p-3 text-center">
                  <div className="text-lg font-bold text-red-700">{bulkStats.failed}</div>
                  <div className="text-xs text-red-600">Failed</div>
                </div>
              </div>

              {bulkResults && bulkResults.length > 0 && (
                <div className="rounded-lg border border-gray-200 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b border-gray-200">
                      <tr>
                        <th className="text-left px-4 py-2 text-xs font-semibold text-gray-500 uppercase">Phone</th>
                        <th className="text-left px-4 py-2 text-xs font-semibold text-gray-500 uppercase">Result</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {bulkResults.map((r) => (
                        <tr key={r.phone_number} className="hover:bg-gray-50">
                          <td className="px-4 py-2 font-mono text-xs text-gray-700">{r.phone_number}</td>
                          <td className="px-4 py-2">
                            {r.success ? (
                              <span className="text-green-600 font-medium">✓ Sent</span>
                            ) : (
                              <span className="text-red-600">✗ {r.error || 'Failed'}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
