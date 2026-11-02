// Webhook del bot de Telegram (fase 5, D-05).
//
// Variables de entorno (secretos de la función, nunca en el repositorio):
//   TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET
// Supabase añade SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY automáticamente.
// En supabase/config.toml esta función tiene verify_jwt = false: Telegram no
// envía un JWT; se verifica el secret_token en handler.ts.

import { createClient } from "@supabase/supabase-js";
import { handleRequest } from "./handler.ts";
import { supabaseStore } from "./store.ts";
import { telegramFiles } from "./telegram.ts";

const MAX_PHOTO_BYTES = 10 * 1024 * 1024; // igual que el bucket y VINCULO_MAX_PHOTO_MB

function required(name: string): string {
  const value = Deno.env.get(name);
  if (!value) throw new Error(`Falta la variable de entorno ${name}`);
  return value;
}

const client = createClient(required("SUPABASE_URL"), required("SUPABASE_SERVICE_ROLE_KEY"), {
  auth: { persistSession: false, autoRefreshToken: false },
});

const deps = {
  webhookSecret: required("TELEGRAM_WEBHOOK_SECRET"),
  maxPhotoBytes: MAX_PHOTO_BYTES,
  store: supabaseStore(client),
  files: telegramFiles(required("TELEGRAM_BOT_TOKEN")),
};

Deno.serve((request) => handleRequest(request, deps));
