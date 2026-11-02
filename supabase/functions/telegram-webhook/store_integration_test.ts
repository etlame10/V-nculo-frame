// store.ts contra un Supabase LOCAL (supabase start), nunca contra un
// proyecto real. Se omite si no están SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY
// o si SUPABASE_URL no es local. En CI lo ejecuta scripts/test_functions_e2e.sh.
import { strict as assert } from "node:assert";
import { createClient } from "@supabase/supabase-js";
import { sha256Hex } from "./handler.ts";
import { supabaseStore } from "./store.ts";

const url = Deno.env.get("SUPABASE_URL") ?? "";
const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const isLocal = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(url);
const ignore = !url || !key || !isLocal;

const FRAME = crypto.randomUUID();
const MEMBER = crypto.randomUUID();
const TELEGRAM_ID = 900_000_000 + Math.floor(Math.random() * 1_000_000);

Deno.test({
  name: "store.ts con Supabase local: miembros, códigos y fotos",
  ignore,
  sanitizeOps: false,
  sanitizeResources: false,
  async fn() {
    const client = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
    const store = supabaseStore(client);
    const must = <T>(result: { data: T; error: { message: string } | null }): T => {
      if (result.error) throw new Error(result.error.message);
      return result.data;
    };

    must(await client.from("frames").insert({ id: FRAME, name: "Marco de prueba" }));
    must(await client.from("family_members").insert({ id: MEMBER, frame_id: FRAME, display_name: "Ana" }));
    try {
      assert.deepEqual(await store.activeMemberships(TELEGRAM_ID), [], "aún no vinculada");

      // Código como lo deja create_link_code: solo su SHA-256.
      must(
        await client.from("member_link_codes").insert({
          code_hash: await sha256Hex(new TextEncoder().encode("ABCD2345")),
          member_id: MEMBER,
          frame_id: FRAME,
          expires_at: new Date(Date.now() + 3600_000).toISOString(),
        }),
      );
      assert.deepEqual(await store.redeemLinkCode("abcd-2345", TELEGRAM_ID), {
        displayName: "Ana",
        frameName: "Marco de prueba",
      });
      assert.equal(await store.redeemLinkCode("abcd-2345", TELEGRAM_ID), null, "un solo uso");

      const memberships = await store.activeMemberships(TELEGRAM_ID);
      assert.deepEqual(memberships, [{ memberId: MEMBER, frameId: FRAME, frameName: "Marco de prueba" }]);

      const bytes = Uint8Array.from([0xff, 0xd8, 0xff, 0xd9]);
      const photo = { bytes, kind: "jpeg" as const, sha256: await sha256Hex(bytes) };
      assert.equal(await store.savePhoto(memberships[0], photo), "saved");
      assert.equal(await store.savePhoto(memberships[0], photo), "duplicate", "reintento de Telegram");

      const rows = must(
        await client.from("photos").select("storage_path, sender_member_id, content_type")
          .eq("frame_id", FRAME),
      );
      assert.deepEqual(rows, [{
        storage_path: `${FRAME}/${photo.sha256}.jpg`,
        sender_member_id: MEMBER,
        content_type: "image/jpeg",
      }]);
      const stored = must(await client.storage.from("photos").download(`${FRAME}/${photo.sha256}.jpg`));
      assert.ok(stored, "el archivo está en el bucket");
      assert.deepEqual(new Uint8Array(await stored.arrayBuffer()), bytes);

      must(await client.from("family_members").update({ active: false }).eq("id", MEMBER));
      assert.deepEqual(await store.activeMemberships(TELEGRAM_ID), [], "desactivada = sin acceso");
    } finally {
      const { data: objects } = await client.storage.from("photos").list(FRAME);
      if (objects?.length) {
        await client.storage.from("photos").remove(objects.map((o) => `${FRAME}/${o.name}`));
      }
      await client.from("frames").delete().eq("id", FRAME);
    }
  },
});
