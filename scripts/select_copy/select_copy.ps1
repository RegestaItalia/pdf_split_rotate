<#
================================================================================
 Script Name:    Copy-Selected-Folders.ps1
 Description:    Copia un insieme predefinito di cartelle da una directory di origine 
                 (quella corrente) a una directory di destinazione (es. D:\staging),
                 selezionando solo quelle effettivamente presenti nella sorgente.

 Scopo:          Usato per raccogliere in un unico punto le cartelle di interesse 
                 (ad esempio clienti o fornitori), senza errori su nomi mancanti.

 Funzionamento:
   - La lista dei nomi cartelle è definita in un array `$folderNames`
   - Per ciascun nome:
       • Se la cartella è presente nella directory corrente, viene copiata in D:\staging
       • Se non è presente, viene ignorata e notificata
   - Alla fine, la cartella di destinazione viene aperta in Esplora Risorse

 Requisiti:
   - PowerShell 5+
   - Permessi di lettura sulla directory corrente
   - Permessi di scrittura su D:\staging

 Autore:         [Tuo Nome o Team]
 Data:           [Inserisci data]
================================================================================
#>

# ========================
# DEFINIZIONE DEI NOMI CARTELLA DA COPIARE
# ========================
$folderNames = @(
  "casalasco-spa",
  "casar-srl",
  "caseifici-granterre-spa",
  "cav-umberto-boschi-spa",
  "comelit-group-spa",
  "coswell-spa",
  "euro-company-spa-societ-benefit",
  "giotto-sca-per-azioni",
  "Gruppo Produttori Agrì",  # attenzione agli accenti nel filesystem
  "ics-firpo-srl",
  "in-al-pi-spa",
  "incos-srl",
  "lab-aliment-cecchin-srl",
  "levoni-spa",
  "luxor-spa",
  "marelli-europe-spa",
  "ml-service-di-milani-laura",
  "mlinotest-dd",
  "panaria-industrie-ceramiche-spa",
  "pdp-box-doccia-spa",
  "pettenon-cosmetics-spa-sb",
  "premiata-gelateria-flli-michielan-srl",
  "Raspini Spa",
  "rib-srl",
  "Rupes Spa",
  "scame-parre-spa",
  "sia-societa-italiana-alimenti-spa",
  "toso-spa",
  "zeca-spa",
  "zilio-industries-spa",
  "fratelli-tanzi-spa",
  "gennaro-auricchio-spa",
  "isem-srl",
  "piatti-freschi-italia-srl",
  "pasta-zara-spa"
)

# ========================
# DEFINIZIONE DELLA DESTINAZIONE
# ========================
$destinationRoot = "D:\staging"  # Può essere cambiata secondo necessità

# ========================
# CREAZIONE CARTELLA DESTINAZIONE SE NON ESISTE
# ========================
if (-not (Test-Path $destinationRoot)) {
    Write-Host "`n[INFO] La cartella di destinazione non esiste. La creo: $destinationRoot`n"
    New-Item -ItemType Directory -Path $destinationRoot | Out-Null
}

# ========================
# ELABORAZIONE DELLE CARTELLE
# ========================
foreach ($name in $folderNames) {

    # Costruisco il path completo di origine e destinazione
    $sourcePath = Join-Path $PWD $name
    $destinationPath = Join-Path $destinationRoot $name

    # Verifico se la cartella di origine esiste
    if (Test-Path $sourcePath) {
        Write-Host "[COPY] $name → $destinationRoot"
        try {
            Copy-Item -Path $sourcePath -Destination $destinationPath -Recurse -Force
        } catch {
            Write-Host "[ERRORE] Errore durante la copia di '$name': $_" -ForegroundColor Red
        }
    } else {
        Write-Host "[SKIP] '$name' non trovato nella directory corrente" -ForegroundColor Yellow
    }
}

# ========================
# APERTURA DELLA CARTELLA DESTINAZIONE
# ========================
Write-Host "`n[FINE] Apertura cartella destinazione in Esplora Risorse: $destinationRoot"
Start-Process "explorer.exe" $destinationRoot
