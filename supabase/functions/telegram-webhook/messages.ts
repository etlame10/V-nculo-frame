// Respuestas del bot. Frases cortas y claras: las leen familiares de todas
// las edades. Nunca incluyen datos de otros familiares ni del marco a quien
// no está autorizado.

export const NOT_AUTHORIZED = "Este bot es privado y usted no está en la lista blanca.";

export const INVALID_CODE =
  "Ese código no es válido o ha caducado. Pide uno nuevo a quien administra el marco.";

export function linked(displayName: string, frameName: string): string {
  return `Hola, ${displayName}. Ya puedes enviar fotos al marco «${frameName}». ` +
    "Envíamelas aquí y aparecerán en la pantalla.";
}

export function help(frameNames: string[]): string {
  return `Envíame una foto y aparecerá en ${frameList(frameNames)}.`;
}

export function photoReceived(frameNames: string[]): string {
  return `✓ Foto recibida. Aparecerá en ${frameList(frameNames)} en unos minutos.`;
}

export const PHOTO_DUPLICATE = "Esta foto ya estaba en el marco.";

export const ONLY_PHOTOS = "Por ahora solo puedo recibir fotos (JPEG, PNG o WebP).";

export function tooLarge(maxMegabytes: number): string {
  return `La foto es demasiado grande. El máximo son ${maxMegabytes} MB.`;
}

export const DAMAGED_PHOTO = "No he podido leer esa foto. Prueba a enviarla otra vez.";

function frameList(frameNames: string[]): string {
  const quoted = frameNames.map((name) => `«${name}»`);
  if (quoted.length === 1) return `el marco ${quoted[0]}`;
  return `los marcos ${quoted.slice(0, -1).join(", ")} y ${quoted.at(-1)}`;
}
