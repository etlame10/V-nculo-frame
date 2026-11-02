-- Estructura e integridad del esquema remoto (fase 4).
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

-- Tablas y RLS ---------------------------------------------------------------

select tables_are(
    'public',
    array['frames', 'frame_admins', 'family_members', 'photos', 'sos_alerts', 'sos_acks', 'member_link_codes'],
    'solo las tablas previstas en public'
);

select ok(c.relrowsecurity, format('RLS activado en %s', c.relname))
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by c.relname;

-- anon no tiene ningún permiso sobre las tablas (además de no tener políticas).
select ok(
    not has_table_privilege('anon', format('public.%I', c.relname), 'SELECT, INSERT, UPDATE, DELETE'),
    format('anon sin permisos en %s', c.relname)
)
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by c.relname;

-- Ninguna política se aplica a anon ni a public.
select is(
    (select count(*)::int from pg_policies
     where schemaname in ('public', 'storage')
       and (roles && array['anon', 'public']::name[])),
    0,
    'ninguna política para anon o public'
);

select policies_are('public', 'frames', array['frames: leer admin o dispositivo']);
select policies_are('public', 'frame_admins', array['frame_admins: leer los de mis marcos']);
select policies_are('public', 'family_members', array[
    'family_members: leer admin o dispositivo',
    'family_members: alta por admin',
    'family_members: edición por admin'
]);
select policies_are('public', 'photos', array[
    'photos: leer admin o dispositivo',
    'photos: borrar admin',
    'photos: me gusta del dispositivo'
]);
select policies_are('public', 'sos_alerts', array[
    'sos_alerts: leer admin o dispositivo',
    'sos_alerts: crear el dispositivo',
    'sos_alerts: resolver admin'
]);
select policies_are('public', 'sos_acks', array['sos_acks: leer admin o dispositivo']);

-- Permisos por columna: lo que authenticated puede cambiar y nada más.
select ok(
    not has_column_privilege('authenticated', 'public.family_members', 'telegram_user_id', 'INSERT')
    and not has_column_privilege('authenticated', 'public.family_members', 'telegram_user_id', 'UPDATE')
    and not has_column_privilege('authenticated', 'public.family_members', 'frame_id', 'UPDATE'),
    'authenticated no escribe telegram_user_id ni cambia el marco de un familiar'
);
select ok(
    has_column_privilege('authenticated', 'public.photos', 'liked_at', 'UPDATE')
    and not has_column_privilege('authenticated', 'public.photos', 'storage_path', 'UPDATE')
    and not has_column_privilege('authenticated', 'public.photos', 'frame_id', 'UPDATE')
    and not has_table_privilege('authenticated', 'public.photos', 'INSERT'),
    'en photos authenticated solo actualiza liked_at y no inserta'
);
select ok(
    not has_column_privilege('authenticated', 'public.sos_alerts', 'resolved_at', 'INSERT')
    and not has_column_privilege('authenticated', 'public.sos_alerts', 'frame_id', 'UPDATE')
    and not has_table_privilege('authenticated', 'public.sos_alerts', 'DELETE'),
    'sos_alerts: no se crea ya resuelta, no cambia de marco y no se borra'
);
select ok(
    not has_table_privilege('authenticated', 'public.sos_acks', 'INSERT, UPDATE, DELETE')
    and not has_table_privilege('authenticated', 'public.frames', 'INSERT, UPDATE, DELETE')
    and not has_table_privilege('authenticated', 'public.frame_admins', 'INSERT, UPDATE, DELETE'),
    'frames, frame_admins y sos_acks son de solo lectura para authenticated'
);

-- Funciones auxiliares -------------------------------------------------------

select is_definer('private', 'is_frame_admin', array['uuid'], 'is_frame_admin es SECURITY DEFINER');
select is_definer('private', 'is_frame_device', array['uuid'], 'is_frame_device es SECURITY DEFINER');
select ok(
    not has_function_privilege('anon', 'private.is_frame_admin(uuid)', 'EXECUTE')
    and not has_function_privilege('anon', 'private.is_frame_device(uuid)', 'EXECUTE'),
    'anon no puede ejecutar las funciones auxiliares'
);
select ok(
    not has_schema_privilege('anon', 'private', 'USAGE'),
    'el esquema private no es accesible para anon'
);

select is(
    private.frame_id_from_path('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/x.jpg'),
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid,
    'frame_id_from_path lee el primer segmento'
);
select is(private.frame_id_from_path('no-es-un-uuid/x.jpg'), null, 'ruta sin uuid → NULL');
select is(private.frame_id_from_path('../x.jpg'), null, 'ruta con .. → NULL');
select is(private.frame_id_from_path(''), null, 'ruta vacía → NULL');
select is(
    private.frame_id_from_path('AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA/x.jpg'),
    null,
    'solo uuid en minúsculas (como los genera Postgres)'
);

-- Storage --------------------------------------------------------------------

select is(
    (select public from storage.buckets where id = 'photos'),
    false,
    'el bucket photos es privado'
);
select is(
    (select allowed_mime_types from storage.buckets where id = 'photos'),
    array['image/jpeg', 'image/png', 'image/webp'],
    'el bucket photos solo admite JPEG, PNG y WebP'
);

-- Integridad (como postgres, sin RLS) -----------------------------------------

insert into auth.users (id, email) values
    ('00000000-0000-4000-8000-0000000000a1', 'admin-a@example.invalid');
insert into public.frames (id, name) values
    ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Marco A'),
    ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'Marco B');
insert into public.family_members (id, frame_id, display_name) values
    ('a0000000-0000-4000-8000-000000000001', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Ana'),
    ('b0000000-0000-4000-8000-000000000001', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'Benito');
insert into public.sos_alerts (id, frame_id, triggered_at) values
    ('a0000000-0000-4000-8000-000000000201', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', now());

select throws_ok(
    $$insert into public.photos (frame_id, sender_member_id, storage_path, sha256, content_type, size_bytes)
      values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'b0000000-0000-4000-8000-000000000001',
              'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/' || repeat('a', 64) || '.jpg',
              repeat('a', 64), 'image/jpeg', 100)$$,
    '23503', null,
    'una foto no puede tener como remitente a un familiar de otro marco'
);
select throws_ok(
    $$insert into public.photos (frame_id, storage_path, sha256, content_type, size_bytes)
      values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
              'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/' || repeat('a', 64) || '.jpg',
              repeat('a', 64), 'image/jpeg', 100)$$,
    '23514', null,
    'la ruta de la foto empieza por el id de su marco'
);
select throws_ok(
    $$insert into public.photos (frame_id, storage_path, sha256, content_type, size_bytes)
      values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/x.gif',
              repeat('a', 64), 'image/gif', 100)$$,
    '23514', null,
    'formato de imagen no admitido'
);
select throws_ok(
    $$insert into public.photos (frame_id, storage_path, sha256, content_type, size_bytes)
      values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/x.jpg',
              'no-es-un-hash', 'image/jpeg', 100)$$,
    '23514', null,
    'sha256 con formato inválido'
);
select lives_ok(
    $$insert into public.photos (id, frame_id, sender_member_id, storage_path, sha256, content_type, size_bytes)
      values ('a0000000-0000-4000-8000-000000000101', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
              'a0000000-0000-4000-8000-000000000001',
              'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/' || repeat('a', 64) || '.jpg',
              repeat('a', 64), 'image/jpeg', 100)$$,
    'una foto válida se guarda'
);
select throws_ok(
    $$insert into public.photos (frame_id, storage_path, sha256, content_type, size_bytes)
      values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
              'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/' || repeat('a', 64) || '.png',
              repeat('a', 64), 'image/png', 100)$$,
    '23505', null,
    'la misma foto (mismo hash) no se guarda dos veces en un marco'
);

delete from public.family_members where id = 'a0000000-0000-4000-8000-000000000001';
select ok(
    (select sender_member_id is null from public.photos
     where id = 'a0000000-0000-4000-8000-000000000101'),
    'al borrar un familiar sus fotos se conservan sin remitente'
);

select throws_ok(
    $$insert into public.sos_acks (alert_id, member_id, frame_id)
      values ('a0000000-0000-4000-8000-000000000201', 'b0000000-0000-4000-8000-000000000001',
              'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')$$,
    '23503', null,
    'solo confirma una alerta un familiar de su mismo marco'
);
select throws_ok(
    $$update public.sos_alerts set resolved_by = '00000000-0000-4000-8000-0000000000a1'
      where id = 'a0000000-0000-4000-8000-000000000201'$$,
    '23514', null,
    'no hay quien resuelva sin fecha de resolución'
);
select throws_ok(
    $$insert into public.family_members (frame_id, display_name)
      values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '')$$,
    '23514', null,
    'el nombre del familiar no puede estar vacío'
);

select * from finish();
rollback;
