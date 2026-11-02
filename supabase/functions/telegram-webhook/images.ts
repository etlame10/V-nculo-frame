// Reconocer el formato real de una imagen y quitarle los metadatos.
//
// Las fotos enviadas desde el móvil como "archivo" conservan EXIF (incluida
// la ubicación GPS), XMP, IPTC y comentarios. Aquí se eliminan sin decodificar
// la imagen: se recorre la estructura del archivo y se copian solo los
// bloques necesarios para mostrarla. La orientación EXIF se conserva en un
// EXIF mínimo nuevo (la galería la usa para girar la foto).
//
// Mismas firmas que src/vinculo_frame/media.py.

export type ImageKind = "jpeg" | "png" | "webp";

export const MIME_BY_KIND: Record<ImageKind, string> = {
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
};

export const EXTENSION_BY_KIND: Record<ImageKind, string> = {
  jpeg: "jpg",
  png: "png",
  webp: "webp",
};

export class InvalidImage extends Error {}

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

function startsWith(data: Uint8Array, prefix: number[], offset = 0): boolean {
  if (data.length < offset + prefix.length) return false;
  return prefix.every((byte, i) => data[offset + i] === byte);
}

function ascii(data: Uint8Array, offset: number, length: number): string {
  return String.fromCharCode(...data.subarray(offset, offset + length));
}

export function detectImageKind(data: Uint8Array): ImageKind | null {
  if (startsWith(data, [0xff, 0xd8, 0xff])) return "jpeg";
  if (startsWith(data, PNG_SIGNATURE)) return "png";
  if (data.length >= 12 && ascii(data, 0, 4) === "RIFF" && ascii(data, 8, 4) === "WEBP") {
    return "webp";
  }
  return null;
}

export function stripMetadata(data: Uint8Array, kind: ImageKind): Uint8Array {
  switch (kind) {
    case "jpeg":
      return stripJpeg(data);
    case "png":
      return stripPng(data);
    case "webp":
      return stripWebp(data);
  }
}

function concat(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

// --- JPEG --------------------------------------------------------------------

const EXIF_HEADER = [0x45, 0x78, 0x69, 0x66, 0x00, 0x00]; // "Exif\0\0"
const ICC_HEADER = [...new TextEncoder().encode("ICC_PROFILE"), 0x00];

function stripJpeg(data: Uint8Array): Uint8Array {
  const kept: Uint8Array[] = [data.subarray(0, 2)]; // SOI
  let orientation = 1;
  let insertAt = 1; // índice en `kept` donde irá el EXIF mínimo
  let pos = 2;

  while (true) {
    if (pos + 1 >= data.length) throw new InvalidImage("JPEG truncado");
    if (data[pos] !== 0xff) throw new InvalidImage("JPEG mal formado");
    let marker = data[pos + 1];
    let start = pos;
    while (marker === 0xff) {
      // Bytes de relleno entre segmentos.
      pos++;
      start = pos;
      if (pos + 1 >= data.length) throw new InvalidImage("JPEG truncado");
      marker = data[pos + 1];
    }
    if (marker === 0xd9) {
      kept.push(data.subarray(start, pos + 2)); // EOI sin imagen
      break;
    }
    if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
      kept.push(data.subarray(start, pos + 2));
      pos += 2;
      continue;
    }
    if (pos + 3 >= data.length) throw new InvalidImage("JPEG truncado");
    const length = (data[pos + 2] << 8) | data[pos + 3];
    if (length < 2 || pos + 2 + length > data.length) {
      throw new InvalidImage("JPEG con un segmento de longitud inválida");
    }
    const end = pos + 2 + length;
    const payload = data.subarray(pos + 4, end);

    if (marker === 0xda) {
      // Inicio de los datos de imagen: el resto se copia tal cual.
      kept.push(data.subarray(start));
      break;
    }

    let keep: boolean;
    if (marker === 0xe1) {
      if (startsWith(payload, EXIF_HEADER)) {
        orientation = readExifOrientation(payload.subarray(6)) ?? orientation;
      }
      keep = false; // EXIF (GPS, cámara, fechas) y XMP
    } else if (marker === 0xe2) {
      keep = startsWith(payload, ICC_HEADER); // perfil de color
    } else if (marker === 0xe0 || marker === 0xee) {
      keep = true; // JFIF y Adobe (necesario para decodificar CMYK)
    } else if (marker >= 0xe3 && marker <= 0xef) {
      keep = false; // otros APPn, incluido IPTC (APP13)
    } else if (marker === 0xfe) {
      keep = false; // comentarios
    } else {
      keep = true; // tablas, cabecera de imagen, etc.
    }
    if (keep) {
      kept.push(data.subarray(start, end));
      if (marker === 0xe0 && kept.length === 2) insertAt = 2; // EXIF tras JFIF
    }
    pos = end;
  }

  if (orientation !== 1) kept.splice(insertAt, 0, minimalExifSegment(orientation));
  return concat(kept);
}

// Lee la etiqueta Orientation (0x0112) del IFD0 de un bloque TIFF.
function readExifOrientation(tiff: Uint8Array): number | null {
  if (tiff.length < 8) return null;
  const order = ascii(tiff, 0, 2);
  if (order !== "II" && order !== "MM") return null;
  const view = new DataView(tiff.buffer, tiff.byteOffset, tiff.byteLength);
  const little = order === "II";
  const ifd = view.getUint32(4, little);
  if (ifd + 2 > tiff.length) return null;
  const count = view.getUint16(ifd, little);
  for (let i = 0; i < count; i++) {
    const entry = ifd + 2 + i * 12;
    if (entry + 12 > tiff.length) return null;
    if (view.getUint16(entry, little) === 0x0112 && view.getUint16(entry + 2, little) === 3) {
      const value = view.getUint16(entry + 8, little);
      return value >= 1 && value <= 8 ? value : null;
    }
  }
  return null;
}

// TIFF (el contenido de un EXIF) con una sola etiqueta: la orientación.
function minimalTiff(orientation: number): Uint8Array {
  // deno-fmt-ignore
  return Uint8Array.from([
    0x4d, 0x4d, 0x00, 0x2a, 0x00, 0x00, 0x00, 0x08, // "MM", 42, IFD0 en 8
    0x00, 0x01, // 1 entrada
    0x01, 0x12, 0x00, 0x03, 0x00, 0x00, 0x00, 0x01, // Orientation, SHORT, 1
    0x00, orientation, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, // no hay más IFD
  ]);
}

// APP1 con un EXIF que solo contiene la orientación.
function minimalExifSegment(orientation: number): Uint8Array {
  const payload = concat([Uint8Array.from(EXIF_HEADER), minimalTiff(orientation)]);
  const length = payload.length + 2;
  return concat([Uint8Array.from([0xff, 0xe1, length >> 8, length & 0xff]), payload]);
}

// En PNG y WebP el bloque EXIF es un TIFF, a veces precedido de "Exif\0\0".
function orientationFromExifChunk(payload: Uint8Array): number | null {
  return readExifOrientation(startsWith(payload, EXIF_HEADER) ? payload.subarray(6) : payload);
}

// --- PNG ---------------------------------------------------------------------

const PNG_METADATA_CHUNKS = new Set(["eXIf", "tEXt", "iTXt", "zTXt", "tIME"]);

function stripPng(data: Uint8Array): Uint8Array {
  const kept: Uint8Array[] = [data.subarray(0, 8)];
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  let orientation = 1;
  let pos = 8;
  while (true) {
    if (pos + 8 > data.length) throw new InvalidImage("PNG truncado");
    const length = view.getUint32(pos);
    const type = ascii(data, pos + 4, 4);
    const end = pos + 12 + length;
    if (end > data.length) throw new InvalidImage("PNG con un bloque de longitud inválida");
    if (type === "eXIf") {
      orientation = orientationFromExifChunk(data.subarray(pos + 8, end - 4)) ?? orientation;
    }
    if (!PNG_METADATA_CHUNKS.has(type)) kept.push(data.subarray(pos, end));
    pos = end;
    if (type === "IEND") break;
  }
  // eXIf mínimo justo después de IHDR (primer bloque), antes de los datos.
  if (orientation !== 1 && kept.length > 1) kept.splice(2, 0, pngChunk("eXIf", minimalTiff(orientation)));
  return concat(kept);
}

function pngChunk(type: string, body: Uint8Array): Uint8Array {
  const chunk = new Uint8Array(12 + body.length);
  const view = new DataView(chunk.buffer);
  view.setUint32(0, body.length);
  chunk.set(new TextEncoder().encode(type), 4);
  chunk.set(body, 8);
  view.setUint32(8 + body.length, crc32(chunk.subarray(4, 8 + body.length)));
  return chunk;
}

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

// --- WebP --------------------------------------------------------------------

function stripWebp(data: Uint8Array): Uint8Array {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const riffEnd = 8 + view.getUint32(4, true);
  if (riffEnd > data.length) throw new InvalidImage("WebP truncado");
  const kept: Uint8Array[] = [];
  let vp8x: Uint8Array | null = null;
  let orientation = 1;
  let pos = 12;
  while (pos < riffEnd) {
    if (pos + 8 > riffEnd) throw new InvalidImage("WebP con un bloque truncado");
    const type = ascii(data, pos, 4);
    const size = view.getUint32(pos + 4, true);
    const end = pos + 8 + size + (size % 2);
    if (end > riffEnd) throw new InvalidImage("WebP con un bloque de longitud inválida");
    if (type === "VP8X") {
      vp8x = data.slice(pos, end);
      vp8x[8] &= ~(0x08 | 0x04); // de momento, sin EXIF ni XMP
      kept.push(vp8x);
    } else if (type === "EXIF") {
      orientation = orientationFromExifChunk(data.subarray(pos + 8, pos + 8 + size)) ?? orientation;
    } else if (type !== "XMP ") {
      kept.push(data.subarray(pos, end));
    }
    pos = end;
  }
  // El EXIF de WebP solo es válido con VP8X; va al final, tras la imagen.
  if (orientation !== 1 && vp8x !== null) {
    const tiff = minimalTiff(orientation);
    const header = new Uint8Array(8);
    header.set(new TextEncoder().encode("EXIF"), 0);
    new DataView(header.buffer).setUint32(4, tiff.length, true);
    kept.push(header, tiff, new Uint8Array(tiff.length % 2));
    vp8x[8] |= 0x08;
  }
  const body = concat(kept);
  const header = new Uint8Array(12);
  header.set(data.subarray(0, 4), 0);
  new DataView(header.buffer).setUint32(4, body.length + 4, true);
  header.set(data.subarray(8, 12), 8);
  return concat([header, body]);
}
