// Pruebas de la descarga desde Telegram con un fetch simulado.
import { strict as assert } from "node:assert";
import { FileTooLarge } from "./handler.ts";
import { TelegramError, telegramFiles } from "./telegram.ts";

const TOKEN = "123456:TOKEN-FICTICIO";

function fakeFetch(routes: Record<string, () => Response>, calls: string[] = []): typeof fetch {
  return (input) => {
    const url = String(input);
    calls.push(url);
    for (const [prefix, respond] of Object.entries(routes)) {
      if (url.startsWith(prefix)) return Promise.resolve(respond());
    }
    return Promise.reject(new TypeError(`fetch falló para ${url}`));
  };
}

const API = `https://api.telegram.org/bot${TOKEN}/getFile`;
const FILES = `https://api.telegram.org/file/bot${TOKEN}/`;

Deno.test("descarga: getFile y luego el archivo", async () => {
  const calls: string[] = [];
  const files = telegramFiles(
    TOKEN,
    fakeFetch({
      [API]: () => Response.json({ ok: true, result: { file_path: "photos/file_1.jpg", file_size: 3 } }),
      [FILES]: () => new Response(Uint8Array.from([1, 2, 3])),
    }, calls),
  );
  assert.deepEqual(await files.download("abc/def", 10), Uint8Array.from([1, 2, 3]));
  assert.equal(calls[0], `${API}?file_id=abc%2Fdef`);
  assert.equal(calls[1], `${FILES}photos/file_1.jpg`);
});

Deno.test("descarga: tamaño declarado mayor que el máximo → FileTooLarge sin descargar", async () => {
  const calls: string[] = [];
  const files = telegramFiles(
    TOKEN,
    fakeFetch({
      [API]: () => Response.json({ ok: true, result: { file_path: "x.jpg", file_size: 11 } }),
    }, calls),
  );
  await assert.rejects(files.download("f", 10), FileTooLarge);
  assert.equal(calls.length, 1);
});

Deno.test("descarga: si el archivo real supera el máximo se corta y falla", async () => {
  const files = telegramFiles(
    TOKEN,
    fakeFetch({
      [API]: () => Response.json({ ok: true, result: { file_path: "x.jpg" } }),
      [FILES]: () => new Response(new Uint8Array(11)),
    }),
  );
  await assert.rejects(files.download("f", 10), FileTooLarge);
});

Deno.test("errores de Telegram o de red no revelan el token", async () => {
  const cases = [
    fakeFetch({ [API]: () => Response.json({ ok: false, description: "Bad Request" }, { status: 400 }) }),
    fakeFetch({ [API]: () => new Response("no es json") }),
    fakeFetch({}),
    fakeFetch({
      [API]: () => Response.json({ ok: true, result: { file_path: "x.jpg" } }),
      [FILES]: () => new Response(null, { status: 404 }),
    }),
  ];
  for (const fetchImpl of cases) {
    const error = await telegramFiles(TOKEN, fetchImpl).download("f", 10).catch((e) => e);
    assert.ok(error instanceof TelegramError, String(error));
    assert.ok(!String(error.message).includes("TOKEN"), error.message);
  }
});
