# Sims 3 Mod Manager

Lokaler Desktop-Modmanager für Windows, Python 3.11+ mit Tcl/Tk (im offiziellen Windows-Installer enthalten). Keine Python-Zusatzpakete nötig.

## Start

1. Python von https://www.python.org/downloads/windows/ installieren, inklusive Tcl/Tk und Python Launcher.
2. `Starten.bat` doppelklicken, alternativ `py -3 app.py`.
3. Sims 3 schließen. Benutzerordner auswählen: normalerweise `Dokumente\Electronic Arts\The Sims 3`, auch unter OneDrive. Der Ordner muss `Saves` oder `Options.ini` enthalten.
4. Mod-The-Sims-Mod-Link einfügen und **Dateien laden** wählen.
5. Beschreibung/Anforderungen im Browser lesen. Passende Datei auswählen, **Herunterladen & installieren** klicken.
6. Unter **Meine Mods** lokale Dateien importieren, Mods deaktivieren/reaktivieren und die Integrität prüfen.

Es werden keine Mods beim ersten Start automatisch installiert. Varianten, Spielversion und Abhängigkeiten entscheidet der Nutzer anhand der Mod-Anleitung. „Automatisch“ bedeutet: Nach Dateiauswahl übernimmt die App Download, Entpacken und Package-Installation.

## Funktionsumfang

- MTS-Mod-Seiten `/d/ID/...` und `/download.php?t=ID` auslesen, Dateivarianten anzeigen.
- HTTPS-Downloads, Session-Cookies innerhalb der App, Fortschritt und Fehleranzeige.
- ZIP und direkte `.package`-Dateien installieren; Package-Signatur DBPF prüfen.
- Doppelte Dateien per SHA-256 erkennen, Originaldateien anderer Mods nicht überschreiben.
- ZIP-Pfade und Entpackgröße prüfen; keine ausführbaren Dateien starten.
- Aktivieren/deaktivieren durch Verschieben kompletter Mod-Ordner.
- Änderungen und fehlende Dateien erkennen. Kein Erkennen von inhaltlichen Ressourcenkonflikten.
- Downloadarchiv und Quell-URL behalten; Bibliothek bleibt zwischen Starts bestehen.
- Vorhandene Resource.cfg beibehalten, vor einer Ergänzung sichern.

## Grenzen

Die Anwendung ist eine erste funktionsfähige Version, kein vollständiger Vortex-Ersatz. Keine automatische Update-/Abhängigkeitsauflösung, kein Nexus-Login oder nxm-Protokoll, keine Mod-Konfliktanalyse. Die App verwendet keine offizielle MTS-API; die Integration liest öffentliches HTML und kann sich bei Website-Änderungen ändern. Login/Captcha/Anti-Bot-Sperren werden nicht umgangen. In dem Fall im Browser herunterladen und importieren. Keine Passwörter in der App hinterlegen.

RAR und 7z mit 7-Zip entpacken, dann Packages importieren. Archive mit DLL/ASI/EXE, Sims3Pack, Sim oder World werden nicht automatisch installiert, auch wenn darin Packages enthalten sind. Spezialmods wie Smooth Patch verlangen eigene Installationsschritte. Anleitung beachten; der heruntergeladene Originalinhalt bleibt erhalten. DBPF-Signatur allein bestätigt nicht die Sims-Spielversion; Sims-3-Kompatibilität auf der Quellseite prüfen.

Nur von der App installierte Dateien werden verwaltet. Pro Benutzerordner nur eine App-Instanz gleichzeitig starten. Spiel und Launcher während Änderungen schließen. Spielstände vor größeren Mod-Änderungen sichern. Keine Spielstände oder Caches werden verändert.

## Speicherorte

- Aktiv: `Mods/Packages/S3Manager/<Mod-ID>/*.package`
- Deaktiviert: `Mods/.s3manager/disabled/<Mod-ID>/`
- Bibliothek: `Mods/.s3manager/library.json`
- Downloads: `Mods/.s3manager/downloads/`
- Resource.cfg-Sicherung: `Mods/.s3manager/Resource-*.cfg.bak`
- Benutzerordner-Einstellung: `settings.json` neben `app.py`

Deaktivieren entfernt keine Mod-Daten aus einem bereits gespeicherten Spielstand. Den Manager-Ordner nicht löschen, solange dessen Bibliothek weiterverwendet werden soll.

## Tests / Entwicklung

`python -m unittest discover -s tests -v`

Die automatischen Tests verwenden temporäre Sims-Ordner und einen lokalen HTTP-Server. GUI und echte MTS-Downloads müssen unter Windows zusätzlich geprüft werden. In der Entwicklungsumgebung fehlte Tcl/Tk. Die zwölf Backend-Tests bestanden. Ein echter Abruf der Smooth-Patch-Seite sowie ihres ZIP-Archivs (836.644 Bytes) inklusive Weiterleitung auf den MTS-Mirror wurde erfolgreich geprüft; der Patch wurde dabei nicht installiert.

Optional selbst eine EXE bauen: `py -3 -m pip install pyinstaller`, danach `py -3 -m PyInstaller --onefile --windowed --name Sims3ModManager app.py`. Dies wurde hier nicht ausgeführt. Die Python-Version mit `Starten.bat` ist der vorgesehene Startweg.

Technische Referenzen:
- https://modthesims.info/wiki.php?title=Game_Help:TS3_Organizing_Custom_Content
- https://modthesims.info/wiki.php?title=Game_Help:Installing_Sims_3_Package_Files/Old_Way_to_New_Way
