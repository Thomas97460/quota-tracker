# Recapitulation: GitHub Copilot CLI Quota Warning Mechanism

This document summarizes the technical findings regarding the "weekly usage limit" warning popup in the GitHub Copilot CLI.

## 1. Source Location
The logic governing these warnings is contained within the compiled/minified JavaScript bundle of the CLI:
- **Path:** `~/.cache/copilot/pkg/linux-x64/1.0.40/app.js` (or equivalent version directory).

## 2. Triggering Mechanism
The warning is not triggered by a local timer or a simple loop, but is **reactive** to server-side telemetry.

- **Event:** `assistant.usage`
- **Impulse:** Whenever the CLI receives a response from the GitHub API that includes quota snapshots (typically in the `x-quota-snapshot-weekly` or `x-usage-ratelimit-weekly` headers), it emits this internal event.

## 3. Logic and Thresholds
The code responsible for monitoring these snapshots uses a fixed set of percentage thresholds.

- **Threshold Array:** `[95, 90, 75, 50]`
- **Comparison Function:** (minified as `aDo` in v1.0.40)
  1. It checks the `remainingPercentage` for both `weekly` and `session` quotas.
  2. If the used percentage (100 - remaining) exceeds one of the thresholds, it triggers a warning.
  3. It uses a `Set` to ensure the same threshold doesn't trigger multiple times in the same session.

## 4. Message Construction
The final message displayed to the user is composed of two parts:

1.  **Usage Warning:** `"You've used over {threshold}% of your {quota_type} limit."`
2.  **Reset Information:** Appended via a date formatting function (minified as `f$`).
    - It parses the `resetDate` provided by the API.
    - Format: `" Your limit resets on {Month} {Day} at {Time}."`

## 5. UI Emission
The message is passed to the UI layer via:
`t.emitEphemeral("session.warning", { warningType: "usage_limit", message: "..." })`

This causes the CLI to render the warning banner/popup in the terminal interface.

---
*Findings generated on May 7, 2026, by Gemini CLI.*



# Constats préliminaires — GitHub Copilot CLI quota / rate limit

## 1. Fichier analysé

Le mécanisme est présent dans le bundle JavaScript minifié de GitHub Copilot CLI :

```text
~/.cache/copilot/pkg/linux-x64/1.0.40/app.js

Le fichier est minifié, donc il est difficile à lire directement. Il faut plutôt extraire des blocs ciblés autour de mots-clés.

2. Les seuils de warning sont codés en dur

Le tableau suivant a été retrouvé dans app.js :

var sDo = [95, 90, 75, 50];

Cela signifie que Copilot CLI déclenche des warnings à ces seuils d’utilisation :

50 %
75 %
90 %
95 %

Le code parcourt les seuils dans l’ordre suivant :

95 → 90 → 75 → 50
3. La logique utilise le pourcentage restant

Le code ne compare pas directement le pourcentage utilisé. Il compare le champ :

remainingPercentage

La logique revient à faire :

usedPercentage = 100 - remainingPercentage

Donc :

Seuil d’alerte	Condition réelle
50 % utilisé	remainingPercentage <= 50
75 % utilisé	remainingPercentage <= 25
90 % utilisé	remainingPercentage <= 10
95 % utilisé	remainingPercentage <= 5
4. Le warning est déclenché via assistant.usage

Le warning écoute l’événement interne :

assistant.usage

Le bloc retrouvé est équivalent à :

t.on("assistant.usage", s => {
  let a = s.data.quotaSnapshots;

  if (a) {
    aDo(t, a["weekly"], r.current, "weekly", "weekly usage limit");
    aDo(t, a["session"], n.current, "session", "session usage limit");
  }
});

Donc les warnings dépendent du contenu de :

s.data.quotaSnapshots
5. Deux types de quotas sont surveillés pour les warnings

Les deux clés importantes sont :

weekly
session

Elles sont définies ainsi :

var U1r = "weekly";
var X1r = "session";

Puis utilisées ici :

aDo(t, a[U1r], ..., "weekly usage limit");
aDo(t, a[X1r], ..., "session usage limit");

Donc Copilot CLI distingue au moins :

weekly usage limit
session usage limit
6. Les variables d’environnement de debug existent

Le code contient deux variables d’environnement permettant de simuler un quota restant :

COPILOT_DEBUG_RATELIMIT_WEEKLY_REM
COPILOT_DEBUG_RATELIMIT_SESSION_REM

Elles correspondent à :

weekly  → COPILOT_DEBUG_RATELIMIT_WEEKLY_REM
session → COPILOT_DEBUG_RATELIMIT_SESSION_REM

Elles permettent de forcer localement une valeur de remainingPercentage.

Exemple :

set -x COPILOT_DEBUG_RATELIMIT_WEEKLY_REM 24
copilot

Cela simule :

24 % restant
76 % utilisé

Donc le warning attendu est celui du seuil :

75 %
7. Le message affiché est construit localement

Le message final est construit ainsi :

message: `You've used over ${c}% of your ${o}.${l}`

Avec :

c = seuil dépassé
o = "weekly usage limit" ou "session usage limit"
l = information de reset

Exemple possible :

You've used over 75% of your weekly usage limit. Your limit resets ...
8. Le reset vient de resetDate

Le code utilise :

e?.resetDate

Puis passe cette date dans une fonction de formatage :

kGa(e?.resetDate)

La fonction produit un suffixe du type :

Your limit resets ...

Donc la date de reset vient du snapshot de quota reçu.

9. Les snapshots de quota viennent des headers HTTP

Un bloc important montre que quotaSnapshots est construit à partir des headers HTTP de la réponse modèle :

let ae = {};

te.response.headers.forEach((Le, He) => {
  let ct = He.toLowerCase();

  if (ct.startsWith(Zcr)) {
    let Ae = Mcr(Le);
    Ae && (ae[ct.slice(Zcr.length)] = Ae);
  } else if (ct.startsWith(Pcr)) {
    let Ae = Mcr(Le);
    Ae && (ae[ct.slice(Pcr.length)] = Ae);
  }
});

Puis ce dictionnaire est envoyé dans l’événement :

quotaSnapshots: ae

Donc le chemin est :

réponse HTTP du modèle
→ headers HTTP
→ parsing des headers quota
→ quotaSnapshots
→ assistant.usage
→ warning
10. Les headers repérés

Les préfixes retrouvés dans le bundle sont :

x-quota-snapshot-
x-usage-ratelimit-

Cela indique que les headers réels ont probablement une forme du genre :

x-quota-snapshot-weekly
x-quota-snapshot-session
x-usage-ratelimit-weekly
x-usage-ratelimit-session

À confirmer précisément en extrayant les constantes :

Zcr
Pcr
11. Le champ quotaSnapshots est propagé dans assistant.usage

Après un appel modèle réussi, on retrouve :

this.emitEphemeral("assistant.usage", {
  model: ...,
  inputTokens: ...,
  outputTokens: ...,
  quotaSnapshots: ne.quotaSnapshots,
  copilotUsage: ...
});

Donc quotaSnapshots n’est pas seulement utilisé pour l’affichage du warning : il fait partie des métriques d’usage internes.

12. Une autre source de quota existe via copilotUser.quota_snapshots

Un autre bloc montre une récupération depuis l’objet utilisateur Copilot :

n = r.copilotUser;

if (n.quota_snapshots) {
  for (let [s, a] of Object.entries(n.quota_snapshots)) {
    a && (o[s] = jRa(a));
  }
}

Cela signifie qu’il existe aussi une source de quota côté profil utilisateur/authentification :

copilotUser.quota_snapshots
13. Transformation de quota_snapshots

La fonction suivante a été retrouvée :

function jRa(t) {
  let e = CBe(t),
      r = t.entitlement ?? e.entitlementRequests,
      n = t.percent_remaining ?? e.remainingPercentage;

  return {
    ...e,
    entitlementRequests: r,
    usedRequests: Math.round(Math.max(0, r * (1 - n / 100))),
    resetDate: t.timestamp_utc
  };
}

Elle montre que Copilot peut recevoir un format avec :

percent_remaining
entitlement
timestamp_utc

Puis le transforme en :

remainingPercentage
entitlementRequests
usedRequests
resetDate
14. Le calcul de usedRequests

La formule retrouvée est :

usedRequests = entitlementRequests × (1 - percent_remaining / 100)

Exemple :

entitlementRequests = 1200
percent_remaining = 25

Alors :

usedRequests = 1200 × (1 - 25 / 100)
usedRequests = 1200 × 0.75
usedRequests = 900

Donc 25 % restant correspond à 75 % utilisé.

15. Le footer utilise aussi les quotas

Un autre bloc gère l’affichage du quota dans le footer :

Remaining reqs.: ${a.remainingPercentage}%

Et aussi :

Monthly: ${eGr(c)}% used

La fonction associée est :

function eGr(t) {
  return Math.max(0, Math.min(100, Math.round(100 - t.remainingPercentage)));
}

Donc l’interface affiche parfois :

Remaining reqs.: X%

et parfois :

Monthly: Y% used
16. Les clés de quotas observées ne sont pas seulement weekly/session

Dans d’autres parties du code, on voit aussi :

chat
premium_interactions

Exemples issus des blocs de test UI :

quotaSnapshots: {
  premium_interactions: ...
}

ou :

quotaSnapshots: {
  chat: ...
}

Donc il y a probablement plusieurs systèmes de quota selon le type de compte ou de plan :

weekly/session
chat
premium_interactions
17. Différence probable entre deux mécanismes

Il semble y avoir au moins deux mécanismes distincts :

Warning popup

Utilise :

weekly
session

Avec seuils :

50 / 75 / 90 / 95 %
Footer / status bar

Utilise plutôt :

chat
premium_interactions

Avec affichage :

Remaining reqs.
Monthly: X% used
18. Conclusion actuelle

Le warning de limite Copilot CLI est bien localement déclenché par le client, mais à partir de données envoyées par le serveur.

Le serveur fournit le quota dans des headers HTTP ou dans copilotUser.quota_snapshots.

Le client transforme ensuite ces données en :

quotaSnapshots

Puis déclenche un warning si :

remainingPercentage <= 50, 25, 10 ou 5

ce qui correspond à :

usedPercentage >= 50, 75, 90 ou 95
19. Ce qu’il reste à trouver

Pour aller plus loin, il faut maintenant identifier précisément :

Zcr
Pcr
Mcr
CBe

Objectif :

Zcr → préfixe exact du header quota
Pcr → préfixe exact du header rate limit
Mcr → parser du contenu des headers
CBe → normalisation du snapshot quota

Cela permettra de connaître le format exact des headers, par exemple :

x-quota-snapshot-weekly: ...
x-usage-ratelimit-session: ...

et de savoir comment reconstruire les quotas sans passer par l’UI Copilot.