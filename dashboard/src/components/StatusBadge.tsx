const COLOR: Record<string, string> = {
  not_contacted: 'bg-gray-100 text-gray-600',
  first_message_sent: 'bg-blue-100 text-blue-700',
  in_conversation: 'bg-indigo-100 text-indigo-700',
  follow_up_sent: 'bg-yellow-100 text-yellow-700',
  booked: 'bg-green-100 text-green-700',
  not_interested: 'bg-red-100 text-red-700',
}

const LABEL: Record<string, string> = {
  not_contacted: 'Not Contacted',
  first_message_sent: 'Msg Sent',
  in_conversation: 'In Conversation',
  follow_up_sent: 'Follow-up Sent',
  booked: 'Booked',
  not_interested: 'Not Interested',
}

export default function StatusBadge({ status }: { status: string }) {
  const cls = COLOR[status] ?? 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {LABEL[status] ?? status}
    </span>
  )
}
