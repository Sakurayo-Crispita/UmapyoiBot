# Script para limpiar procesos "zombie" de UmapyoiBot
Write-Host "Buscando procesos de Python y puerto 5000..." -ForegroundColor Cyan

$port_process = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | Unique
if ($port_process) {
    Write-Host "Cerrando proceso en puerto 5000 (ID: $port_process)..." -ForegroundColor Yellow
    Stop-Process -Id $port_process -Force -ErrorAction SilentlyContinue
}

$python_processes = Get-Process -Name python* -ErrorAction SilentlyContinue
if ($python_processes) {
    Write-Host "Cerrando otros procesos de Python..." -ForegroundColor Yellow
    Stop-Process -Name python* -Force -ErrorAction SilentlyContinue
}

Write-Host "¡Todo limpio! Ya puedes iniciar el servidor con: python web/app.py" -ForegroundColor Green
