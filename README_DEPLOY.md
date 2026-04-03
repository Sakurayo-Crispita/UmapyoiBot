# Guía de Despliegue 24/7 - UmapyoiBot

Sigue estos pasos para desplegar tu bot y dashboard en un servidor (VPS) de forma permanente.

## 1. Requisitos Previos
- Un servidor VPS (Ubuntu/Debian recomendado).
- Python 3.10 o superior instalado.
- Node.js y NPM (para instalar PM2).

## 2. Preparación del Servidor
```bash
# Actualizar el sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependencias de Python
sudo apt install python3-pip python3-venv -y

# Instalar PM2 (Process Manager)
sudo apt install nodejs npm -y
sudo npm install pm2 -g
```

## 3. Instalación de UmapyoiBot
```bash
# Sube tus archivos al servidor o usa git clone
cd /ruta/hacia/UmapyoiBot
pa              
# Crear entorno virtual (opcional pero recomendado)
python3 -m venv venv
source venv/bin/activate

# Instalar los requerimientos
pip install -r requirements.txt
```

## 4. Configuración
Asegúrate de que tu archivo `.env` esté correctamente configurado con:
- `DISCORD_TOKEN`
- `OWNER_ID`
- `GEMINI_API_KEY`
- `PORT=5000` (El puerto para la web)

## 5. Lanzamiento con PM2 (24/7)
Este es el paso más importante para que nunca se apague.

```bash
# Iniciar todo el sistema (Bot + Web)
pm2 start ecosystem.config.js

# Ver el estado
pm2 status

# Ver logs en tiempo real
pm2 logs umapyoi-system

# Configurar PM2 para que se inicie al reiniciar el sistema
pm2 startup
pm2 save
```

## 6. Acceso Web
Si estás en un VPS, podrás acceder a través de: `http://DIRECCION_IP:5000`. 
*Recuerda abrir el puerto 5000 en el firewall del servidor.*
