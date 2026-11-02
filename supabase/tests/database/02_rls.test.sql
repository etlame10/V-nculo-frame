-- Quién puede ver y cambiar qué (RLS + permisos por columna), fase 4.
--
-- Dos marcos (A y B), cada uno con su administrador y su usuario dispositivo,
-- y un usuario autenticado sin relación con ninguno. Cada bloque actúa como
-- uno de ellos y comprueba que solo alcanza lo suyo.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

-- Actuar como un usuario: rol authenticated + "sub" en los claims, como
-- hace la API de Supabase. reset role vuelve a postgres.
create function pg_temp.como(p_user uuid) returns void
language sql as $$
    select set_config('request.jwt.claims',
                      json_build_object('sub', p_user, 'role', 'authenticated')::text, true);
    select set_config('role', 'authenticated', true);
$$;

-- Datos (como postgres) --------------------------------------------------------

insert into auth.users (id, email) values
    ('00000000-0000-4000-8000-0000000000a1', 'admin-a@example.invalid'),
    ('00000000-0000-4000-8000-0000000000a2', 'marco-a@example.invalid'),
    ('00000000-0000-4000-8000-0000000000b1', 'admin-b@example.invalid'),
    ('00000000-0000-4000-8000-0000000000b2', 'marco-b@example.invalid'),
    ('00000000-0000-4000-8000-0000000000c1', 'ajeno@example.invalid');

insert into public.frames (id, name, device_user_id) values
    ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Marco A', '00000000-0000-4000-8000-0000000000a2'),
    ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'Marco B', '00000000-0000-4000-8000-0000000000b2');

insert into public.frame_admins (frame_id, user_id) values
    ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '00000000-0000-4000-8000-0000000000a1'),
    ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', '00000000-0000-4000-8000-0000000000b1');

insert into public.family_members (id, frame_id, display_name, telegram_user_id) values
    ('a0000000-0000-4000-8000-000000000001', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Ana', 1001),
    ('b0000000-0000-4000-8000-000000000001', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'Benito', 2001);

insert into public.photos (id, frame_id, sender_member_id, storage_path, sha256, content_type, size_bytes) values
    ('a0000000-0000-4000-8000-000000000101', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
     'a0000000-0000-4000-8000-000000000001',
     'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/' || repeat('a', 64) || '.jpg', repeat('a', 64), 'image/jpeg', 100),
    ('a0000000-0000-4000-8000-000000000102', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
     'a0000000-0000-4000-8000-000000000001',
     'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/' || repeat('c', 64) || '.jpg', repeat('c', 64), 'image/jpeg', 100),
    ('b0000000-0000-4000-8000-000000000101', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
     'b0000000-0000-4000-8000-000000000001',
     'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/' || repeat('b', 64) || '.png', repeat('b', 64), 'image/png', 100);

insert into public.sos_alerts (id, frame_id, triggered_at) values
    ('a0000000-0000-4000-8000-000000000201', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', now()),
    ('b0000000-0000-4000-8000-000000000201', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', now());

insert into public.sos_acks (alert_id, member_id, frame_id) values
    ('a0000000-0000-4000-8000-000000000201', 'a0000000-0000-4000-8000-000000000001', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    ('b0000000-0000-4000-8000-000000000201', 'b0000000-0000-4000-8000-000000000001', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');

insert into storage.objects (bucket_id, name) values
    ('photos', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/' || repeat('a', 64) || '.jpg'),
    ('photos', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/' || repeat('b', 64) || '.png'),
    ('photos', 'sin-marco/' || repeat('d', 64) || '.jpg');

-- anon ------------------------------------------------------------------------

set local role anon;
select set_config('request.jwt.claims', '{"role":"anon"}', true);

select throws_ok('select * from public.frames', '42501', null, 'anon: no puede leer frames');
select throws_ok('select * from public.family_members', '42501', null, 'anon: no puede leer familiares');
select throws_ok('select * from public.photos', '42501', null, 'anon: no puede leer fotos');
select throws_ok('select * from public.sos_alerts', '42501', null, 'anon: no puede leer alertas');
select throws_ok(
    $$insert into public.sos_alerts (id, frame_id, triggered_at)
      values (gen_random_uuid(), 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', now())$$,
    '42501', null, 'anon: no puede crear alertas'
);
select is((select count(*)::int from storage.objects), 0, 'anon: no ve ningún archivo del bucket');

reset role;

-- Usuario autenticado sin relación con ningún marco ---------------------------

select pg_temp.como('00000000-0000-4000-8000-0000000000c1');

select is((select count(*)::int from public.frames), 0, 'ajeno: no ve marcos');
select is((select count(*)::int from public.family_members), 0, 'ajeno: no ve familiares');
select is((select count(*)::int from public.photos), 0, 'ajeno: no ve fotos');
select is((select count(*)::int from public.sos_alerts), 0, 'ajeno: no ve alertas');
select is((select count(*)::int from storage.objects), 0, 'ajeno: no ve archivos');
select throws_ok(
    $$insert into public.family_members (frame_id, display_name)
      values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Intruso')$$,
    '42501', null, 'ajeno: no puede añadir familiares'
);

reset role;

-- Administrador del marco A ----------------------------------------------------

select pg_temp.como('00000000-0000-4000-8000-0000000000a1');

select is(
    (select array_agg(id) from public.frames),
    array['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid],
    'admin A: solo ve el marco A'
);
select is(
    (select array_agg(distinct frame_id) from public.frame_admins),
    array['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid],
    'admin A: solo ve los administradores del marco A'
);
select is((select count(*)::int from public.family_members), 1, 'admin A: ve un familiar');
select is(
    (select count(*)::int from public.family_members where frame_id <> 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    0, 'admin A: no ve familiares de B'
);
select is((select count(*)::int from public.photos), 2, 'admin A: ve las 2 fotos de A');
select is((select count(*)::int from public.sos_alerts), 1, 'admin A: ve la alerta de A');
select is((select count(*)::int from public.sos_acks), 1, 'admin A: ve la confirmación de A');
select is(
    (select array_agg(name) from storage.objects),
    array['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/' || repeat('a', 64) || '.jpg'],
    'admin A: en el bucket solo ve los archivos de A (ni B ni rutas sin marco)'
);

select lives_ok(
    $$insert into public.family_members (frame_id, display_name)
      values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Carmen')$$,
    'admin A: añade un familiar a su marco (el id lo pone la base de datos)'
);
select throws_ok(
    $$insert into public.family_members (id, frame_id, display_name)
      values (gen_random_uuid(), 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Elegido')$$,
    '42501', null, 'admin A: no elige el id de un familiar'
);
select throws_ok(
    $$insert into public.family_members (frame_id, display_name)
      values ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'Intruso')$$,
    '42501', null, 'admin A: no puede añadir familiares al marco B'
);
select throws_ok(
    $$insert into public.family_members (frame_id, display_name, telegram_user_id)
      values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Atajo', 3001)$$,
    '42501', null, 'admin A: no puede fijar telegram_user_id (solo la vinculación segura)'
);
select throws_ok(
    $$update public.family_members set telegram_user_id = 9999
      where id = 'a0000000-0000-4000-8000-000000000001'$$,
    '42501', null, 'admin A: no puede cambiar el telegram_user_id de un familiar'
);
select throws_ok(
    $$update public.family_members set frame_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
      where id = 'a0000000-0000-4000-8000-000000000001'$$,
    '42501', null, 'admin A: no puede mover un familiar a otro marco'
);
select throws_ok(
    $$delete from public.family_members where id = 'a0000000-0000-4000-8000-000000000001'$$,
    '42501', null, 'admin A: los familiares se desactivan, no se borran'
);

update public.family_members set active = false where id = 'a0000000-0000-4000-8000-000000000001';
update public.family_members set display_name = 'Pirata' where id = 'b0000000-0000-4000-8000-000000000001';
update public.photos set liked_at = now() where id = 'a0000000-0000-4000-8000-000000000101';
delete from public.photos where id = 'b0000000-0000-4000-8000-000000000101';
delete from public.photos where id = 'a0000000-0000-4000-8000-000000000102';

select throws_ok(
    $$update public.sos_alerts set resolved_at = now(), resolved_by = '00000000-0000-4000-8000-0000000000c1'
      where id = 'a0000000-0000-4000-8000-000000000201'$$,
    '42501', null, 'admin A: al resolver no puede firmar como otra persona'
);
update public.sos_alerts set resolved_at = now(), resolved_by = '00000000-0000-4000-8000-0000000000b1'
    where id = 'b0000000-0000-4000-8000-000000000201';
update public.sos_alerts set resolved_at = now(), resolved_by = '00000000-0000-4000-8000-0000000000a1'
    where id = 'a0000000-0000-4000-8000-000000000201';

-- Lo que ve el administrador A al borrar en el bucket coincide con la política.
select is(
    (select count(*)::int from storage.objects
     where bucket_id = 'photos' and private.is_frame_admin(private.frame_id_from_path(name))),
    1, 'admin A: la condición de borrado del bucket solo cubre archivos de A'
);

reset role;

select is(
    (select active from public.family_members where id = 'a0000000-0000-4000-8000-000000000001'),
    false, 'admin A: desactivó a un familiar de su marco'
);
select is(
    (select display_name from public.family_members where id = 'b0000000-0000-4000-8000-000000000001'),
    'Benito', 'admin A: no pudo renombrar a un familiar de B'
);
select is(
    (select liked_at from public.photos where id = 'a0000000-0000-4000-8000-000000000101'),
    null, 'admin A: no puede marcar "me gusta" (solo el marco)'
);
select ok(
    exists (select 1 from public.photos where id = 'b0000000-0000-4000-8000-000000000101'),
    'admin A: no pudo borrar la foto de B'
);
select ok(
    not exists (select 1 from public.photos where id = 'a0000000-0000-4000-8000-000000000102'),
    'admin A: borró una foto de su marco'
);
select is(
    (select resolved_at from public.sos_alerts where id = 'b0000000-0000-4000-8000-000000000201'),
    null, 'admin A: no pudo resolver la alerta de B'
);
select is(
    (select resolved_by from public.sos_alerts where id = 'a0000000-0000-4000-8000-000000000201'),
    '00000000-0000-4000-8000-0000000000a1'::uuid, 'admin A: resolvió la alerta de A con su usuario'
);

-- Una alerta ya resuelta no se vuelve a resolver.
select pg_temp.como('00000000-0000-4000-8000-0000000000a1');
update public.sos_alerts set resolved_at = now() + interval '1 day'
    where id = 'a0000000-0000-4000-8000-000000000201';
reset role;
select ok(
    (select resolved_at < now() + interval '1 hour' from public.sos_alerts
     where id = 'a0000000-0000-4000-8000-000000000201'),
    'admin A: no puede cambiar la resolución de una alerta ya resuelta'
);

-- Usuario dispositivo del marco A ----------------------------------------------

select pg_temp.como('00000000-0000-4000-8000-0000000000a2');

select is(
    (select array_agg(id) from public.frames),
    array['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid],
    'marco A: solo ve su marco'
);
select is((select count(*)::int from public.frame_admins), 0, 'marco A: no ve quién administra');
select is(
    (select count(*)::int from public.family_members where frame_id <> 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    0, 'marco A: no ve familiares de B'
);
select is((select count(*)::int from public.family_members), 2, 'marco A: ve los familiares de su marco');
select is((select count(*)::int from public.photos), 1, 'marco A: ve la foto que queda en A');
select is((select count(*)::int from public.sos_acks), 1, 'marco A: ve las confirmaciones de A');
select is(
    (select array_agg(name) from storage.objects),
    array['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/' || repeat('a', 64) || '.jpg'],
    'marco A: en el bucket solo ve sus archivos'
);
select is(
    (select count(*)::int from storage.objects
     where bucket_id = 'photos' and private.is_frame_admin(private.frame_id_from_path(name))),
    0, 'marco A: la condición de borrado del bucket no le cubre'
);

select lives_ok(
    $$insert into public.sos_alerts (id, frame_id, triggered_at)
      values ('a0000000-0000-4000-8000-000000000202', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', now())$$,
    'marco A: crea una alerta SOS'
);
select throws_ok(
    $$insert into public.sos_alerts (id, frame_id, triggered_at)
      values ('a0000000-0000-4000-8000-000000000202', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', now())$$,
    '23505', null, 'marco A: reenviar la misma alerta no la duplica'
);
select throws_ok(
    $$insert into public.sos_alerts (id, frame_id, triggered_at)
      values (gen_random_uuid(), 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', now())$$,
    '42501', null, 'marco A: no puede crear alertas para el marco B'
);
select throws_ok(
    $$insert into public.sos_alerts (id, frame_id, triggered_at, resolved_at)
      values (gen_random_uuid(), 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', now(), now())$$,
    '42501', null, 'marco A: no puede crear una alerta ya resuelta'
);
select throws_ok(
    $$insert into public.family_members (frame_id, display_name)
      values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Nuevo')$$,
    '42501', null, 'marco A: no puede añadir familiares'
);
select throws_ok(
    $$update public.photos set storage_path = 'otra/ruta.jpg'
      where id = 'a0000000-0000-4000-8000-000000000101'$$,
    '42501', null, 'marco A: no puede cambiar la ruta de una foto'
);

update public.photos set liked_at = now() where id = 'a0000000-0000-4000-8000-000000000101';
update public.photos set liked_at = now() where id = 'b0000000-0000-4000-8000-000000000101';
delete from public.photos where id = 'a0000000-0000-4000-8000-000000000101';
update public.sos_alerts set resolved_at = now(), resolved_by = '00000000-0000-4000-8000-0000000000a2'
    where id = 'a0000000-0000-4000-8000-000000000202';
update public.family_members set display_name = 'Cambiado' where display_name = 'Carmen';

reset role;

select isnt(
    (select liked_at from public.photos where id = 'a0000000-0000-4000-8000-000000000101'),
    null, 'marco A: marcó "me gusta" en su foto'
);
select is(
    (select liked_at from public.photos where id = 'b0000000-0000-4000-8000-000000000101'),
    null, 'marco A: no pudo marcar "me gusta" en una foto de B'
);
select ok(
    exists (select 1 from public.photos where id = 'a0000000-0000-4000-8000-000000000101'),
    'marco A: no puede borrar fotos'
);
select is(
    (select resolved_at from public.sos_alerts where id = 'a0000000-0000-4000-8000-000000000202'),
    null, 'marco A: no puede resolver alertas (decisión pendiente D-08)'
);
select is(
    (select count(*)::int from public.family_members where display_name = 'Carmen'),
    1, 'marco A: no puede editar familiares'
);

-- Usuario dispositivo del marco B no ve nada de A -------------------------------

select pg_temp.como('00000000-0000-4000-8000-0000000000b2');
select is(
    (select count(*)::int from public.photos where frame_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    0, 'marco B: no ve fotos de A'
);
select is(
    (select count(*)::int from public.sos_alerts where frame_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    0, 'marco B: no ve alertas de A'
);
reset role;

select * from finish();
rollback;
