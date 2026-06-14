# ha-orphaned-entities

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/Noack1978/ha-orphaned-entities.svg)](https://github.com/Noack1978/ha-orphaned-entities/releases)
[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/Noack1978/ha-orphaned-entities/releases/tag/v1.1.0)

Findet verwaiste oder dauerhaft inaktive Entitäten in Home Assistant und ermöglicht es, diese direkt per Lovelace-Karte zu **deaktivieren**, **löschen** oder für zukünftige Scans zu **ignorieren**.

## Features

- 🔍 Erkennt Entitäten ohne Gerät, ohne Integration oder dauerhaft im `unavailable`/`unknown`-Status
- ✅ Checkbox-Auswahl einzelner oder aller Entitäten
- ⏸ Deaktivieren (reversibel, bleibt in der Registry)
- 🗑 Löschen (mit Bestätigungs-Dialog)
- 👁 Ignorieren (wird beim nächsten Scan übersprungen, persistent gespeichert)
- 🔄 Manueller Rescan per Button
- 🔎 Suche & Sortierung nach Domain, Name oder Status
- ⚙️ Konfigurierbar: Scan-Intervall, Inaktivitätsschwelle, ignorierte Domains

### Hinweis zu YAML-Helfern

Per **YAML** (`configuration.yaml`) konfigurierte Helfer wie `template`, `statistics`,
`filter`, `min_max`, `utility_meter`, `history_stats`, `trend`, `threshold`, `tod`,
`generic_hygrostat`/`generic_thermostat`, `derivative`/`integration` (Riemann) und
`bayesian` werden **nicht** als verwaist markiert, auch wenn sie kein Gerät und keinen
Config-Entry besitzen – das ist bei diesen Plattformen normal.

Per **UI** angelegte Helfer (Einstellungen → Geräte & Dienste → Helfer) sind ohnehin
automatisch geschützt, da sie immer einen Config-Entry besitzen.

### Hinweis zu Geräte-Sub-Entitäten

Viele Geräte (z.B. Zigbee-Steckdosen) bieten Sub-Entitäten wie „Child lock" an,
die das jeweilige Gerät nie meldet und die dauerhaft im Status `unknown` bleiben –
das ist normal und kein Zeichen von Verwaisung. Solche Entitäten werden **nur**
als „Inaktiv" markiert, wenn **kein** anderes Entity desselben Geräts innerhalb
der Inaktivitätsschwelle Aktivität zeigt. Ist das Gerät also über andere Entitäten
aktiv, wird die einzelne `unknown`-Sub-Entität nicht angezeigt.

## Installation

### Via HACS (empfohlen)

1. HACS → Integrationen → ⋮ → Benutzerdefiniertes Repository hinzufügen
2. URL: `https://github.com/Noack1978/ha-orphaned-entities`
3. Kategorie: Integration
4. Integration installieren & HA neu starten

### Manuell

Ordner `custom_components/orphaned_entities/` in dein HA-Konfigurationsverzeichnis kopieren.

## Einrichtung

1. Einstellungen → Geräte & Dienste → Integration hinzufügen → **Orphaned Entities**
2. Scan-Intervall, Inaktivitätsschwelle und ignorierte Domains konfigurieren

## Lovelace-Karte

```yaml
type: custom:orphaned-entities-card
```

Die Karte wird nach der Installation der Integration automatisch unter `/orphaned_entities_card/orphaned-entities-card.js` bereitgestellt.

**Lovelace-Ressource manuell hinzufügen** (falls nicht automatisch):

Einstellungen → Dashboards → ⋮ → Ressourcen → `+ Ressource hinzufügen`
- URL: `/orphaned_entities_card/orphaned-entities-card.js`
- Typ: JavaScript-Modul

## Services

| Service | Parameter | Beschreibung |
|---|---|---|
| `orphaned_entities.rescan` | – | Neustart des Scans |
| `orphaned_entities.get_results` | – | Ergebnisse abrufen (feuert Event) |
| `orphaned_entities.disable_entity` | `entity_id` | Entität deaktivieren |
| `orphaned_entities.delete_entity` | `entity_id` | Entität löschen |
| `orphaned_entities.ignore_entity` | `entity_id` | Entität ignorieren |
| `orphaned_entities.unignore_entity` | `entity_id` | Ignorierung aufheben |

## Einstellungen

| Parameter | Standard | Beschreibung |
|---|---|---|
| Scan-Intervall | 24 Stunden | Wie oft automatisch gescannt wird |
| Inaktivitätsschwelle | 30 Tage | Ab wann `unavailable`/`unknown` als verwaist gilt |
| Ignorierte Domains | (viele) | Diese Domains werden beim Scan übersprungen |
