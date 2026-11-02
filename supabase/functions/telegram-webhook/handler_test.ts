// Pruebas del webhook con dobles de Telegram y de Supabase: no se envía ni
// se recibe ningún mensaje real.
import { strict as assert } from "node:assert";
import { CleanPhoto, Deps, extractCode, FileTooLarge, handleRequest, Membership } from "./handler.ts";
import * as text from "./messages.ts";

const SECRET = "secreto-de-prueba";
const MAX = 10 * 1024 * 1024;

const ANA = 5001;
const DESCONOCIDO = 9999;
const ABUELA: Membership = { memberId: "m-ana", frameId: "f-abuela", frameName: "Marco de la abuela" };
const ABUELO: Membership = { memberId: "m-ana-2", frameId: "f-abuelo", frameName: "Marco del abuelo" };

// JPEG mínimo con EXIF (orientación 1 y texto "GPS") para comprobar que se limpia.
const JPEG = Uint8Array.from([
  0xff,
  0xd8,
  0xff,
  0xe1,
  0x00,
  0x0d,
  0x45,
  0x78,
  0x69,
  0x66,
  0x00,
  0x00,
  0x47,
  0x50,
  0x53,
  0x2d,
  0x31,
  0xff,
  0xda,
  0x00,
  0x08,
  0x01,
  0x01,
  0x00,
  0x00,
  0x3f,
  0x00,
  0x12,
  0x34,
  0xff,
  0xd9,
]);

class FakeWorld {
  memberships = new Map<number, Membership[]>([[ANA, [ABUELA]]]);
  validCodes = new Map<string, { displayName: string; frameName: string }>([
    ["K7PM2QXA", { displayName: "Carlos", frameName: "Marco de la abuela" }],
  ]);
  files = new Map<string, Uint8Array>([["foto-grande", JPEG]]);
  downloads: string[] = [];
  saved: { membership: Membership; photo: CleanPhoto }[] = [];
  redeemed: { code: string; userId: number }[] = [];
  failSave = false;

  deps(overrides: Partial<Deps> = {}): Deps {
    return {
      webhookSecret: SECRET,
      maxPhotoBytes: MAX,
      store: {
        redeemLinkCode: (code, userId) => {
          this.redeemed.push({ code, userId });
          const normalized = code.replace(/[\s-]/g, "").toUpperCase();
          const result = this.validCodes.get(normalized) ?? null;
          if (result) {
            this.validCodes.delete(normalized);
            this.memberships.set(userId, [{
              memberId: "m-new",
              frameId: "f-abuela",
              frameName: result.frameName,
            }]);
          }
          return Promise.resolve(result);
        },
        activeMemberships: (userId) => Promise.resolve(this.memberships.get(userId) ?? []),
        savePhoto: (membership, photo) => {
          if (this.failSave) return Promise.reject(new Error("storage caído"));
          const duplicate = this.saved.some(
            (s) => s.membership.frameId === membership.frameId && s.photo.sha256 === photo.sha256,
          );
          if (!duplicate) this.saved.push({ membership, photo });
          return Promise.resolve(duplicate ? "duplicate" : "saved");
        },
      },
      files: {
        download: (fileId, maxBytes) => {
          this.downloads.push(fileId);
          const data = this.files.get(fileId);
          if (!data) return Promise.reject(new Error("no existe"));
          if (data.length > maxBytes) return Promise.reject(new FileTooLarge());
          return Promise.resolve(data);
        },
      },
      ...overrides,
    };
  }
}

function update(message: Record<string, unknown>, from = ANA, chatType = "private") {
  return {
    update_id: 1,
    message: {
      message_id: 7,
      date: 0,
      chat: { id: from, type: chatType },
      from: { id: from, is_bot: false },
      ...message,
    },
  };
}

function post(body: unknown, secret: string | null = SECRET): Request {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (secret !== null) headers.set("X-Telegram-Bot-Api-Secret-Token", secret);
  return new Request("https://example.invalid/telegram-webhook", {
    method: "POST",
    headers,
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

async function reply(world: FakeWorld, body: unknown): Promise<string> {
  const response = await handleRequest(post(body), world.deps());
  assert.equal(response.status, 200);
  const json = await response.json();
  assert.equal(json.method, "sendMessage");
  return json.text;
}

const PHOTO = {
  photo: [
    { file_id: "foto-pequena", file_size: 1000, width: 90, height: 60 },
    { file_id: "foto-grande", file_size: 200000, width: 1280, height: 853 },
    { file_id: "foto-media", file_size: 30000, width: 320, height: 213 },
  ],
};

// Seguridad del webhook ---------------------------------------------------------

Deno.test("sin secret_token o con uno incorrecto → 401 y no se procesa nada", async () => {
  const world = new FakeWorld();
  for (const secret of [null, "", "otro", SECRET + "x"]) {
    const response = await handleRequest(post(update(PHOTO), secret), world.deps());
    assert.equal(response.status, 401);
  }
  assert.equal(world.downloads.length, 0);
  assert.equal(world.saved.length, 0);
});

Deno.test("si falta configurar el secreto, nunca acepta mensajes", async () => {
  const world = new FakeWorld();
  const response = await handleRequest(post(update(PHOTO), ""), world.deps({ webhookSecret: "" }));
  assert.equal(response.status, 500);
  assert.equal(world.downloads.length, 0);
});

Deno.test("solo acepta POST y JSON válido", async () => {
  const world = new FakeWorld();
  const get = new Request("https://example.invalid/", {
    headers: { "X-Telegram-Bot-Api-Secret-Token": SECRET },
  });
  assert.equal((await handleRequest(get, world.deps())).status, 405);
  assert.equal((await handleRequest(post("{no es json"), world.deps())).status, 400);
});

Deno.test("grupos, canales, bots y mensajes editados se ignoran sin responder", async () => {
  const world = new FakeWorld();
  for (
    const body of [
      update(PHOTO, ANA, "group"),
      update(PHOTO, ANA, "supergroup"),
      { update_id: 2, edited_message: update(PHOTO).message },
      { update_id: 3, channel_post: { chat: { id: 1, type: "channel" } } },
      {
        update_id: 4,
        message: { chat: { id: 1, type: "private" }, from: { id: 1, is_bot: true }, ...PHOTO },
      },
      { update_id: 5 },
    ]
  ) {
    const response = await handleRequest(post(body), world.deps());
    assert.equal(response.status, 200);
    assert.equal(await response.text(), "");
  }
  assert.equal(world.downloads.length, 0);
});

// Personas no autorizadas -------------------------------------------------------

Deno.test("desconocido: foto → mensaje de bot privado y la foto ni se descarga", async () => {
  const world = new FakeWorld();
  assert.equal(await reply(world, update(PHOTO, DESCONOCIDO)), text.NOT_AUTHORIZED);
  assert.equal(world.downloads.length, 0);
  assert.equal(world.saved.length, 0);
});

Deno.test("desconocido: texto, /start o vídeo → mensaje de bot privado", async () => {
  const world = new FakeWorld();
  for (
    const message of [{ text: "Hola" }, { text: "/start" }, { video: { file_id: "v" } }, { sticker: {} }]
  ) {
    assert.equal(await reply(world, update(message, DESCONOCIDO)), text.NOT_AUTHORIZED);
  }
});

Deno.test("familiar desactivado (sin vínculos activos) = no autorizado", async () => {
  const world = new FakeWorld();
  world.memberships.set(ANA, []);
  assert.equal(await reply(world, update(PHOTO)), text.NOT_AUTHORIZED);
  assert.equal(world.downloads.length, 0);
});

// Vinculación -------------------------------------------------------------------

Deno.test("código válido (solo o con /start) vincula y saluda", async () => {
  const world = new FakeWorld();
  assert.equal(
    await reply(world, update({ text: "/start k7pm-2qxa" }, DESCONOCIDO)),
    text.linked("Carlos", "Marco de la abuela"),
  );
  assert.deepEqual(world.redeemed, [{ code: "k7pm-2qxa", userId: DESCONOCIDO }]);
  // Ya vinculado, su foto se acepta.
  assert.equal(await reply(world, update(PHOTO, DESCONOCIDO)), text.photoReceived(["Marco de la abuela"]));
});

Deno.test("código no válido o caducado → aviso de código, sin datos del marco", async () => {
  const world = new FakeWorld();
  assert.equal(await reply(world, update({ text: "ZZZZ-ZZZZ" }, DESCONOCIDO)), text.INVALID_CODE);
});

Deno.test("familiar vinculado que escribe una palabra de 8 letras recibe ayuda", async () => {
  const world = new FakeWorld();
  assert.equal(await reply(world, update({ text: "abuelita" })), text.help(["Marco de la abuela"]));
});

Deno.test("extractCode", () => {
  assert.equal(extractCode("K7PM-2QXA"), "K7PM-2QXA");
  assert.equal(extractCode("  k7pm 2qxa "), "k7pm 2qxa");
  assert.equal(extractCode("/start K7PM2QXA"), "K7PM2QXA");
  assert.equal(extractCode("/start@VinculoBot K7PM-2QXA"), "K7PM-2QXA");
  assert.equal(extractCode("/start"), null);
  assert.equal(extractCode("hola qué tal"), null);
  assert.equal(extractCode("K7PM-2QXA; drop table"), null);
});

// Fotos -------------------------------------------------------------------------

Deno.test("foto de un familiar: descarga la mayor resolución, quita metadatos y guarda", async () => {
  const world = new FakeWorld();
  assert.equal(await reply(world, update(PHOTO)), text.photoReceived(["Marco de la abuela"]));
  assert.deepEqual(world.downloads, ["foto-grande"]);
  assert.equal(world.saved.length, 1);
  const { membership, photo } = world.saved[0];
  assert.deepEqual(membership, ABUELA);
  assert.equal(photo.kind, "jpeg");
  assert.match(photo.sha256, /^[0-9a-f]{64}$/);
  assert.ok(!new TextDecoder().decode(photo.bytes).includes("GPS"), "sin metadatos");
});

Deno.test("la misma foto dos veces → aviso de duplicada", async () => {
  const world = new FakeWorld();
  await reply(world, update(PHOTO));
  assert.equal(await reply(world, update(PHOTO)), text.PHOTO_DUPLICATE);
  assert.equal(world.saved.length, 1);
});

Deno.test("familiar de dos marcos: la foto llega a ambos", async () => {
  const world = new FakeWorld();
  world.memberships.set(ANA, [ABUELA, ABUELO]);
  assert.equal(
    await reply(world, update(PHOTO)),
    text.photoReceived(["Marco de la abuela", "Marco del abuelo"]),
  );
  assert.deepEqual(world.saved.map((s) => s.membership.frameId), ["f-abuela", "f-abuelo"]);
});

Deno.test("foto enviada como archivo (con su EXIF original)", async () => {
  const world = new FakeWorld();
  world.files.set("doc-1", JPEG);
  const body = update({ document: { file_id: "doc-1", mime_type: "image/jpeg", file_size: JPEG.length } });
  assert.equal(await reply(world, body), text.photoReceived(["Marco de la abuela"]));
  assert.equal(world.saved.length, 1);
});

Deno.test("archivos que no son fotos → solo fotos, sin descargar", async () => {
  const world = new FakeWorld();
  for (
    const message of [
      { document: { file_id: "pdf", mime_type: "application/pdf", file_size: 100 } },
      { document: { file_id: "gif", mime_type: "image/gif", file_size: 100 } },
      { video: { file_id: "v" } },
      { voice: { file_id: "a" } },
    ]
  ) {
    assert.equal(await reply(world, update(message)), text.ONLY_PHOTOS);
  }
  assert.equal(world.downloads.length, 0);
});

Deno.test("un archivo que dice ser JPEG pero no lo es → solo fotos, nada guardado", async () => {
  const world = new FakeWorld();
  world.files.set("falso", new TextEncoder().encode("%PDF-1.7 esto no es una imagen"));
  const body = update({ document: { file_id: "falso", mime_type: "image/jpeg", file_size: 30 } });
  assert.equal(await reply(world, body), text.ONLY_PHOTOS);
  assert.equal(world.saved.length, 0);
});

Deno.test("archivo vacío → solo fotos", async () => {
  const world = new FakeWorld();
  world.files.set("vacio", new Uint8Array());
  const body = update({ document: { file_id: "vacio", mime_type: "image/png", file_size: 0 } });
  assert.equal(await reply(world, body), text.ONLY_PHOTOS);
});

Deno.test("foto dañada → aviso, nada guardado", async () => {
  const world = new FakeWorld();
  world.files.set("rota", Uint8Array.from([0xff, 0xd8, 0xff, 0xe1, 0xff, 0xff, 1]));
  const body = update({ document: { file_id: "rota", mime_type: "image/jpeg", file_size: 7 } });
  assert.equal(await reply(world, body), text.DAMAGED_PHOTO);
  assert.equal(world.saved.length, 0);
});

Deno.test("demasiado grande: por el tamaño declarado (sin descargar) o al descargar", async () => {
  const world = new FakeWorld();
  const declared = update({ document: { file_id: "enorme", mime_type: "image/jpeg", file_size: MAX + 1 } });
  assert.equal(await reply(world, declared), text.tooLarge(10));
  assert.equal(world.downloads.length, 0);

  world.files.set("miente", new Uint8Array(64));
  const lying = update({ document: { file_id: "miente", mime_type: "image/jpeg", file_size: 10 } });
  const response = await handleRequest(post(lying), world.deps({ maxPhotoBytes: 32 }));
  assert.equal((await response.json()).text, text.tooLarge(0));
  assert.equal(world.saved.length, 0);
});

Deno.test("si falla la descarga o el guardado → 500 para que Telegram reintente", async () => {
  const world = new FakeWorld();
  const missing = update({ photo: [{ file_id: "no-existe", width: 1, height: 1 }] });
  assert.equal((await handleRequest(post(missing), world.deps())).status, 500);

  world.failSave = true;
  assert.equal((await handleRequest(post(update(PHOTO)), world.deps())).status, 500);
});
