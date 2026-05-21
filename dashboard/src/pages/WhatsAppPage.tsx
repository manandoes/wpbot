import { useEffect, useState, useCallback } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { getWhatsAppStatus, getQR, restartSession } from '../api/whatsapp'
import type { WhatsAppStatus } from '../api/whatsapp'

export default function WhatsAppPage() {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null)
  const [qr, setQr] = useState<string | null>(null)
  const [loadingQr, setLoadingQr] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [restartMsg, setRestartMsg] = useState<string | null>(null)

  const fetchStatus = useCallback(() => {
    getWhatsAppStatus().then(({ data }) => setStatus(data)).catch(() => {})
  }, [])

  const fetchQr = () => {
    setLoadingQr(true)
    getQR()
      .then(({ data }) => setQr(data.qr || null))
      .catch(() => setQr(null))
      .finally(() => setLoadingQr(false))
  }

  const handleRestartSession = () => {
    setRestarting(true)
    setRestartMsg(null)
    setQr(null)
    restartSession()
      .then(() => {
        setRestartMsg('Session wiped. Waiting for new QR code…')
        // Poll for QR after a short delay so the server has time to reinitialise
        setTimeout(() => fetchQr(), 8000)
      })
      .catch(() => setRestartMsg('Restart failed — check server logs.'))
      .finally(() => setRestarting(false))
  }

  useEffect(() => {
    fetchStatus()
    const id = setInterval(fetchStatus, 5000)
    return () => clearInterval(id)
  }, [fetchStatus])

  useEffect(() => {
    if (status && !status.ready && status.qr_available) {
      fetchQr()
    }
    if (status?.ready) {
      setQr(null)
    }
  }, [status])

  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">WhatsApp Status</h2>

      <div className="max-w-md">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          {/* Connection status */}
          <div className="flex items-center gap-3 mb-6">
            <div className={`w-3 h-3 rounded-full ${status?.ready ? 'bg-green-500' : 'bg-red-400'}`} />
            <div>
              <p className="text-base font-semibold text-gray-900">
                {status?.ready ? 'Connected' : 'Not Connected'}
              </p>
              {status?.phone_number && (
                <p className="text-xs text-gray-400 font-mono">{status.phone_number}</p>
              )}
            </div>
          </div>

          {/* QR code */}
          {!status?.ready && (
            <div className="text-center">
              {qr ? (
                <>
                  <p className="text-sm text-gray-600 mb-4">
                    Scan this QR code with WhatsApp to authenticate the bot.
                  </p>
                  <div className="inline-block p-3 bg-white border-2 border-gray-200 rounded-xl">
                    <QRCodeSVG value={qr} size={220} />
                  </div>
                  <p className="text-xs text-gray-400 mt-3">QR codes expire — refresh if it doesn't work</p>
                  <button
                    onClick={fetchQr}
                    disabled={loadingQr}
                    className="mt-3 text-indigo-600 hover:text-indigo-800 text-sm font-medium disabled:opacity-50"
                  >
                    {loadingQr ? 'Refreshing…' : '↻ Refresh QR'}
                  </button>
                </>
              ) : (
                <div className="py-8">
                  <p className="text-gray-500 text-sm mb-3">
                    {status === null ? 'Checking status…' : 'No QR code pending. The bot may be initializing.'}
                  </p>
                  <button
                    onClick={fetchQr}
                    disabled={loadingQr}
                    className="bg-indigo-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {loadingQr ? 'Loading…' : 'Load QR Code'}
                  </button>
                </div>
              )}
            </div>
          )}

          {status?.ready && (
            <div className="text-center py-4">
              <div className="text-5xl mb-3">✅</div>
              <p className="text-sm text-gray-600">
                WhatsApp Web is authenticated and running.
                <br />The bot is ready to send and receive messages.
              </p>
            </div>
          )}

          {/* Restart session — always available */}
          <div className="mt-6 border-t border-gray-100 pt-5 text-center">
            <button
              onClick={handleRestartSession}
              disabled={restarting}
              className="text-sm text-red-500 hover:text-red-700 font-medium disabled:opacity-50"
            >
              {restarting ? 'Restarting…' : '⟳ Restart / Re-link WhatsApp'}
            </button>
            <p className="text-xs text-gray-400 mt-1">Wipes the saved session and generates a fresh QR code</p>
            {restartMsg && (
              <p className="text-xs text-indigo-600 mt-2 font-medium">{restartMsg}</p>
            )}
          </div>
        </div>

        <p className="text-xs text-gray-400 mt-3 text-center">Status refreshes every 5 seconds</p>
      </div>
    </div>
  )
}
