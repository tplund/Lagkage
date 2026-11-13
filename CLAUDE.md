# Lagkage – Tomas' billededitor

En lille Windows-billededitor (Python + PySide6), der erstatter Photoshop til Tomas' daglige brug: lag, markeringer, flyt, udfyld, pipette og lidt mere. Han kender Photoshop udenad, så **genveje og opførsel skal være som i Photoshop**. Det er hovedreglen for alt, der bygges her.

Brugere: Tomas og Anne-Mette (hans kollega). Anne-Mette har den installerede udgave og får opdateringer automatisk.

## Sådan arbejder du her

- **Brugerfladen er på dansk.** Menuerne følger Photoshops struktur (Filer, Rediger, Billede, Lag, Marker, Vis, Hjælp).
- **Byg ikke en fuld Photoshop.** Tilføj det, Tomas faktisk bruger eller beder om. Spørg, hvis en funktion trækker i en anden retning.
- **Test før du siger, at noget virker:** `.venv\Scripts\python.exe tests\run_all.py` (51 tjek; nogle bruger Windows' baggrundsbilleder i `C:\Windows\Web\Wallpaper`). Tilføj tjek i `tests/`, når du bygger noget nyt.
- **Brug altid `.venv` (Python 3.13).** Systemets Python 3.10.0 kan ikke køre PyInstaller.
- **Udgivelse er offentlig.** `release.py` lægger installeren på GitHub, hvor alle installerede kopier henter den. Spørg Tomas, før du udgiver.

## Kommandoer

```
.venv\Scripts\python.exe run.py                         # kør fra kildekoden
.venv\Scripts\python.exe tests\run_all.py               # alle tests
.venv\Scripts\python.exe release.py 1.3 "Hvad er nyt"   # byg exe + installer, commit, tag, GitHub-release
```

Tomas' genvej på skrivebordet peger på `dist\Lagkage\Lagkage.exe` (udviklingsbygget). Det opdateres, når `release.py` eller PyInstaller køres. Luk Lagkage, før du bygger, ellers er filerne låst.

## Opbygning

- `lagkage/document.py` – dokumentmodellen: lag (pixel eller justering), masker (Grayscale8, kædet til lagets position), markering (Alpha8), flydende pixels ved flyt/Ctrl+T, fortryd som øjebliksbilleder (QImage deler data, så det er billigt) og fil-I/O (PSD via psd-tools, `.lagkage`, flade formater)
- `lagkage/canvas.py` – lærredet: visning, zoom/panorering og alle værktøjer
- `lagkage/panels.py` – værktøjslinje, indstillingslinje og lagpanel
- `lagkage/window.py` – menuer, genveje, faner, gem/åbn, dialoger og opdatering
- `lagkage/adjust.py` + `adjust_dialogs.py` – justeringslag (niveauer, kurver, lysstyrke/kontrast, farvetone/mætning, sort-hvid, invertér) og deres dialoger
- `lagkage/inpaint.py` (indholdsbevidst udfyld, LaMa) og `subject.py` (Marker motiv, ISNet) – lokale ONNX-modeller i `%LOCALAPPDATA%\Lagkage\models`, hentes ved første brug
- `lagkage/updater.py` – tjekker den seneste GitHub-udgivelse ved opstart (kun installerede kopier)
- `installer/Lagkage.iss` – Inno Setup-installer (`%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`)

Gengivelsen sker i skærmopløsning (`Document.render` med en transform), så store billeder forbliver hurtige. Justeringslag beregnes med numpy på det, der allerede er tegnet.

## Kendte begrænsninger og mulige næste skridt

- Intet tekstværktøj, ingen laggrupper, ingen klippemasker (Alt+Ctrl+G)
- PSD: justeringslag kan ikke skrives redigerbart (de bages ind ved gem som PSD). `.lagkage` beholder alt.
- Indholdsbevidst udfyld arbejder i 512 px, så store huller bliver bløde
- Pensel: hårdhed og opacitet, men ingen flow eller tryk
- Ingen historikpanel (kun Ctrl+Z / Ctrl+Shift+Z)

## Repo

Offentligt: https://github.com/tplund/Lagkage. Commit-beskeder skrives på dansk.
