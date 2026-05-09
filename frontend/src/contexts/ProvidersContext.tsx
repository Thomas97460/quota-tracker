import { createContext, useContext } from "react"
import type { ProviderSummary, QuotaRow } from "../types"
import type { Range } from "../hooks/useDashboard"

interface ProvidersContextValue {
  providers: ProviderSummary[]
  quotas: QuotaRow[]
  range: Range
  setRange: (r: Range) => void
}

export const ProvidersContext = createContext<ProvidersContextValue>({
  providers: [],
  quotas: [],
  range: "7d",
  setRange: () => {},
})

export function useProviders(): ProvidersContextValue {
  return useContext(ProvidersContext)
}
