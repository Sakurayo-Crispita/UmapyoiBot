import requests
import time
import os

BASE_URL = "http://localhost:5000"

print("\n" + "="*50)
print("🛡️ INICIANDO AUDITORÍA DE SEGURIDAD UMAPYOIBOT 🛡️")
print("="*50 + "\n")

# 1. PRUEBA DE CABECERAS HTTP
print("[⏳] Prueba 1: Cabeceras Anti-Clickjacking y XSS...")
try:
    res = requests.get(BASE_URL)
    headers = res.headers
    
    x_frame = headers.get('X-Frame-Options')
    x_content = headers.get('X-Content-Type-Options')
    ref_policy = headers.get('Referrer-Policy')
    
    if x_frame == 'DENY' and x_content == 'nosniff' and ref_policy == 'strict-origin-when-cross-origin':
        print("  ✅ ÉXITO: Cabeceras de seguridad blindadas detectadas.")
    else:
        print(f"  ❌ FALLO: Faltan cabeceras. Encontrado: {x_frame}, {x_content}, {ref_policy}")
except Exception as e:
    print(f"  ❌ FALLO DE CONEXIÓN: {e}")

# 2. PRUEBA DE PÁGINA 404 (ESTÉTICA)
print("\n[⏳] Prueba 2: Pantalla de Error 404 Estética...")
try:
    res = requests.get(f"{BASE_URL}/esta-pagina-no-existe-jajaja")
    if res.status_code == 404 and "Página no encontrada - UmapyoiBot" in res.text:
        print("  ✅ ÉXITO: Redirección correcta a la pantalla de cristal 404. Ningún dato expuesto.")
    else:
        print(f"  ❌ FALLO: Código {res.status_code} u HTML incorrecto.")
except Exception as e:
    print(f"  ❌ FALLO DE CONEXIÓN: {e}")

# 3. PRUEBA DE LÍMITE DE PAYLOAD (RAM EXHAUSTION)
print("\n[⏳] Prueba 3: Ataque de Sobrecarga de RAM (Payload > 5MB)...")
try:
    huge_payload = "A" * (6 * 1024 * 1024)  # 6 MB de "A"s
    res = requests.post(f"{BASE_URL}/test-payload", data=huge_payload)
    if res.status_code == 413:
        print("  ✅ ÉXITO: El servidor cortó la conexión y bloqueó el archivo de 6MB (Error 413). Memoria a salvo.")
    else:
        print(f"  ❌ FALLO: El servidor aceptó la carga maliciosa o devolvió {res.status_code}.")
except Exception as e:
    print(f"  ❌ FALLO DE CONEXIÓN: {e}")

# 4. PRUEBA DE RATE LIMITER (ANTI-DDOS Y BANEO DE IP)
print("\n[⏳] Prueba 4: Ataque de Spam (Tirar 6 peticiones en 1 segundo)...")
try:
    successes = 0
    blocks = 0
    banned = False
    
    for i in range(1, 8):
        res = requests.get(f"{BASE_URL}/")
        if res.status_code == 200:
            successes += 1
            print(f"  -> Pet. {i}: Aceptada (Status: 200)")
        elif res.status_code == 429:
            blocks += 1
            banned = True
            print(f"  -> Pet. {i}: ¡BLOQUEADA! Escudo activado (Status: 429)")
            
    if successes == 5 and blocks == 2 and banned:
        print("  ✅ ÉXITO: El rate limiter funcionó perfecto. Las primeras 5 pasaron, el resto colapsó contra el escudo 429.")
        
        print("\n  [⏳] Verificando el Castigo Inamovible (10 segundos)...")
        time.sleep(4)
        print("  -> Esperamos 4 segundos, el atacante intenta de nuevo...")
        res_punish = requests.get(f"{BASE_URL}/")
        if res_punish.status_code == 429:
            print("  ✅ ÉXITO: Sigue BANEADO. El atacante no puede esquivar el castigo de 10s.")
        else:
            print("  ❌ FALLO: El castigo se borró prematuramente.")
    else:
        print(f"  ❌ FALLO DEL RATE LIMITER: Aceptó {successes} y bloqueó {blocks}.")
except Exception as e:
    print(f"  ❌ FALLO DE CONEXIÓN: {e}")

print("\n" + "="*50)
print("🏁 AUDITORÍA COMPLETADA 🏁")
print("="*50 + "\n")
