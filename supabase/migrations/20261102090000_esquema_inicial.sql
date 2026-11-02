-- Fase 4: esquema remoto inicial de Vínculo Frame.
--
-- Principios (docs/SEGURIDAD.md, D-06):
--   * RLS activado en todas las tablas; ninguna política para `anon`.
--   * Dos tipos de usuario autenticado:
--       - administrador de un marco (fila en frame_admins), desde el panel web;
--       - usuario dispositivo (frames.device_user_id), la Raspberry Pi.
--   * Las escrituras del bot (fotos entrantes, confirmaciones SOS, vincular
--     Telegram) las hará una función del servidor con service_role, que se
--     salta RLS. Por eso aquí no hay políticas de inserción para esas tablas.
--   * Además de RLS, los permisos por columna limitan QUÉ puede cambiar cada
--     rol (por ejemplo, el marco solo puede tocar photos.liked_at).
--
-- Una migración publicada no se edita: los cambios van en una migración nueva.

-- ---------------------------------------------------------------------------
-- Funciones auxiliares en un esquema privado (no expuesto por la API).
-- SECURITY DEFINER para que las políticas no dependan de los permisos sobre
-- frame_admins/frames, con search_path vacío para evitar suplantaciones.
-- ---------------------------------------------------------------------------

create schema if not exists private;
revoke all on schema private from public;
grant usage on schema private to authenticated;

-- ---------------------------------------------------------------------------
-- Tablas
-- ---------------------------------------------------------------------------

create table public.frames (
    id uuid primary key default gen_random_uuid(),
    name text not null check (char_length(name) between 1 and 80),
    -- Usuario Auth propio del marco (D-06). Uno por marco.
    device_user_id uuid unique references auth.users (id) on delete set null,
    created_at timestamptz not null default now()
);

create table public.frame_admins (
    frame_id uuid not null references public.frames (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (frame_id, user_id)
);

create table public.family_members (
    id uuid primary key default gen_random_uuid(),
    frame_id uuid not null references public.frames (id) on delete cascade,
    display_name text not null check (char_length(display_name) between 1 and 60),
    -- NULL hasta que el familiar vincula su cuenta de Telegram (fase 5).
    telegram_user_id bigint check (telegram_user_id > 0),
    active boolean not null default true,
    created_at timestamptz not null default now(),
    unique (frame_id, telegram_user_id),
    -- Permite claves foráneas que garantizan "mismo marco".
    unique (id, frame_id)
);

create table public.photos (
    -- Es el remote_id de la base de datos local del marco (D-15).
    id uuid primary key default gen_random_uuid(),
    frame_id uuid not null references public.frames (id) on delete cascade,
    sender_member_id uuid,
    -- Ruta en el bucket privado "photos": <frame_id>/<sha256>.<ext>
    storage_path text not null unique,
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    content_type text not null check (content_type in ('image/jpeg', 'image/png', 'image/webp')),
    size_bytes integer not null check (size_bytes > 0),
    received_at timestamptz not null default now(),
    liked_at timestamptz,
    unique (frame_id, sha256),
    check (split_part(storage_path, '/', 1) = frame_id::text),
    -- El remitente debe ser un familiar del mismo marco; si se borra, la foto
    -- se conserva sin remitente.
    foreign key (sender_member_id, frame_id)
        references public.family_members (id, frame_id)
        on delete set null (sender_member_id)
);

create table public.sos_alerts (
    -- Lo genera el marco (uuid4 en sos.py): reenviar la misma alerta es idempotente.
    id uuid primary key,
    frame_id uuid not null references public.frames (id) on delete cascade,
    triggered_at timestamptz not null,
    resolved_at timestamptz,
    resolved_by uuid references auth.users (id) on delete set null,
    created_at timestamptz not null default now(),
    unique (id, frame_id),
    -- resolved_by puede quedar NULL si se borra el usuario, pero nunca hay
    -- quien resuelva sin fecha de resolución.
    check (resolved_by is null or resolved_at is not null)
);

create table public.sos_acks (
    alert_id uuid not null,
    member_id uuid not null,
    frame_id uuid not null,
    acked_at timestamptz not null default now(),
    primary key (alert_id, member_id),
    foreign key (alert_id, frame_id)
        references public.sos_alerts (id, frame_id) on delete cascade,
    foreign key (member_id, frame_id)
        references public.family_members (id, frame_id) on delete cascade
);

create index frame_admins_user_id on public.frame_admins (user_id);
create index family_members_frame_id on public.family_members (frame_id);
create index photos_frame_id_received_at on public.photos (frame_id, received_at desc);
create index photos_sender_member_id on public.photos (sender_member_id);
create index sos_alerts_frame_id_triggered_at on public.sos_alerts (frame_id, triggered_at desc);
create index sos_acks_frame_id on public.sos_acks (frame_id);
create index sos_acks_member_id on public.sos_acks (member_id);

-- ---------------------------------------------------------------------------
-- Funciones auxiliares de autorización
-- ---------------------------------------------------------------------------

create function private.is_frame_admin(p_frame_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from public.frame_admins a
        where a.frame_id = p_frame_id
          and a.user_id = (select auth.uid())
    );
$$;

create function private.is_frame_device(p_frame_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from public.frames f
        where f.id = p_frame_id
          and f.device_user_id = (select auth.uid())
    );
$$;

-- Primer segmento de una ruta de Storage como uuid; NULL si no lo es
-- (una ruta mal formada nunca da acceso ni provoca un error).
create function private.frame_id_from_path(p_name text)
returns uuid
language sql
immutable
set search_path = ''
as $$
    select case
        when split_part(p_name, '/', 1) ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            then split_part(p_name, '/', 1)::uuid
    end;
$$;

revoke all on function private.is_frame_admin(uuid) from public;
revoke all on function private.is_frame_device(uuid) from public;
revoke all on function private.frame_id_from_path(text) from public;
grant execute on function private.is_frame_admin(uuid) to authenticated;
grant execute on function private.is_frame_device(uuid) to authenticated;
grant execute on function private.frame_id_from_path(text) to authenticated;

-- ---------------------------------------------------------------------------
-- Permisos de tabla y columna. Supabase concede por defecto todo a anon y
-- authenticated en public; se retira y se concede solo lo necesario.
-- ---------------------------------------------------------------------------

revoke all on public.frames, public.frame_admins, public.family_members,
    public.photos, public.sos_alerts, public.sos_acks
    from anon, authenticated;

grant select on public.frames, public.frame_admins, public.family_members,
    public.photos, public.sos_alerts, public.sos_acks
    to authenticated;

-- Administrador: alta de familiares (nombre) y edición de nombre/activo.
-- telegram_user_id solo lo escribe la vinculación segura (fase 5).
grant insert (frame_id, display_name) on public.family_members to authenticated;
grant update (display_name, active) on public.family_members to authenticated;

-- Administrador: borrar fotos de sus marcos.
grant delete on public.photos to authenticated;
-- Marco: marcar "me gusta".
grant update (liked_at) on public.photos to authenticated;

-- Marco: crear alertas. Administrador: resolverlas.
grant insert (id, frame_id, triggered_at) on public.sos_alerts to authenticated;
grant update (resolved_at, resolved_by) on public.sos_alerts to authenticated;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------

alter table public.frames enable row level security;
alter table public.frame_admins enable row level security;
alter table public.family_members enable row level security;
alter table public.photos enable row level security;
alter table public.sos_alerts enable row level security;
alter table public.sos_acks enable row level security;

create policy "frames: leer admin o dispositivo"
    on public.frames for select to authenticated
    using ((select private.is_frame_admin(id)) or device_user_id = (select auth.uid()));

create policy "frame_admins: leer los de mis marcos"
    on public.frame_admins for select to authenticated
    using ((select private.is_frame_admin(frame_id)));

create policy "family_members: leer admin o dispositivo"
    on public.family_members for select to authenticated
    using ((select private.is_frame_admin(frame_id)) or (select private.is_frame_device(frame_id)));

create policy "family_members: alta por admin"
    on public.family_members for insert to authenticated
    with check ((select private.is_frame_admin(frame_id)));

create policy "family_members: edición por admin"
    on public.family_members for update to authenticated
    using ((select private.is_frame_admin(frame_id)))
    with check ((select private.is_frame_admin(frame_id)));

create policy "photos: leer admin o dispositivo"
    on public.photos for select to authenticated
    using ((select private.is_frame_admin(frame_id)) or (select private.is_frame_device(frame_id)));

create policy "photos: borrar admin"
    on public.photos for delete to authenticated
    using ((select private.is_frame_admin(frame_id)));

create policy "photos: me gusta del dispositivo"
    on public.photos for update to authenticated
    using ((select private.is_frame_device(frame_id)))
    with check ((select private.is_frame_device(frame_id)));

create policy "sos_alerts: leer admin o dispositivo"
    on public.sos_alerts for select to authenticated
    using ((select private.is_frame_admin(frame_id)) or (select private.is_frame_device(frame_id)));

create policy "sos_alerts: crear el dispositivo"
    on public.sos_alerts for insert to authenticated
    with check ((select private.is_frame_device(frame_id)));

create policy "sos_alerts: resolver admin"
    on public.sos_alerts for update to authenticated
    using ((select private.is_frame_admin(frame_id)) and resolved_at is null)
    with check (
        (select private.is_frame_admin(frame_id))
        and resolved_at is not null
        and resolved_by = (select auth.uid())
    );

create policy "sos_acks: leer admin o dispositivo"
    on public.sos_acks for select to authenticated
    using ((select private.is_frame_admin(frame_id)) or (select private.is_frame_device(frame_id)));

-- ---------------------------------------------------------------------------
-- Storage: bucket privado "photos" (D-07). Rutas <frame_id>/<sha256>.<ext>.
-- Las subidas las hace la función del bot con service_role.
-- ---------------------------------------------------------------------------

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('photos', 'photos', false, 10485760, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do nothing;

create policy "photos bucket: leer admin o dispositivo"
    on storage.objects for select to authenticated
    using (
        bucket_id = 'photos'
        and (
            (select private.is_frame_admin(private.frame_id_from_path(name)))
            or (select private.is_frame_device(private.frame_id_from_path(name)))
        )
    );

create policy "photos bucket: borrar admin"
    on storage.objects for delete to authenticated
    using (
        bucket_id = 'photos'
        and (select private.is_frame_admin(private.frame_id_from_path(name)))
    );
