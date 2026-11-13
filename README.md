# Lagkage

En lille billededitor til Windows med Photoshops genveje: lag, markeringer, flyt, udfyld og pipette. Den åbner og gemmer PSD med lag.

**Kør:** `dist\Lagkage\Lagkage.exe` (eller `python run.py` under udvikling).
**Genveje:** F1 i programmet.

## Byg igen efter ændringer

PyInstaller virker ikke med Python 3.10.0, så der bygges med venv'en på Python 3.13:

```
.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --name Lagkage --icon lagkage/lagkage.ico --add-data "lagkage/lagkage.ico;lagkage" --exclude-module tkinter --exclude-module matplotlib run.py
```

## Udgiv en ny version (selvopdatering)

```
.venv\Scripts\python.exe release.py 1.2 "Hvad er nyt"
```

Scriptet sætter versionsnummeret, bygger exe og installer, committer, tagger og lægger installeren ud som en GitHub-udgivelse. Installerede kopier tjekker den seneste udgivelse ved opstart og viser en linje med "Opdatér nu". Når man klikker på den, henter programmet installeren, lukker, installerer stille og starter igen. Udviklingsbygget i `dist\` opdaterer ikke sig selv.

## Installer (til at dele programmet)

Byg først exe'en (se ovenfor), og byg derefter installeren med Inno Setup:

```
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\Lagkage.iss
```

Resultatet er `installer\Output\Lagkage-Setup-1.0.exe` (ca. 70 MB). Den installerer uden administratorrettigheder i `%LOCALAPPDATA%\Programs\Lagkage`. Den laver genveje i Start-menuen (og på skrivebordet, hvis man vælger det) og føjer Lagkage til "Åbn med". Man kan også vælge, at PSD-filer åbner i Lagkage. Afinstallation sker under Indstillinger > Apps. AI-modellerne er ikke med i installeren. De hentes, første gang man bruger funktionerne.

## Opbygning

- `lagkage/document.py` – lag, markering (Alpha8-maske), flydende pixels, fortryd og PSD-I/O (psd-tools)
- `lagkage/canvas.py` – lærred, zoom og alle værktøjer, inkl. frit transformér
- `lagkage/panels.py` – værktøjslinje, indstillingslinje og lagpanel
- `lagkage/window.py` – menuer, genveje, faner, gem/åbn og dialoger

## Indholdsbevidst udfyld

Udfyld (Shift+F5 eller Shift+Backspace) har valget "Indholdsbevidst". Det bruger LaMa (open source), som kører lokalt på CPU via onnxruntime. Modellen ligger i `%LOCALAPPDATA%\Lagkage\models\lama_fp32.onnx` (208 MB) og hentes automatisk, hvis den mangler. Programmet indlæser den i baggrunden ved opstart, og en udfyldning tager cirka 5 sekunder. Meget store huller bliver lidt bløde, fordi modellen arbejder i 512 × 512 px.

## Marker motiv

Marker > Motiv, eller knappen i indstillingslinjen for markeringsværktøjerne. Det bruger ISNet (open source, fra rembg-projektet) lokalt via onnxruntime. Modellen ligger i `%LOCALAPPDATA%\Lagkage\models\isnet-general-use.onnx` (180 MB) og hentes automatisk, hvis den mangler.

## PSD-begrænsninger

Tekst-, form- og smart object-lag bliver til pixellag ved åbning. Justeringslag udelades, og lagmasker og effekter bages ind i pixels. Grupper foldes ud til almindelige lag.
