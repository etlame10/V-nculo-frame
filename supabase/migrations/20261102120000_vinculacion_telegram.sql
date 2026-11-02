-- Fase 5: vincular la cuenta de Telegram de un familiar con un código de un
-- solo uso (D-05: el bot recibe los mensajes en una Edge Function).
--
-- 1. El administrador pide un código para un familiar desde el panel
--    (public.create_link_code). Se le muestra una sola vez.
-- 2. El familiar lo envía al bot. La Edge Function, con service_role, llama a
--    public.redeem_link_code, que vincula su telegram_user_id.
--
-- Solo se guarda el SHA-256 del código. Caduca a las 24 horas, sirve una vez
-- y pedir uno nuevo anula los anteriores del mismo familiar.

create table public.member_link_codes (
    code_hash text primary key check (code_hash ~ '^[0-9a-f]{64}$'),
    member_id uuid not null,
    frame_id uuid not null,
    created_by uuid references auth.users (id) on delete set null,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    used_at timestamptz,
    foreign key (member_id, frame_id)
        references public.family_members (id, frame_id) on delete cascade
);

create index member_link_codes_member_id on public.member_link_codes (member_id);

-- Nadie la lee ni la escribe directamente: solo las dos funciones de abajo.
alter table public.member_link_codes enable row level security;
revoke all on public.member_link_codes from anon, authenticated;

-- Código normalizado: 8 caracteres de un alfabeto sin 0/O, 1/I/L.
create function private.normalize_link_code(p_code text)
returns text
language sql
immutable
set search_path = ''
as $$
    select upper(regexp_replace(coalesce(p_code, ''), '[\s-]', '', 'g'));
$$;

create function private.link_code_hash(p_code text)
returns text
language sql
immutable
set search_path = ''
as $$
    select encode(sha256(convert_to(private.normalize_link_code(p_code), 'UTF8')), 'hex');
$$;

create function public.create_link_code(p_member_id uuid)
returns table (code text, expires_at timestamptz)
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
    alphabet constant text := 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
    v_frame_id uuid;
    v_random bytea;
    v_code text := '';
    v_expires timestamptz := now() + interval '24 hours';
begin
    select m.frame_id into v_frame_id
    from public.family_members m
    where m.id = p_member_id and m.active;

    -- Mismo error si no existe o no es suyo: no revela qué familiares existen.
    if v_frame_id is null or not private.is_frame_admin(v_frame_id) then
        raise exception 'familiar no encontrado' using errcode = '42501';
    end if;

    -- 16 bytes aleatorios (gen_random_uuid usa el generador seguro del
    -- sistema); el sesgo de módulo 31 es despreciable para este uso.
    v_random := uuid_send(gen_random_uuid());
    for i in 0..7 loop
        v_code := v_code || substr(alphabet, get_byte(v_random, i) % 31 + 1, 1);
    end loop;

    delete from public.member_link_codes c
    where c.member_id = p_member_id and c.used_at is null;

    insert into public.member_link_codes (code_hash, member_id, frame_id, created_by, expires_at)
    values (private.link_code_hash(v_code), p_member_id, v_frame_id, auth.uid(), v_expires);

    return query select substr(v_code, 1, 4) || '-' || substr(v_code, 5, 4), v_expires;
end;
$$;

create function public.redeem_link_code(p_code text, p_telegram_user_id bigint)
returns table (member_id uuid, frame_id uuid, display_name text, frame_name text)
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
    v_code public.member_link_codes%rowtype;
begin
    if p_telegram_user_id is null or p_telegram_user_id <= 0 then
        return;
    end if;

    select c.* into v_code
    from public.member_link_codes c
    join public.family_members m on m.id = c.member_id
    where c.code_hash = private.link_code_hash(p_code)
      and c.used_at is null
      and c.expires_at > now()
      and m.active
    for update of c;

    if not found then
        return;
    end if;

    update public.member_link_codes c set used_at = now()
    where c.code_hash = v_code.code_hash;

    -- Una cuenta de Telegram representa a un solo familiar por marco.
    update public.family_members m set telegram_user_id = null
    where m.frame_id = v_code.frame_id
      and m.telegram_user_id = p_telegram_user_id
      and m.id <> v_code.member_id;

    update public.family_members m set telegram_user_id = p_telegram_user_id
    where m.id = v_code.member_id;

    return query
    select m.id, m.frame_id, m.display_name, f.name
    from public.family_members m
    join public.frames f on f.id = m.frame_id
    where m.id = v_code.member_id;
end;
$$;

revoke all on function private.normalize_link_code(text) from public;
revoke all on function private.link_code_hash(text) from public;
revoke all on function public.create_link_code(uuid) from public, anon;
revoke all on function public.redeem_link_code(text, bigint) from public, anon, authenticated;
grant execute on function public.create_link_code(uuid) to authenticated;
grant execute on function public.redeem_link_code(text, bigint) to service_role;

create index family_members_telegram_user_id
    on public.family_members (telegram_user_id) where telegram_user_id is not null;
