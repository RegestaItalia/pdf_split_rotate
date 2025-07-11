# Specifica il percorso della cartella da analizzare
$folderPath = "W:\03_processati"

# Estrai solo le cartelle al primo livello e ordina alfabeticamente
$folders = Get-ChildItem -Path $folderPath -Directory | Sort-Object Name

# Salva i nomi delle cartelle in un file di testo
$folders | ForEach-Object { $_.Name } | Out-File "C:\Users\RegestaAdm\Documents\pdf_split_rotate-main\folders.txt"

----------------------
----------------------
----------------------
----------------------

# Specifica il percorso del file di input e del file di output
$inputFile = "C:\Users\RegestaAdm\Documents\pdf_split_rotate-main\count_script\folders_to_count.txt"
$outputFile = "C:\Users\RegestaAdm\Documents\pdf_split_rotate-main\count_script\folders_with_count.txt"

# Leggi tutte le cartelle dal file di input
$folders = Get-Content -Path $inputFile

# Crea una lista vuota per i risultati
$results = @()

# Cicla su ogni cartella
foreach ($folder in $folders) {
    # Costruisci il percorso completo della cartella principale
    $folderPath = "W:\03_processati\$folder"
    
    # Verifica se la cartella principale esiste
    if (Test-Path -Path $folderPath) {
        # Trova la sottocartella al primo livello
        $subFolder = Get-ChildItem -Path $folderPath -Directory | Select-Object -First 1
        
        if ($subFolder) {
            # Conta il numero di file dentro la sottocartella, escludendo le sottocartelle
            $fileCount = (Get-ChildItem -Path $subFolder.FullName -File -ErrorAction SilentlyContinue).Count
            
            # Aggiungi il risultato (nome cartella e conteggio dei file) alla lista
            $results += "$folder $fileCount"
        } else {
            # Se non ci sono sottocartelle, segnala che non è stata trovata
            $results += "$folder - No subfolder found"
        }
    }
    else {
        # Se la cartella principale non esiste, segnala l'errore
        $results += "$folder - Directory not found"
    }
}

# Scrivi i risultati nel file di output
$results | Out-File -FilePath $outputFile
