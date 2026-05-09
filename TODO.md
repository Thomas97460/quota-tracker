# Quota Tracker — TODO

## User Requests
- [x] Top projects: Calculate share based on all projects, not just visible ones on the current page. (Fixed: Backend now returns global total tokens for correct percentage calculation).
- [x] Top projects: Group all projects named "repo" (from Gemini) into a single project. (Fixed: SQL now groups by name 'repo' or path ending in '/repo').
- [x] Recent sessions: Change pagination to 5 items per page (currently 10).
- [x] Charts: Fix Y-axis clipping (e.g., '1' in '100%' is cut off). Ensure enough left margin.
- [x] Charts: Add a visual switch to toggle between "Tokens" and "Estimated Cost ($)" on the Y-axis for both `Tokens over time` (Overview & Provider pages).
- [x] Settings: Redesign provider configuration to be more compact and elegant, respecting the overall UI.
- [x] Settings: In "Model Pricing" table, explicitly indicate that values are in `$` (respecting UX).
- [x] Overview: Remove the standalone "Tokens" KPI card.
- [x] Overview: Rename "Per provider" card to "Tokens".
- [x] Overview: In the new "Tokens" card, display total tokens and total estimated cost (in dollars) side-by-side. Include an info tooltip explaining it's an estimated cost. Make the pricing larger and not grayed out. Keep per-provider costs next to the provider bars.
- [x] Gemini Quotas: Attempt to display used/total requests (like Copilot), if the API data permits. (Verified: Google's `retrieveUserQuota` API only returns a relative `remainingFraction`, not absolute counts. Sticking to percentage display).
- [x] Sidebar/Navbar Quotas: The progress bar should only reflect the worst percentage among the *hero* quotas (the ones visible in the top quota cards), ignoring hidden/secondary quotas like "Claude Design".
- [x] UI Pricing format: Remove badge/label styling for prices. Display them as `(<green_price>)` on the same level as other info (e.g., in Token Types).
- [x] Provider Detail Layout: Put "Token types" and "Top projects" side-by-side in a 2-column grid, as they currently take up too much vertical space.
- [x] Model Pricing: Added missing Codex models (gpt-5-codex, gpt-5.1-*, gpt-5.2, etc.) to default pricing.
- [x] Share Calculation: Fixed "Share %" scaling to thousands (it now uses global provider totals as denominator).
