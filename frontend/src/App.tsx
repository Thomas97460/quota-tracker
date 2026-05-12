import React, { useCallback, useEffect, useState } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Sidebar } from "./components/layout/Sidebar"
import { ProvidersContext } from "./contexts/ProvidersContext"
import { Overview } from "./pages/Overview"
import { ProviderDetail } from "./pages/ProviderDetail"
import { Settings } from "./pages/Settings"
import type { ProviderSummary, QuotaRow } from "./types"
import type { Range } from "./hooks/useDashboard"
import { apiGet } from "./api"

export default function App(): React.JSX.Element {
  const [providers, setProviders] = useState<ProviderSummary[]>([])
  const [quotas, setQuotas] = useState<QuotaRow[]>([])
  const [range, setRange] = useState<Range>("7d")

  const fetchBaseline = useCallback(() => {
    apiGet<{ providers: ProviderSummary[] }>("/api/providers")
      .then((res) => setProviders(res.providers))
      .catch(() => {})
    apiGet<{ items: QuotaRow[] }>("/api/quotas?limit=200")
      .then((res) => setQuotas(res.items))
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetchBaseline()
    const id = setInterval(fetchBaseline, 30_000)
    return () => clearInterval(id)
  }, [fetchBaseline])

  return (
    <ProvidersContext.Provider value={{ providers, quotas, range, setRange, refresh: fetchBaseline }}>
      <BrowserRouter>
        <div className="shell">
          <Sidebar />
          <div className="main">
            <Routes>
              <Route path="/" element={<Navigate to="/overview" replace />} />
              <Route path="/overview" element={<Overview />} />
              <Route path="/provider/:id" element={<ProviderDetail />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<Navigate to="/overview" replace />} />
            </Routes>
          </div>
        </div>
      </BrowserRouter>
    </ProvidersContext.Provider>
  )
}
