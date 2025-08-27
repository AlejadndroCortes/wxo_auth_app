# wxo-auth-app (Python/Flask + MSAL)
Servicio ligero para autenticar usuarios con Microsoft Entra ID (Azure AD) usando OIDC (Authorization Code + PKCE) y emitir una **aserción interna (JWT)** que tu gateway o agente Watsonx Orchestrate puede confiar.

## 🧩 Arquitectura (alta nivel)
Usuario → wxo-auth-app (/login) → Microsoft Login → wxo-auth-app (/redirect) → Sesión activa → `/assertion` devuelve JWT interno → Gateway/Agente valida y permite acceso.

## 🚀 Requisitos previos
- Cuenta de Microsoft Entra ID (Azure AD) con permisos para registrar aplicaciones.
- Python 3.10+
- (Recomendado) Entorno virtual y HTTPS detrás de un reverse proxy.

## 🛠️ Pasos de configuración en Entra ID
1. **Registrar una aplicación** en Entra ID.
2. **Tipos de cuentas compatibles**: normalmente *Single tenant*.
3. **Redirect URI** (tipo *Web*): `https://TU_DOMINIO/redirect` (en local: `http://localhost:8000/redirect`)
4. Crear un **Client Secret** y guardarlo.
5. Opcional: Configurar **Optional Claims** (email, groups) si deseas leerlos en el ID Token.
6. Guardar:
   - `CLIENT_ID`
   - `CLIENT_SECRET`
   - `TENANT_ID`

## 🔐 Variables de entorno
Copia `.env.example` a `.env` y completa los valores:
```
CLIENT_ID=...
CLIENT_SECRET=...
TENANT_ID=...
AUTHORITY=https://login.microsoftonline.com/${TENANT_ID}
REDIRECT_PATH=/redirect
SCOPES=openid profile email
INTERNAL_JWT_SECRET=un_secreto_compartido_con_tu_gateway
```
> **Nota:** Usa `COOKIE_SECURE=true` y HTTPS en producción.

## ▶️ Ejecución local
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # edita con tus valores
python app.py
```
- Accede a `http://localhost:8000/` para ver el estado.
- Inicia sesión en `http://localhost:8000/login`.

## 🔄 Endpoints clave
- `GET /login` → redirige a Microsoft para login.
- `GET /redirect` → callback OIDC. Crea sesión local si fue exitoso.
- `GET /me` → estado de autenticación e identidad normalizada.
- `GET /assertion` → devuelve **JWT interno** (HS256) con claims básicos para consumir desde tu gateway/agente.
- `GET /logout` → cierra sesión local y opcionalmente en Microsoft.

## 🧾 Formato del JWT interno
Payload típico:
```json
{
  "iss": "wxo-auth-service",
  "aud": "watsonx-orchestrate",
  "iat": 1710000000,
  "nbf": 1710000000,
  "exp": 1710003600,
  "sub": "OID del usuario",
  "name": "Nombre Apellido",
  "email": "usuario@empresa.com",
  "tid": "Tenant ID",
  "roles": ["GrupoA", "GrupoB"]
}
```
Valida con HS256 y el `INTERNAL_JWT_SECRET` que compartes con el consumidor.

## 🧰 Integración con tu agente / gateway
- Haz que el **gateway** o el **middleware** que protege a Watsonx llame a `GET /assertion` con la cookie de sesión del usuario (mismo dominio/subdominio).
- Si el JWT es válido y no expiró, permite la solicitud hacia Watsonx Orchestrate.
- Puedes mapear `roles` a permisos del agente.

## 🔒 Buenas prácticas
- **HTTPS obligatorio** en producción.
- Cookies `Secure` y `SameSite=Lax/Strict`.
- Corto TTL de sesión y del JWT interno; usa refresh por demanda.
- Almacena la sesión en Redis/Memcached (cambia `SESSION_TYPE`).
- Revisa auditoría: log-ins, expiraciones, errores.

## 🧪 Prueba rápida con curl
```bash
# 1) Obtener sesión: visita /login en el navegador y autentícate.
# 2) Con la cookie de sesión, pide el JWT interno:
curl -i http://localhost:8000/assertion
```

## 🐳 (Opcional) Docker
```Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000
CMD ["python", "app.py"]
```
> Ejecuta con variables de entorno seguras (no bakear secretos en la imagen).

---
**Soporte**: si necesitas ampliar con verificación de `groups`/`roles`, políticas de IP, o integrar con IBM API Connect, se puede extender fácilmente.
