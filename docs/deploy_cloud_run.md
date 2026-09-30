# Deploy de la API en Google Cloud Run

La web (GitHub Pages) no necesita la API para lo principal; la API responde las previas con fecha histórica.
Esta guía se hace **una sola vez**. Después, cada push a `main` que toque la API y dos veces por semana (datos nuevos),
`.github/workflows/deploy-api.yml` reconstruye la imagen y la despliega solo.

## Qué se crea y por qué

| Recurso | Para qué |
|---|---|
| Repositorio Docker en Artifact Registry | Guardar las imágenes. Política de limpieza: se conservan las 2 más recientes. |
| Cuenta de servicio `api-runtime` | Identidad con la que corre la API. **Sin permisos**: la API no accede a nada de Google Cloud. |
| Cuenta de servicio `github-deployer` | Identidad con la que GitHub Actions construye y despliega. |
| Workload Identity Federation | GitHub Actions se autentica con tokens de corta duración, **sin claves JSON guardadas en ningún lado**. Solo este repositorio puede usarla. |

## Costos (verificar siempre en las páginas oficiales)

* Cloud Run tiene un nivel gratuito mensual (2 millones de pedidos, 180.000 vCPU-segundos, 360.000 GB-segundos).
  El servicio escala a cero, así que en reposo no consume. Máximo 2 instancias para acotar el gasto.
* Artifact Registry: 0,5 GB gratis por cuenta de facturación; después, USD 0,10 por GB y mes. La imagen es liviana
  (sin scipy ni pyarrow) y la política de limpieza evita acumular versiones.
* Google Cloud **requiere una cuenta de facturación** aunque no se supere el nivel gratuito.
  **Recomendado:** crear un presupuesto con alertas (Facturación → Presupuestos y alertas), por ejemplo de USD 5.

## Pasos

Requisitos: [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) instalado y `gcloud auth login` hecho, un
proyecto con facturación habilitada y el repositorio ya subido a GitHub.

```bash
# --- completar ---
PROJECT_ID="tu-proyecto"
REGION="us-central1"
GITHUB_REPO="tu-usuario/football-match-predictor"   # dueño/nombre exactos del repo en GitHub
GITHUB_OWNER="${GITHUB_REPO%%/*}"

gcloud config set project "$PROJECT_ID"

# 1) APIs necesarias
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

# 2) Repositorio de imágenes + política de limpieza (conserva las 2 más recientes)
gcloud artifacts repositories create premier-predictor \
  --repository-format=docker --location="$REGION" \
  --description="Imágenes de la API de Marcador Probable"
gcloud artifacts repositories set-cleanup-policies premier-predictor \
  --location="$REGION" --policy=deploy/artifact-cleanup-policy.json --no-dry-run

# 3) Cuentas de servicio
gcloud iam service-accounts create api-runtime --display-name="Runtime de la API (sin permisos)"
gcloud iam service-accounts create github-deployer --display-name="Deploy desde GitHub Actions"
RUNTIME_SA="api-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOYER_SA="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

# Permisos del deployer: administrar Cloud Run, subir imágenes a ESE repositorio,
# y "actuar como" la cuenta de runtime (solo esa).
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOYER_SA}" --role="roles/run.admin"
gcloud artifacts repositories add-iam-policy-binding premier-predictor --location="$REGION" \
  --member="serviceAccount:${DEPLOYER_SA}" --role="roles/artifactregistry.writer"
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="serviceAccount:${DEPLOYER_SA}" --role="roles/iam.serviceAccountUser"

# 4) Workload Identity Federation (según el README de google-github-actions/auth)
gcloud iam workload-identity-pools create "github" \
  --location="global" --display-name="GitHub Actions Pool"
gcloud iam workload-identity-pools providers create-oidc "football-predictor" \
  --location="global" --workload-identity-pool="github" \
  --display-name="GitHub football-match-predictor" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == '${GITHUB_OWNER}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

POOL_ID=$(gcloud iam workload-identity-pools describe "github" --location="global" --format="value(name)")
# Solo ESTE repositorio puede usar la cuenta del deployer
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_SA" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${GITHUB_REPO}"

# 5) Valores para cargar en GitHub (ver abajo)
echo "GCP_PROJECT_ID=$PROJECT_ID"
echo "GCP_REGION=$REGION"
echo "GCP_WIF_PROVIDER=$(gcloud iam workload-identity-pools providers describe football-predictor --location=global --workload-identity-pool=github --format='value(name)')"
echo "GCP_DEPLOYER_SA=$DEPLOYER_SA"
echo "GCP_RUNTIME_SA=$RUNTIME_SA"
```

## Variables en GitHub

En el repositorio: *Settings → Secrets and variables → Actions → **Variables*** (no son secretos: ninguno da acceso
por sí solo, porque la federación solo acepta tokens emitidos para este repositorio).

| Variable | Valor |
|---|---|
| `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_WIF_PROVIDER`, `GCP_DEPLOYER_SA`, `GCP_RUNTIME_SA` | Los que imprime el paso 5 |
| `ALLOWED_ORIGINS` | El origen de la web, p. ej. `https://tu-usuario.github.io` (uno solo, sin barra final) |
| `API_URL` | La URL del servicio que muestra el primer deploy (p. ej. `https://premier-predictor-api-xxxx.a.run.app`) |

Orden sugerido: cargar las `GCP_*` y `ALLOWED_ORIGINS` → correr **Deploy de la API (Cloud Run)** a mano (pestaña
*Actions*) → copiar la URL a `API_URL` → correr **Actualizar datos y publicar** para que la web la use.

## Verificar

```bash
curl "https://<tu-servicio>.run.app/health"
curl "https://<tu-servicio>.run.app/predict?home=Arsenal&away=Chelsea&date=2024-01-20"
```

La documentación interactiva de la API queda en `https://<tu-servicio>.run.app/docs`.
