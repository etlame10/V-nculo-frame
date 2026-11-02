// Descarga de archivos con la Bot API de Telegram (getFile + descarga).
//
// La URL de descarga contiene el token del bot, así que ningún error que
// salga de aquí incluye la URL ni el mensaje original de fetch.

import { FileTooLarge, TelegramFiles } from "./handler.ts";

export class TelegramError extends Error {}

type Fetch = typeof fetch;

export function telegramFiles(token: string, fetchImpl: Fetch = fetch): TelegramFiles {
  const api = `https://api.telegram.org/bot${token}`;
  const files = `https://api.telegram.org/file/bot${token}`;

  async function call(url: string): Promise<Response> {
    try {
      return await fetchImpl(url);
    } catch {
      throw new TelegramError("no se pudo contactar con Telegram");
    }
  }

  return {
    async download(fileId: string, maxBytes: number): Promise<Uint8Array> {
      const info = await call(`${api}/getFile?file_id=${encodeURIComponent(fileId)}`);
      const body = await info.json().catch(() => null);
      if (!info.ok || !body?.ok || typeof body.result?.file_path !== "string") {
        throw new TelegramError(`getFile falló (HTTP ${info.status})`);
      }
      if (typeof body.result.file_size === "number" && body.result.file_size > maxBytes) {
        throw new FileTooLarge();
      }
      const path = body.result.file_path.split("/").map(encodeURIComponent).join("/");
      const response = await call(`${files}/${path}`);
      if (!response.ok || !response.body) {
        throw new TelegramError(`descarga fallida (HTTP ${response.status})`);
      }
      return await readLimited(response.body, maxBytes);
    },
  };
}

// Lee como mucho maxBytes; si el archivo es mayor, para y lanza FileTooLarge
// (no se fía del tamaño declarado).
async function readLimited(stream: ReadableStream<Uint8Array>, maxBytes: number): Promise<Uint8Array> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > maxBytes) {
      await reader.cancel();
      throw new FileTooLarge();
    }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}
