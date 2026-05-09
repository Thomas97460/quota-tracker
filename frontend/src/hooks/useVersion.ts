import { useCallback, useEffect, useState } from "react"

interface VersionInfo {
  current: string
  latest: string | null
  update_available: boolean
}

interface UseVersionResult {
  current: string
  updateAvailable: boolean
  latestVersion: string | null
  updating: boolean
  triggerUpdate: () => Promise<void>
}

export function useVersion(): UseVersionResult {
  const [info, setInfo] = useState<VersionInfo>({ current: "", latest: null, update_available: false })
  const [updating, setUpdating] = useState(false)

  const fetchVersion = useCallback(async () => {
    try {
      const r = await fetch("/api/version")
      if (r.ok) setInfo(await r.json())
    } catch {
      // ignore — offline or dev mode
    }
  }, [])

  useEffect(() => {
    fetchVersion()
    const id = setInterval(fetchVersion, 30 * 60 * 1000)
    return () => clearInterval(id)
  }, [fetchVersion])

  const triggerUpdate = useCallback(async () => {
    setUpdating(true)
    try {
      await fetch("/api/update", { method: "POST" })
    } catch {
      // ignore — service will restart
    }
    // Poll until the service comes back up (max 90s), then reload
    const deadline = Date.now() + 90_000
    const poll = async () => {
      await new Promise((r) => setTimeout(r, 3000))
      try {
        const r = await fetch("/api/version")
        if (r.ok) { window.location.reload(); return }
      } catch { /* still restarting */ }
      if (Date.now() < deadline) poll()
      else window.location.reload()
    }
    poll()
  }, [])

  return {
    current: info.current,
    updateAvailable: info.update_available,
    latestVersion: info.latest,
    updating,
    triggerUpdate,
  }
}
