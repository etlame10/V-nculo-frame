#!/usr/bin/env bash
# Prueba de extremo a extremo del webhook de Telegram con un Supabase LOCAL
# (CLI + Docker). No usa ningún bot ni proyecto real: el token es ficticio y
# solo se prueban mensajes que no necesitan descargar nada de Telegram.
#
# Requisitos: supabase (CLI), deno, curl, jq. Uso: ./scripts/test_functions_e2e.sh
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

# Si ya hay un Supabase local arrancado solo con la base de datos
# (`supabase db start`), `supabase start` no arranca el resto: se para antes.
if ! supabase status -o json 2>/dev/null | jq -e '.API_URL' >/dev/null; then
    supabase stop --no-backup >/dev/null 2>&1 || true
fi
supabase start -x studio,imgproxy,realtime,logflare,vector,supavisor

status="$(supabase status -o json)"
api_url="$(jq -r '.API_URL' <<<"$status")"
service_key="$(jq -r '.SERVICE_ROLE_KEY // .SECRET_KEY // empty' <<<"$status")"
if [[ -z "$api_url" || "$api_url" == null || -z "$service_key" ]]; then
    echo "supabase status no devolvió API_URL y la clave de servicio; campos: $(jq -c 'keys' <<<"$status")" >&2
    exit 1
fi

echo "== store.ts contra Supabase local"
(cd supabase/functions/telegram-webhook &&
    SUPABASE_URL="$api_url" SUPABASE_SERVICE_ROLE_KEY="$service_key" \
        deno test -A store_integration_test.ts)

echo "== Webhook servido por el runtime de Edge Functions"
env_file="$(mktemp)"
trap 'rm -f "$env_file"; kill "${serve_pid:-0}" 2>/dev/null || true' EXIT
secret="secreto-solo-para-ci-$RANDOM$RANDOM"
printf 'TELEGRAM_BOT_TOKEN=000000000:FICTICIO\nTELEGRAM_WEBHOOK_SECRET=%s\n' "$secret" >"$env_file"
supabase functions serve telegram-webhook --env-file "$env_file" &
serve_pid=$!

endpoint="$api_url/functions/v1/telegram-webhook"
update='{"update_id":1,"message":{"message_id":1,"date":0,"chat":{"id":424242,"type":"private"},"from":{"id":424242,"is_bot":false},"text":"Hola"}}'

for _ in $(seq 1 60); do
    code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$endpoint" -H 'Content-Type: application/json' -d "$update" || true)"
    [[ "$code" == 401 ]] && break
    sleep 2
done
[[ "$code" == 401 ]] || { echo "sin secreto se esperaba 401 y llegó $code" >&2; exit 1; }
echo "ok: sin secreto → 401"

code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$endpoint" -H 'Content-Type: application/json' \
    -H 'X-Telegram-Bot-Api-Secret-Token: incorrecto' -d "$update")"
[[ "$code" == 401 ]] || { echo "secreto incorrecto: se esperaba 401 y llegó $code" >&2; exit 1; }
echo "ok: secreto incorrecto → 401"

reply="$(curl -s -X POST "$endpoint" -H 'Content-Type: application/json' \
    -H "X-Telegram-Bot-Api-Secret-Token: $secret" -d "$update")"
expected="Este bot es privado y usted no está en la lista blanca."
[[ "$(jq -r '.text' <<<"$reply")" == "$expected" && "$(jq -r '.method' <<<"$reply")" == sendMessage ]] || {
    echo "respuesta inesperada para un desconocido: $reply" >&2
    exit 1
}
echo "ok: desconocido → \"$expected\""
