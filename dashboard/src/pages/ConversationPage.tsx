import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getConversation } from '../api/contacts'
import type { ConversationData } from '../api/contacts'
import StatusBadge from '../components/StatusBadge'

export default function ConversationPage() {
  const { phone } = useParams<{ phone: string }>()
  const [data, setData] = useState<ConversationData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!phone) return
    getConversation(phone)
      .then(({ data }) => setData(data))
      .catch(() => setError('Failed to load conversation'))
      .finally(() => setLoading(false))
  }, [phone])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [data])

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-4">
        <button
          onClick={() => navigate('/contacts')}
          className="text-gray-500 hover:text-gray-700 text-sm"
        >
          ← Back
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h2 className="text-base font-semibold text-gray-900">
              {data?.contact_name || phone}
            </h2>
            {data && <StatusBadge status={data.contact_status} />}
          </div>
          <p className="text-xs text-gray-400 font-mono">{phone}</p>
        </div>
        {data && (
          <span className="text-xs text-gray-400">
            {data.messages.length} message{data.messages.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3"
        style={{ backgroundImage: 'radial-gradient(circle, #e5e7eb 1px, transparent 1px)', backgroundSize: '20px 20px' }}
      >
        {loading && <p className="text-center text-gray-400 mt-8">Loading…</p>}
        {error && <p className="text-center text-red-500 mt-8">{error}</p>}
        {data?.messages.length === 0 && (
          <p className="text-center text-gray-400 mt-8">No messages yet</p>
        )}
        {data?.messages.map((msg) => {
          const isUser = msg.role === 'user'
          return (
            <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-xs lg:max-w-md px-4 py-2.5 rounded-2xl shadow-sm ${
                  isUser
                    ? 'bg-green-500 text-white rounded-br-sm'
                    : 'bg-white text-gray-800 rounded-bl-sm border border-gray-200'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap break-words">{msg.message}</p>
                <p className={`text-xs mt-1 ${isUser ? 'text-green-100' : 'text-gray-400'} text-right`}>
                  {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
