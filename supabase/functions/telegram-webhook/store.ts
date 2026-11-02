// Acceso a Supabase con service_role, solo desde esta función del servidor
// (D-06): nunca en la Raspberry Pi ni en el navegador.

import type { SupabaseClient } from "@supabase/supabase-js";
import { EXTENSION_BY_KIND, MIME_BY_KIND } from "./images.ts";
import type { CleanPhoto, LinkResult, Membership, Store } from "./handler.ts";

const BUCKET = "photos";

export function supabaseStore(client: SupabaseClient): Store {
  return {
    async redeemLinkCode(code: string, telegramUserId: number): Promise<LinkResult | null> {
      const { data, error } = await client.rpc("redeem_link_code", {
        p_code: code,
        p_telegram_user_id: telegramUserId,
      });
      if (error) throw new Error(`redeem_link_code: ${error.message}`);
      const row = Array.isArray(data) ? data[0] : null;
      return row ? { displayName: row.display_name, frameName: row.frame_name } : null;
    },

    async activeMemberships(telegramUserId: number): Promise<Membership[]> {
      const { data, error } = await client
        .from("family_members")
        .select("id, frame_id, frames(name)")
        .eq("telegram_user_id", telegramUserId)
        .eq("active", true);
      if (error) throw new Error(`family_members: ${error.message}`);
      return (data ?? []).map((row: { id: string; frame_id: string; frames: unknown }) => ({
        memberId: row.id,
        frameId: row.frame_id,
        frameName: (row.frames as { name: string } | null)?.name ?? "",
      }));
    },

    async savePhoto(membership: Membership, photo: CleanPhoto): Promise<"saved" | "duplicate"> {
      const path = `${membership.frameId}/${photo.sha256}.${EXTENSION_BY_KIND[photo.kind]}`;
      const upload = await client.storage.from(BUCKET).upload(path, photo.bytes, {
        contentType: MIME_BY_KIND[photo.kind],
        upsert: false,
      });
      // Si el archivo ya existe (reintento de Telegram), se sigue con la fila.
      if (upload.error && !/exists|duplicate/i.test(upload.error.message)) {
        throw new Error(`storage: ${upload.error.message}`);
      }
      const { data, error } = await client
        .from("photos")
        .upsert(
          {
            frame_id: membership.frameId,
            sender_member_id: membership.memberId,
            storage_path: path,
            sha256: photo.sha256,
            content_type: MIME_BY_KIND[photo.kind],
            size_bytes: photo.bytes.length,
          },
          { onConflict: "frame_id,sha256", ignoreDuplicates: true },
        )
        .select("id");
      if (error) throw new Error(`photos: ${error.message}`);
      return data && data.length > 0 ? "saved" : "duplicate";
    },
  };
}
