-- Imitación mínima de Supabase para probar las migraciones en un PostgreSQL
-- normal (scripts/test_db.sh), cuando no se puede usar `supabase start`.
-- Está fuera de supabase/tests para que `supabase test db` no la ejecute.
--
-- Solo reproduce lo que usan las migraciones y las pruebas:
--   * roles anon, authenticated y service_role (este último se salta RLS);
--   * auth.users y auth.uid(), que lee el "sub" de request.jwt.claims igual
--     que Supabase;
--   * storage.buckets y storage.objects con RLS activado;
--   * los permisos por defecto que Supabase da en el esquema public.
--
-- NO se usa nunca contra un proyecto real. La prueba de referencia es
-- `supabase test db` (job "supabase" de GitHub Actions).

create role anon nologin noinherit;
create role authenticated nologin noinherit;
create role service_role nologin noinherit bypassrls;

create schema extensions;
create extension pgtap with schema extensions;
grant usage on schema extensions to anon, authenticated, service_role;

grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public
    grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public
    grant all on functions to anon, authenticated, service_role;
alter default privileges in schema public
    grant all on sequences to anon, authenticated, service_role;

-- auth ----------------------------------------------------------------------

create schema auth;
grant usage on schema auth to anon, authenticated, service_role;

create table auth.users (
    id uuid primary key,
    email text,
    created_at timestamptz not null default now()
);

create function auth.uid() returns uuid
language sql stable
as $$
    select coalesce(
        nullif(current_setting('request.jwt.claim.sub', true), ''),
        (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
    )::uuid;
$$;

create function auth.role() returns text
language sql stable
as $$
    select coalesce(
        nullif(current_setting('request.jwt.claim.role', true), ''),
        (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role')
    );
$$;

grant execute on function auth.uid() to anon, authenticated, service_role;
grant execute on function auth.role() to anon, authenticated, service_role;

-- storage -------------------------------------------------------------------

create schema storage;
grant usage on schema storage to anon, authenticated, service_role;

create table storage.buckets (
    id text primary key,
    name text not null unique,
    owner uuid,
    public boolean default false,
    file_size_limit bigint,
    allowed_mime_types text[],
    created_at timestamptz default now()
);

create table storage.objects (
    id uuid primary key default gen_random_uuid(),
    bucket_id text references storage.buckets (id),
    name text,
    owner uuid,
    created_at timestamptz default now(),
    metadata jsonb,
    unique (bucket_id, name)
);

alter table storage.buckets enable row level security;
alter table storage.objects enable row level security;
grant all on storage.buckets, storage.objects to anon, authenticated, service_role;
