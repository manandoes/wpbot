import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getContacts } from '../api/contacts'
import type { ContactItem } from '../api/contacts'
import { updateContactStatus } from '../api/messaging'
import StatusBadge from '../components/StatusBadge'

const STATUSES = [
  '', 'not_contacted', 'first_message_sent', 'in_conversation',
  'follow_up_sent', 'booked', 'not_interested',
]

const STATUS_LABELS: Record<string, string> = {
  '': 'All Statuses',
  not_contacted: 'Not Contacted',
  first_message_sent: 'Msg Sent',
  in_conversation: 'In Conversation',
  follow_up_sent: 'Follow-up Sent',
  booked: 'Booked',
  not_interested: 'Not Interested',
}

const PAGE_SIZE = 20

export default function ContactsPage() {
  const [contacts, setContacts] = useState<ContactItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [updatingStatus, setUpdatingStatus] = useState<Record<number, boolean>>({})
  const navigate = useNavigate()

  const fetchContacts = (p = page, s = search, st = status) => {
    setLoading(true)
    getContacts({ page: p, page_size: PAGE_SIZE, search: s || undefined, status: st || undefined })
      .then(({ data }) => {
        setContacts(data.contacts)
        setTotal(data.total)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchContacts(1, search, status) }, [])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    fetchContacts(1, search, status)
  }

  const handleStatusChange = (s: string) => {
    setStatus(s)
    setPage(1)
    fetchContacts(1, search, s)
  }

  const handleStatusUpdate = async (contact: ContactItem, newStatus: string) => {
    if (newStatus === contact.status) return
    setUpdatingStatus((prev) => ({ ...prev, [contact.id]: true }))
    try {
      await updateContactStatus(contact.phone_number, newStatus)
      setContacts((prev) =>
        prev.map((c) => (c.id === contact.id ? { ...c, status: newStatus } : c))
      )
    } catch {
      // silently ignore; the select will revert since we didn't update state
    } finally {
      setUpdatingStatus((prev) => ({ ...prev, [contact.id]: false }))
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)

  const changePage = (p: number) => {
    setPage(p)
    fetchContacts(p, search, status)
  }

  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Contacts</h2>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name or phone…"
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 w-60"
          />
          <button
            type="submit"
            className="bg-indigo-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-indigo-700"
          >
            Search
          </button>
        </form>
        <select
          value={status}
          onChange={(e) => handleStatusChange(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
        <span className="flex items-center text-sm text-gray-500">
          {total} contact{total !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading…</div>
        ) : contacts.length === 0 ? (
          <div className="p-8 text-center text-gray-400">No contacts found</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Name</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Phone</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Last Active</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {contacts.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{c.name || '—'}</td>
                  <td className="px-4 py-3 text-gray-600 font-mono text-xs">{c.phone_number}</td>
                  <td className="px-4 py-3">
                    <select
                      value={c.status}
                      disabled={updatingStatus[c.id]}
                      onChange={(e) => handleStatusUpdate(c, e.target.value)}
                      className="border border-gray-200 rounded-md px-2 py-1 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-50"
                    >
                      {STATUSES.filter(Boolean).map((s) => (
                        <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {new Date(c.last_contacted_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => navigate(`/contacts/${c.phone_number}/conversation`)}
                      className="text-indigo-600 hover:text-indigo-800 text-xs font-medium"
                    >
                      View Chat →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-5">
          <button
            onClick={() => changePage(page - 1)}
            disabled={page === 1}
            className="px-3 py-1.5 rounded-lg border border-gray-300 text-sm disabled:opacity-40 hover:bg-gray-50"
          >
            ← Prev
          </button>
          <span className="text-sm text-gray-600">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => changePage(page + 1)}
            disabled={page === totalPages}
            className="px-3 py-1.5 rounded-lg border border-gray-300 text-sm disabled:opacity-40 hover:bg-gray-50"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}
