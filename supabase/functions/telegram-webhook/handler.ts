// Lógica del webhook de Telegram, sin dependencias de red ni de Supabase:
// recibe la petición y unas dependencias inyectadas, y devuelve la respuesta.
// index.ts conecta las dependencias reales; las pruebas usan dobles.
//
// Reglas (docs/SEGURIDAD.md):
//   * Sin el secret_token correcto → 401 y no se lee nada más.
//   * Solo chats privados. Grupos, canales y mensajes editados se ignoran.
//   * Quien no está vinculado y activo recibe NOT_AUTHORIZED; su foto ni
//     siquiera se descarga.
//   * Las respuestas van en el propio cuerpo de la respuesta HTTP (Telegram
//     las envía como sendMessage), así que el bot no hace llamadas extra.

import { detectImageKind, ImageKind, InvalidImage, stripMetadata } from "./images.ts";
import * as text from "./messages.ts";

export interface Membership {
  memberId: string;
  frameId: string;
  frameName: string;
}

export interface LinkResult {
  displayName: string;
  frameName: string;
}

export interface CleanPhoto {
  bytes: Uint8Array;
  kind: ImageKind;
  sha256: string;
}

export interface Store {
  redeemLinkCode(code: string, telegramUserId: number): Promise<LinkResult | null>;
  activeMemberships(telegramUserId: number): Promise<Membership[]>;
  /** Guarda archivo y fila; "duplicate" si el marco ya tenía esa foto. */
  savePhoto(membership: Membership, photo: CleanPhoto): Promise<"saved" | "duplicate">;
}

export interface TelegramFiles {
  /** Descarga un archivo; FileTooLarge si supera maxBytes. */
  download(fileId: string, maxBytes: number): Promise<Uint8Array>;
}

export class FileTooLarge extends Error {}

export interface Deps {
  webhookSecret: string;
  maxPhotoBytes: number;
  store: Store;
  files: TelegramFiles;
}

// Subconjunto de los tipos de la Bot API que se usa.
interface TgUser {
  id: number;
  is_bot?: boolean;
}

interface TgPhotoSize {
  file_id: string;
  file_size?: number;
  width: number;
  height: number;
}

interface TgDocument {
  file_id: string;
  mime_type?: string;
  file_size?: number;
}

interface TgMessage {
  chat: { id: number; type: string };
  from?: TgUser;
  text?: string;
  photo?: TgPhotoSize[];
  document?: TgDocument;
}

interface TgUpdate {
  update_id: number;
  message?: TgMessage;
}

const ACCEPTED_DOCUMENT_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const CODE_PATTERN = /^[A-Za-z0-9]{4}[\s-]?[A-Za-z0-9]{4}$/;

export async function handleRequest(request: Request, deps: Deps): Promise<Response> {
  if (request.method !== "POST") return new Response(null, { status: 405 });
  if (!deps.webhookSecret) {
    // Mal configurado: nunca aceptar mensajes sin poder verificarlos.
    return new Response(null, { status: 500 });
  }
  const given = request.headers.get("X-Telegram-Bot-Api-Secret-Token") ?? "";
  if (!(await sameSecret(given, deps.webhookSecret))) {
    return new Response(null, { status: 401 });
  }

  let update: TgUpdate;
  try {
    update = await request.json();
  } catch {
    return new Response(null, { status: 400 });
  }

  const message = update.message;
  if (!message || message.chat?.type !== "private" || !message.from || message.from.is_bot) {
    return new Response(null, { status: 200 });
  }
  let reply: string;
  try {
    reply = await replyTo(message, message.from.id, deps);
  } catch (error) {
    // Red, Telegram o Supabase: 500 para que Telegram reintente. El registro
    // no incluye datos personales ni URLs (que podrían llevar el token).
    console.error("telegram-webhook:", error instanceof Error ? error.message : "error");
    return new Response(null, { status: 500 });
  }
  return Response.json({ method: "sendMessage", chat_id: message.chat.id, text: reply });
}

async function replyTo(message: TgMessage, userId: number, deps: Deps): Promise<string> {
  let triedCode = false;
  if (typeof message.text === "string") {
    const code = extractCode(message.text);
    if (code !== null) {
      const result = await deps.store.redeemLinkCode(code, userId);
      if (result) return text.linked(result.displayName, result.frameName);
      triedCode = true;
    }
  }

  const memberships = await deps.store.activeMemberships(userId);
  if (memberships.length === 0) return triedCode ? text.INVALID_CODE : text.NOT_AUTHORIZED;
  const frameNames = memberships.map((m) => m.frameName);

  const fileId = pickImageFile(message);
  if (fileId === null) {
    return message.text !== undefined ? text.help(frameNames) : text.ONLY_PHOTOS;
  }
  if (fileId.declaredSize !== undefined && fileId.declaredSize > deps.maxPhotoBytes) {
    return text.tooLarge(megabytes(deps.maxPhotoBytes));
  }

  let bytes: Uint8Array;
  try {
    bytes = await deps.files.download(fileId.id, deps.maxPhotoBytes);
  } catch (error) {
    if (error instanceof FileTooLarge) return text.tooLarge(megabytes(deps.maxPhotoBytes));
    throw error;
  }

  const kind = bytes.length > 0 ? detectImageKind(bytes) : null;
  if (kind === null) return text.ONLY_PHOTOS;
  let clean: Uint8Array;
  try {
    clean = stripMetadata(bytes, kind);
  } catch (error) {
    if (error instanceof InvalidImage) return text.DAMAGED_PHOTO;
    throw error;
  }

  const photo = { bytes: clean, kind, sha256: await sha256Hex(clean) };
  const results = [];
  for (const membership of memberships) {
    results.push(await deps.store.savePhoto(membership, photo));
  }
  return results.every((r) => r === "duplicate") ? text.PHOTO_DUPLICATE : text.photoReceived(frameNames);
}

/** "/start CODIGO" (enlace de invitación) o el código solo. */
export function extractCode(message: string): string | null {
  let candidate = message.trim();
  const start = /^\/start(?:@\w+)?(?:\s+(.*))?$/s.exec(candidate);
  if (start) candidate = (start[1] ?? "").trim();
  return CODE_PATTERN.test(candidate) ? candidate : null;
}

function pickImageFile(message: TgMessage): { id: string; declaredSize?: number } | null {
  if (message.photo && message.photo.length > 0) {
    // Telegram manda varias resoluciones; la mayor es la de más píxeles.
    const largest = message.photo.reduce((a, b) => (b.width * b.height > a.width * a.height ? b : a));
    return { id: largest.file_id, declaredSize: largest.file_size };
  }
  if (message.document && ACCEPTED_DOCUMENT_TYPES.has(message.document.mime_type ?? "")) {
    return { id: message.document.file_id, declaredSize: message.document.file_size };
  }
  return null;
}

function megabytes(bytes: number): number {
  return Math.round(bytes / (1024 * 1024));
}

export async function sha256Hex(data: Uint8Array): Promise<string> {
  // Copia con ArrayBuffer propio (lo que exige el tipo BufferSource).
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new Uint8Array(data)));
  return Array.from(digest, (b) => b.toString(16).padStart(2, "0")).join("");
}

// Comparación en tiempo constante: se comparan los hashes, que siempre
// tienen la misma longitud.
async function sameSecret(given: string, expected: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const [a, b] = await Promise.all([
    sha256Hex(encoder.encode(given)),
    sha256Hex(encoder.encode(expected)),
  ]);
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
