-- Vinculación de Telegram con códigos de un solo uso (fase 5).
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

create function pg_temp.como(p_user uuid) returns void
language sql as $$
    select set_config('request.jwt.claims',
                      json_build_object('sub', p_user, 'role', 'authenticated')::text, true);
    select set_config('role', 'authenticated', true);
$$;

insert into auth.users (id, email) values
    ('00000000-0000-4000-8000-0000000000a1', 'admin-a@example.invalid'),
    ('00000000-0000-4000-8000-0000000000a2', 'marco-a@example.invalid'),
    ('00000000-0000-4000-8000-0000000000b1', 'admin-b@example.invalid');
insert into public.frames (id, name, device_user_id) values
    ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Marco de la abuela', '00000000-0000-4000-8000-0000000000a2'),
    ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'Marco B', null);
insert into public.frame_admins (frame_id, user_id) values
    ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '00000000-0000-4000-8000-0000000000a1'),
    ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', '00000000-0000-4000-8000-0000000000b1');
insert into public.family_members (id, frame_id, display_name, active) values
    ('a0000000-0000-4000-8000-000000000001', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Ana', true),
    ('a0000000-0000-4000-8000-000000000002', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Inactivo', false),
    ('a0000000-0000-4000-8000-000000000003', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'Carlos', true),
    ('b0000000-0000-4000-8000-000000000001', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'Benito', true);

create temp table codigos (nombre text primary key, code text, expires_at timestamptz);
grant all on codigos to authenticated, service_role;

-- Permisos ---------------------------------------------------------------------

select ok(
    not has_function_privilege('anon', 'public.create_link_code(uuid)', 'EXECUTE')
    and not has_function_privilege('anon', 'public.redeem_link_code(text, bigint)', 'EXECUTE')
    and not has_function_privilege('authenticated', 'public.redeem_link_code(text, bigint)', 'EXECUTE')
    and has_function_privilege('service_role', 'public.redeem_link_code(text, bigint)', 'EXECUTE'),
    'solo el servidor (service_role) canjea códigos; anon no crea ni canjea'
);
select ok(
    not has_table_privilege('authenticated', 'public.member_link_codes', 'SELECT, INSERT, UPDATE, DELETE')
    and not has_table_privilege('anon', 'public.member_link_codes', 'SELECT, INSERT, UPDATE, DELETE'),
    'nadie con sesión lee ni escribe la tabla de códigos'
);
select policies_are('public', 'member_link_codes', array[]::name[], 'member_link_codes sin políticas');

-- Crear códigos ----------------------------------------------------------------

select pg_temp.como('00000000-0000-4000-8000-0000000000a1');

insert into codigos select 'ana-1', * from public.create_link_code('a0000000-0000-4000-8000-000000000001');
select matches(
    (select code from codigos where nombre = 'ana-1'),
    '^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{4}-[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{4}$',
    'admin A: obtiene un código XXXX-XXXX sin caracteres confusos'
);
select ok(
    (select expires_at between now() + interval '23 hours' and now() + interval '25 hours'
     from codigos where nombre = 'ana-1'),
    'el código caduca a las 24 horas'
);
select throws_ok(
    $$select public.create_link_code('b0000000-0000-4000-8000-000000000001')$$,
    '42501', 'familiar no encontrado', 'admin A: no puede pedir códigos para familiares de B'
);
select throws_ok(
    $$select public.create_link_code('a0000000-0000-4000-8000-000000000002')$$,
    '42501', 'familiar no encontrado', 'admin A: no hay código para un familiar desactivado'
);
select throws_ok(
    $$select public.create_link_code('a0000000-0000-4000-8000-0000000000ff')$$,
    '42501', 'familiar no encontrado', 'un familiar inexistente da el mismo error'
);
reset role;

select pg_temp.como('00000000-0000-4000-8000-0000000000a2');
select throws_ok(
    $$select public.create_link_code('a0000000-0000-4000-8000-000000000001')$$,
    '42501', 'familiar no encontrado', 'el marco no puede pedir códigos'
);
reset role;

select is(
    (select count(*)::int from public.member_link_codes
     where code_hash = private.link_code_hash((select code from codigos where nombre = 'ana-1'))),
    1, 'se guarda el SHA-256 del código'
);
select is(
    (select count(*)::int from public.member_link_codes
     where code_hash like '%' || replace((select code from codigos where nombre = 'ana-1'), '-', '') || '%'),
    0, 'el código en claro no se guarda'
);

-- Canjear códigos (como la Edge Function) --------------------------------------

set local role service_role;

select is(
    (select count(*)::int from public.redeem_link_code('ZZZZ-ZZZZ', 5001)),
    0, 'un código inventado no vincula nada'
);
select results_eq(
    $$select member_id, frame_id, display_name, frame_name
      from public.redeem_link_code(lower((select code from codigos where nombre = 'ana-1')), 5001)$$,
    $$values ('a0000000-0000-4000-8000-000000000001'::uuid, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid,
              'Ana'::text, 'Marco de la abuela'::text)$$,
    'un código válido (aunque llegue en minúsculas) vincula y dice a qué marco'
);
select is(
    (select count(*)::int from public.redeem_link_code((select code from codigos where nombre = 'ana-1'), 6001)),
    0, 'el mismo código no sirve una segunda vez'
);
reset role;

select is(
    (select telegram_user_id from public.family_members where id = 'a0000000-0000-4000-8000-000000000001'),
    5001::bigint, 'Ana queda vinculada a su cuenta de Telegram'
);

-- Pedir un código nuevo anula el anterior.
select pg_temp.como('00000000-0000-4000-8000-0000000000a1');
insert into codigos select 'carlos-1', * from public.create_link_code('a0000000-0000-4000-8000-000000000003');
insert into codigos select 'carlos-2', * from public.create_link_code('a0000000-0000-4000-8000-000000000003');
reset role;

set local role service_role;
select is(
    (select count(*)::int from public.redeem_link_code((select code from codigos where nombre = 'carlos-1'), 7001)),
    0, 'un código anterior deja de valer al pedir otro'
);
-- Formato con espacios en lugar de guion.
select is(
    (select count(*)::int from public.redeem_link_code(
        replace((select code from codigos where nombre = 'carlos-2'), '-', ' '), 5001)),
    1, 'la cuenta de Ana se vincula ahora como Carlos (otro código válido)'
);
reset role;

select is(
    (select telegram_user_id from public.family_members where id = 'a0000000-0000-4000-8000-000000000001'),
    null, 'una cuenta de Telegram es un solo familiar por marco: Ana queda desvinculada'
);
select is(
    (select telegram_user_id from public.family_members where id = 'a0000000-0000-4000-8000-000000000003'),
    5001::bigint, 'Carlos queda vinculado'
);

-- Códigos caducados o de familiares desactivados.
insert into public.member_link_codes (code_hash, member_id, frame_id, expires_at) values
    (private.link_code_hash('AAAA-BBBB'), 'a0000000-0000-4000-8000-000000000001',
     'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', now() - interval '1 minute'),
    (private.link_code_hash('CCCC-DDDD'), 'a0000000-0000-4000-8000-000000000002',
     'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', now() + interval '1 hour');

set local role service_role;
select is(
    (select count(*)::int from public.redeem_link_code('AAAA-BBBB', 8001)),
    0, 'un código caducado no vincula'
);
select is(
    (select count(*)::int from public.redeem_link_code('CCCC-DDDD', 8001)),
    0, 'el código de un familiar desactivado no vincula'
);
select is(
    (select count(*)::int from public.redeem_link_code('', 8001)),
    0, 'un código vacío no vincula'
);
select is(
    (select count(*)::int from public.redeem_link_code(null, 8001)),
    0, 'un código nulo no vincula'
);
reset role;

select is(
    (select count(*)::int from public.family_members where telegram_user_id = 8001),
    0, 'ningún intento fallido dejó una vinculación'
);

select * from finish();
rollback;
