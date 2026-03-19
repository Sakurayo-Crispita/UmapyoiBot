import discord
import asyncio
import os
import sys

async def diag():
    print("--- DIAGNÓSTICO DE VOZ UMAPYOI ---")
    
    # 1. Verificar PyNaCl
    try:
        import nacl
        print("✅ PyNaCl (nacl) está instalado correctamente.")
    except ImportError:
        print("❌ ERROR: PyNaCl no está instalado. Ejecuta: pip install pynacl")
        return

    # 2. Verificar FFmpeg
    ffmpeg_check = os.system("ffmpeg -version > /dev/null 2>&1")
    if ffmpeg_check == 0:
        print("✅ FFmpeg está instalado y accesible.")
    else:
        print("❌ ERROR: FFmpeg no se encuentra en el sistema.")

    # 3. Prueba de Red (UDP)
    print("\nNota: Discord usa puertos UDP aleatorios para la voz.")
    print("Si tu firewall bloquea el tráfico de salida UDP, la voz fallará.")
    
    # 4. Verificar yt-dlp
    try:
        import yt_dlp
        print(f"✅ yt-dlp instalado (Versión: {yt_dlp.version.__version__})")
    except Exception as e:
        print(f"❌ Error verificando yt-dlp: {e}")

if __name__ == "__main__":
    asyncio.run(diag())
