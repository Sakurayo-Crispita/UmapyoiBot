# UmapyoiBot Database Sync Script
# Este script descarga la base de datos real del servidor a tu PC local.

$IP = "152.70.220.215"
$USER = "ubuntu"
$KEY = ".\ssh-key-2026-03-21.key"
$REMOTE_PATH = "/home/ubuntu/UmapyoiBot/bot_data.db"
$LOCAL_PATH = ".\bot_data_real.db"

Write-Host "--- Iniciando Sincronización de Base de Datos ---" -ForegroundColor Cyan
Write-Host "Conectando a $IP ..."

if (Test-Path $KEY) {
    scp -i $KEY "${USER}@${IP}:${REMOTE_PATH}" $LOCAL_PATH
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ ¡Éxito! Base de datos descargada como: $LOCAL_PATH" -ForegroundColor Green
        Write-Host "Ya puedes abrirla con DB Browser para SQLite."
    } else {
        Write-Host "❌ Error al descargar. Revisa que el servidor esté encendido y la IP sea correcta." -ForegroundColor Red
    }
} else {
    Write-Host "❌ No se encontró la llave SSH: $KEY" -ForegroundColor Red
    Write-Host "Asegúrate de que el archivo .key esté en esta misma carpeta."
}

Write-Host "`nPresiona cualquier tecla para salir..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
