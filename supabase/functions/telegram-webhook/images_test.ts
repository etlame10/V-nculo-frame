// Pruebas de images.ts con imágenes construidas byte a byte (sin fotos reales).
import { strict as assert } from "node:assert";
import { detectImageKind, InvalidImage, stripMetadata } from "./images.ts";

const enc = new TextEncoder();

function bytes(...parts: (number[] | Uint8Array | string)[]): Uint8Array {
  const arrays = parts.map((p) => (typeof p === "string" ? enc.encode(p) : Uint8Array.from(p)));
  const out = new Uint8Array(arrays.reduce((n, a) => n + a.length, 0));
  let offset = 0;
  for (const a of arrays) {
    out.set(a, offset);
    offset += a.length;
  }
  return out;
}

function contains(haystack: Uint8Array, needle: string | number[] | Uint8Array): boolean {
  const n = typeof needle === "string" ? enc.encode(needle) : Uint8Array.from(needle);
  outer: for (let i = 0; i + n.length <= haystack.length; i++) {
    for (let j = 0; j < n.length; j++) if (haystack[i + j] !== n[j]) continue outer;
    return true;
  }
  return false;
}

function segment(marker: number, payload: Uint8Array | number[] | string): Uint8Array {
  const body = typeof payload === "string" ? enc.encode(payload) : Uint8Array.from(payload);
  const length = body.length + 2;
  return bytes([0xff, marker, length >> 8, length & 0xff], body);
}

// EXIF little-endian con Orientation y un puntero a GPS (con texto fácil de buscar).
function exifPayload(orientation: number): Uint8Array {
  const tiff = [
    0x49,
    0x49,
    0x2a,
    0x00,
    0x08,
    0x00,
    0x00,
    0x00, // "II", 42, IFD0 en 8
    0x02,
    0x00, // 2 entradas
    0x12,
    0x01,
    0x03,
    0x00,
    0x01,
    0x00,
    0x00,
    0x00,
    orientation,
    0x00,
    0x00,
    0x00,
    0x25,
    0x88,
    0x04,
    0x00,
    0x01,
    0x00,
    0x00,
    0x00,
    0x26,
    0x00,
    0x00,
    0x00, // GPSInfo
    0x00,
    0x00,
    0x00,
    0x00,
  ];
  return bytes("Exif\0\0", tiff, "GPS-40.4168N-3.7038W");
}

const SOI = [0xff, 0xd8];
const EOI = [0xff, 0xd9];
const JFIF = segment(0xe0, bytes("JFIF\0", [1, 1, 0, 0, 1, 0, 1, 0, 0]));
const DQT = segment(0xdb, [0x00, ...new Array(64).fill(1)]);
const SOS_AND_DATA = bytes(segment(0xda, [1, 1, 0, 0, 0x3f, 0]), [0x12, 0x34, 0xff, 0x00, 0x56], EOI);

function jpeg(...middle: Uint8Array[]): Uint8Array {
  return bytes(SOI, JFIF, ...middle, DQT, SOS_AND_DATA);
}

Deno.test("detecta JPEG, PNG y WebP por sus bytes, no por el nombre", () => {
  assert.equal(detectImageKind(jpeg()), "jpeg");
  assert.equal(detectImageKind(bytes([0x89], "PNG\r\n\x1a\n")), "png");
  assert.equal(detectImageKind(bytes("RIFF", [4, 0, 0, 0], "WEBP")), "webp");
  assert.equal(detectImageKind(bytes("GIF89a")), null);
  assert.equal(detectImageKind(bytes("%PDF-1.7")), null);
  assert.equal(detectImageKind(new Uint8Array()), null);
});

Deno.test("JPEG: quita EXIF con GPS, XMP, IPTC y comentarios; conserva la orientación", () => {
  const original = jpeg(
    segment(0xe1, exifPayload(6)),
    segment(0xe1, "http://ns.adobe.com/xap/1.0/\0<x:xmpmeta>GPSLatitude 40.4</x:xmpmeta>"),
    segment(0xed, "Photoshop 3.0\0IPTC-Ciudad-Madrid"),
    segment(0xfe, "Comentario: casa de la abuela"),
  );
  const clean = stripMetadata(original, "jpeg");

  assert.ok(!contains(clean, "GPS"), "no queda ningún dato de ubicación");
  assert.ok(!contains(clean, "xmpmeta"));
  assert.ok(!contains(clean, "IPTC"));
  assert.ok(!contains(clean, "abuela"));
  // EXIF mínimo: "MM", Orientation (0x0112) SHORT = 6, justo tras JFIF.
  assert.ok(
    contains(clean, bytes("Exif\0\0MM", [0, 0x2a, 0, 0, 0, 8, 0, 1, 1, 0x12, 0, 3, 0, 0, 0, 1, 0, 6])),
  );
  assert.deepEqual(clean.subarray(0, 2 + JFIF.length), bytes(SOI, JFIF));
  assert.equal(clean[2 + JFIF.length + 1], 0xe1);
  // Tablas e imagen intactas.
  assert.ok(contains(clean, DQT));
  assert.ok(contains(clean, SOS_AND_DATA));
});

Deno.test("JPEG sin orientación (o normal) no recibe EXIF nuevo", () => {
  const clean = stripMetadata(jpeg(segment(0xe1, exifPayload(1))), "jpeg");
  assert.ok(!contains(clean, "Exif"));
  assert.deepEqual(clean, jpeg());
  assert.deepEqual(stripMetadata(jpeg(), "jpeg"), jpeg());
});

Deno.test("JPEG: conserva el perfil de color ICC y el bloque Adobe", () => {
  const icc = segment(0xe2, bytes("ICC_PROFILE\0", [1, 1, 9, 9]));
  const adobe = segment(0xee, bytes("Adobe", [0, 100, 0, 0, 0, 0, 1]));
  const otherApp2 = segment(0xe2, "FPXR\0datos");
  const clean = stripMetadata(jpeg(icc, adobe, otherApp2), "jpeg");
  assert.ok(contains(clean, icc));
  assert.ok(contains(clean, adobe));
  assert.ok(!contains(clean, "FPXR"));
});

Deno.test("JPEG: orientación en EXIF big-endian y EXIF dañado", () => {
  const be = bytes("Exif\0\0", [
    0x4d,
    0x4d,
    0,
    0x2a,
    0,
    0,
    0,
    8,
    0,
    1,
    0x01,
    0x12,
    0,
    3,
    0,
    0,
    0,
    1,
    0,
    8,
    0,
    0,
    0,
    0,
    0,
    0,
  ]);
  assert.ok(contains(stripMetadata(jpeg(segment(0xe1, be)), "jpeg"), [0x01, 0x12, 0, 3, 0, 0, 0, 1, 0, 8]));
  // IFD fuera de rango: se ignora la orientación, pero el EXIF se quita igual.
  const broken = bytes("Exif\0\0", [0x49, 0x49, 0x2a, 0, 0xff, 0xff, 0, 0], "GPS");
  const clean = stripMetadata(jpeg(segment(0xe1, broken)), "jpeg");
  assert.ok(!contains(clean, "GPS"));
  assert.ok(!contains(clean, "Exif"));
});

Deno.test("JPEG: bytes de relleno entre segmentos", () => {
  const withFill = bytes(SOI, [0xff], JFIF, DQT, SOS_AND_DATA);
  assert.ok(contains(stripMetadata(withFill, "jpeg"), SOS_AND_DATA));
});

Deno.test("JPEG truncado o con longitudes falsas → InvalidImage", () => {
  assert.throws(() => stripMetadata(bytes(SOI, [0xff]), "jpeg"), InvalidImage);
  assert.throws(() => stripMetadata(bytes(SOI, [0xff, 0xe1, 0xff, 0xff, 1, 2]), "jpeg"), InvalidImage);
  assert.throws(() => stripMetadata(bytes(SOI, [0xff, 0xe1, 0x00, 0x01]), "jpeg"), InvalidImage);
  assert.throws(() => stripMetadata(bytes(SOI, [0x12, 0x34]), "jpeg"), InvalidImage);
  assert.throws(() => stripMetadata(bytes(SOI, JFIF), "jpeg"), InvalidImage);
});

function pngChunk(type: string, data: Uint8Array | string): Uint8Array {
  const body = typeof data === "string" ? enc.encode(data) : data;
  const length = [
    body.length >>> 24,
    (body.length >>> 16) & 0xff,
    (body.length >>> 8) & 0xff,
    body.length & 0xff,
  ];
  return bytes(length, type, body, [0, 0, 0, 0]); // CRC sin comprobar aquí
}

const PNG_SIG = bytes([0x89], "PNG\r\n\x1a\n");
const IHDR = pngChunk("IHDR", Uint8Array.from([0, 0, 0, 1, 0, 0, 0, 1, 8, 2, 0, 0, 0]));
const IDAT = pngChunk("IDAT", Uint8Array.from([1, 2, 3]));
const IEND = pngChunk("IEND", new Uint8Array());

Deno.test("PNG: quita eXIf y textos; conserva la imagen", () => {
  const original = bytes(
    PNG_SIG,
    IHDR,
    pngChunk("eXIf", "MM\0*GPS"),
    pngChunk("tEXt", "Location\0Madrid"),
    pngChunk("iTXt", "XML:com.adobe.xmp\0GPS"),
    pngChunk("tIME", "1234567"),
    IDAT,
    IEND,
  );
  assert.deepEqual(stripMetadata(original, "png"), bytes(PNG_SIG, IHDR, IDAT, IEND));
});

Deno.test("PNG truncado → InvalidImage", () => {
  assert.throws(() => stripMetadata(bytes(PNG_SIG, IHDR), "png"), InvalidImage);
  assert.throws(() => stripMetadata(bytes(PNG_SIG, [0, 0, 1, 0], "IDAT", [1]), "png"), InvalidImage);
});

function webpChunk(type: string, data: Uint8Array | string): Uint8Array {
  const body = typeof data === "string" ? enc.encode(data) : data;
  const size = [body.length & 0xff, (body.length >> 8) & 0xff, 0, 0];
  return bytes(type, size, body, body.length % 2 ? [0] : []);
}

function webp(...chunks: Uint8Array[]): Uint8Array {
  const body = bytes("WEBP", ...chunks);
  return bytes("RIFF", [body.length & 0xff, (body.length >> 8) & 0xff, 0, 0], body);
}

Deno.test("WebP: quita EXIF y XMP, ajusta indicadores y tamaño", () => {
  const vp8x = webpChunk("VP8X", Uint8Array.from([0x0c, 0, 0, 0, 0, 0, 0, 0, 0, 0]));
  const image = webpChunk("VP8 ", Uint8Array.from([1, 2, 3, 4, 5]));
  const clean = stripMetadata(
    webp(vp8x, image, webpChunk("EXIF", "GPS"), webpChunk("XMP ", "<x>GPS</x>")),
    "webp",
  );

  assert.ok(!contains(clean, "GPS"));
  const expectedVp8x = webpChunk("VP8X", Uint8Array.from([0x00, 0, 0, 0, 0, 0, 0, 0, 0, 0]));
  assert.deepEqual(clean, webp(expectedVp8x, image));
  const declared = clean[4] | (clean[5] << 8);
  assert.equal(declared, clean.length - 8);
});

Deno.test("WebP truncado → InvalidImage", () => {
  const good = webp(webpChunk("VP8 ", Uint8Array.from([1, 2, 3, 4])));
  assert.throws(() => stripMetadata(good.subarray(0, good.length - 2), "webp"), InvalidImage);
});

const ORIENTATION_6_TIFF = Uint8Array.from([
  0x4d,
  0x4d,
  0,
  0x2a,
  0,
  0,
  0,
  8,
  0,
  1,
  0x01,
  0x12,
  0,
  3,
  0,
  0,
  0,
  1,
  0,
  6,
  0,
  0,
  0,
  0,
  0,
  0,
]);

Deno.test("PNG: conserva solo la orientación en un eXIf nuevo tras IHDR", () => {
  const exifWithGps = bytes(exifPayload(6).subarray(6)); // TIFF sin "Exif\0\0"
  const original = bytes(PNG_SIG, IHDR, pngChunk("eXIf", exifWithGps), IDAT, IEND);
  const clean = stripMetadata(original, "png");
  assert.ok(!contains(clean, "GPS"));
  const exifChunk = clean.subarray(PNG_SIG.length + IHDR.length);
  assert.equal(String.fromCharCode(...exifChunk.subarray(4, 8)), "eXIf");
  assert.deepEqual(exifChunk.subarray(8, 8 + ORIENTATION_6_TIFF.length), ORIENTATION_6_TIFF);
  assert.ok(contains(clean, bytes(IDAT, IEND)));
});

Deno.test("WebP: conserva solo la orientación en un EXIF nuevo e indica que existe", () => {
  const vp8x = webpChunk("VP8X", Uint8Array.from([0x08, 0, 0, 0, 0, 0, 0, 0, 0, 0]));
  const image = webpChunk("VP8L", Uint8Array.from([1, 2, 3]));
  const clean = stripMetadata(webp(vp8x, image, webpChunk("EXIF", exifPayload(6))), "webp");
  assert.ok(!contains(clean, "GPS"));
  assert.equal(clean[20], 0x08, "VP8X marca que hay EXIF");
  assert.ok(contains(clean, bytes("EXIF", [ORIENTATION_6_TIFF.length, 0, 0, 0], ORIENTATION_6_TIFF)));
  assert.equal(clean[4] | (clean[5] << 8), clean.length - 8);
});
