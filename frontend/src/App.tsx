import React, { useEffect, useState } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Sidebar } from "./components/layout/Sidebar"
import { ProvidersContext } from "./contexts/ProvidersContext"
import { Overview } from "./pages/Overview"
import { ProviderDetail } from "./pages/ProviderDetail"
import { Settings } from "./pages/Settings"
import type { ProviderSummary } from "./types"
import { apiGet } from "./api"

function Layout(): React.JSX.Element {
  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar />
      <main className="flex-1 overflow-y-auto min-w-0">
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/provider/:id" element={<ProviderDetail />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App(): React.JSX.Element {
  const [providers, setProviders] = useState<ProviderSummary[]>([])

  useEffect(() => {
    apiGet<{ providers: ProviderSummary[] }>("/api/providers")
      .then((res) => setProviders(res.providers))
      .catch(() => {
        // providers context starts empty — sidebar degrades gracefully
      })
  }, [])

  return (
    <ProvidersContext.Provider value={{ providers }}>
      <BrowserRouter>
        <Layout />
      </BrowserRouter>
    </ProvidersContext.Provider>
  )
}
