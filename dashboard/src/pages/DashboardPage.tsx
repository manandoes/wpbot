import { useEffect, useState } from 'react'
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import { getStats } from '../api/stats'
import type { StatsData } from '../api/stats'
import StatCard from '../components/StatCard'

const STATUS_COLORS: Record<string, string> = {
  not_contacted: '#94a3b8',
  first_message_sent: '#60a5fa',
  in_conversation: '#818cf8',
  follow_up_sent: '#fbbf24',
  booked: '#34d399',
  not_interested: '#f87171',
}

const FUNNEL_ORDER = [
  'not_contacted',
  'first_message_sent',
  'in_conversation',
  'follow_up_sent',
  'booked',
  'not_interested',
]

const FUNNEL_LABELS: Record<string, string> = {
  not_contacted: 'Not Contacted',
  first_message_sent: 'Msg Sent',
  in_conversation: 'In Conv.',
  follow_up_sent: 'Follow-up',
  booked: 'Booked',
  not_interested: 'Not Int.',
}

export default function DashboardPage() {
  const [stats, setStats] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    getStats()
      .then(({ data }) => setStats(data))
      .catch(() => setError('Failed to load stats'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-8 text-gray-500">Loading stats…</div>
  if (error || !stats) return <div className="p-8 text-red-500">{error || 'No data'}</div>

  const pieData = Object.entries(stats.status_breakdown).map(([key, val]) => ({
    name: FUNNEL_LABELS[key] ?? key,
    value: val,
    fill: STATUS_COLORS[key] ?? '#94a3b8',
  })).filter(d => d.value > 0)

  const barData = FUNNEL_ORDER.map((key) => ({
    name: FUNNEL_LABELS[key],
    count: stats.status_breakdown[key as keyof typeof stats.status_breakdown],
    fill: STATUS_COLORS[key],
  }))

  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Overview</h2>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Contacts" value={stats.total_contacts} />
        <StatCard
          label="Booked"
          value={stats.status_breakdown.booked}
          color="text-green-600"
        />
        <StatCard
          label="Conversion Rate"
          value={`${stats.conversion_rate}%`}
          color="text-indigo-600"
        />
        <StatCard
          label="Active Last 24h"
          value={stats.contacts_last_24h}
          color="text-blue-600"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pie chart */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">Status Breakdown</h3>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={pieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label={({ name, percent }) =>
                  (percent ?? 0) > 0.05 ? `${name} ${((percent ?? 0) * 100).toFixed(0)}%` : ''
                }
              >
                {pieData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Bar / funnel chart */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">Contact Funnel</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={barData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {barData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
