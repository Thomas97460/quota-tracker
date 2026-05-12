import { useCallback, useEffect, useState } from "react"
import { apiGet, apiSend } from "../api"
import type { ConfigShape, ModelPricing, ProviderId, ProviderSummary } from "../types"

interface UseConfigReturn {
  config: ConfigShape | null
  providers: ProviderSummary[]
  busy: boolean
  updateConfig: (patch: Partial<{
    sync_interval_minutes: number
    // Deprecated — kept for back-compat if callers still use old field names
    active_probe_interval_minutes: number
    passive_sync_interval_minutes: number
    pricing: Record<string, ModelPricing>
  }>) => Promise<void>
  updateProvider: (id: ProviderId, patch: { enabled?: boolean; home_path?: string }) => Promise<void>
  scanProvider: (id: ProviderId) => Promise<void>
  probeProvider: (id: ProviderId) => Promise<void>
  reload: () => void
}

export function useConfig(onUpdate?: () => void): UseConfigReturn {
  const [config, setConfig] = useState<ConfigShape | null>(null)
  const [providers, setProviders] = useState<ProviderSummary[]>([])
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)

  const reload = useCallback(() => {
    setTick((t) => t + 1)
    if (onUpdate) onUpdate()
  }, [onUpdate])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      apiGet<{ config: ConfigShape }>("/api/config"),
      apiGet<{ providers: ProviderSummary[] }>("/api/providers"),
    ])
      .then(([cfg, prov]) => {
        if (cancelled) return
        setConfig(cfg.config)
        setProviders(prov.providers)
      })
      .catch(() => {
        // silently ignore — errors are shown in the UI via null config
      })
    return () => {
      cancelled = true
    }
  }, [tick])

  const updateConfig = useCallback(
    async (patch: Partial<{
      sync_interval_minutes: number;
      active_probe_interval_minutes: number;
      passive_sync_interval_minutes: number;
      pricing: Record<string, ModelPricing>;
    }>) => {
      setBusy(true)
      try {
        const res = await apiSend<{ config: ConfigShape }>("PATCH", "/api/config", patch)
        setConfig(res.config)
      } finally {
        setBusy(false)
      }
    },
    []
  )

  const updateProvider = useCallback(
    async (id: ProviderId, patch: { enabled?: boolean; home_path?: string }) => {
      setBusy(true)
      try {
        await apiSend("PATCH", `/api/providers/${id}`, patch)
        reload()
      } finally {
        setBusy(false)
      }
    },
    [reload]
  )

  const scanProvider = useCallback(
    async (id: ProviderId) => {
      setBusy(true)
      try {
        await apiSend("POST", `/api/providers/${id}/scan`, { full_rescan: false })
        reload()
      } finally {
        setBusy(false)
      }
    },
    [reload]
  )

  const probeProvider = useCallback(
    async (id: ProviderId) => {
      setBusy(true)
      try {
        await apiSend("POST", `/api/providers/${id}/probe`, {})
        reload()
      } finally {
        setBusy(false)
      }
    },
    [reload]
  )

  return { config, providers, busy, updateConfig, updateProvider, scanProvider, probeProvider, reload }
}
