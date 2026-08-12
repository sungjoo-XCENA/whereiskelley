pragma journal_mode = wal;
pragma synchronous = normal;
pragma foreign_keys = on;
pragma busy_timeout = 30000;

create table if not exists merchant_scan_runs (
  id integer primary key,
  phase text not null,
  status text not null default 'running',
  range_start integer,
  range_end integer,
  started_at text not null default current_timestamp,
  finished_at text,
  checked integer not null default 0,
  found integer not null default 0,
  errors integer not null default 0,
  notes text
);

create table if not exists merchant_scan_ids (
  merchant_id integer primary key,
  status text not null,
  http_status integer,
  canonical_url text,
  error text,
  checked_at text not null default current_timestamp
);

create table if not exists merchants (
  id integer primary key,
  wine_searcher_id integer unique,
  wine_searcher_url text,
  name text not null,
  normalized_name text not null default '',
  merchant_type text not null default 'Wine Shop',
  description text,
  website_url text,
  website_domain text,
  country text,
  city text,
  address text,
  latitude real,
  longitude real,
  phone text,
  wine_searcher_item_count integer,
  profile_status text not null default 'found',
  profile_error text,
  first_seen_at text not null default current_timestamp,
  last_seen_at text not null default current_timestamp,
  last_profile_checked_at text,
  last_inventory_checked_at text,
  inventory_status text not null default 'pending',
  inventory_error text,
  active integer not null default 1,
  raw_hash text
);

create table if not exists merchant_sources (
  id integer primary key,
  merchant_id integer not null references merchants(id) on delete cascade,
  source_type text not null default 'html',
  source_url text not null,
  platform text,
  status text not null default 'candidate',
  parser_status text,
  confidence real,
  content_hash text,
  etag text,
  last_modified text,
  item_count integer not null default 0,
  first_seen_at text not null default current_timestamp,
  last_seen_at text not null default current_timestamp,
  last_checked_at text,
  last_success_at text,
  next_crawl_at text,
  error_count integer not null default 0,
  last_error text,
  unique(merchant_id, source_url)
);

create table if not exists merchant_products (
  id integer primary key,
  merchant_id integer not null references merchants(id) on delete cascade,
  source_id integer not null references merchant_sources(id) on delete cascade,
  source_key text not null,
  source_url text,
  raw_name text not null,
  normalized_text text not null,
  producer text,
  wine_name text,
  vintage text,
  region text,
  size_ml integer,
  pack_quantity integer,
  price_value real,
  currency text,
  price_text text,
  price_krw real,
  availability text,
  raw_text text,
  content_hash text,
  active integer not null default 1,
  first_seen_at text not null default current_timestamp,
  last_seen_at text not null default current_timestamp,
  unique(source_id, source_key)
);

create table if not exists merchant_offer_history (
  id integer primary key,
  product_id integer not null references merchant_products(id) on delete cascade,
  observed_at text not null default current_timestamp,
  price_value real,
  currency text,
  availability text,
  content_hash text not null,
  unique(product_id, content_hash)
);

create table if not exists merchant_reviews (
  id integer primary key,
  merchant_id integer references merchants(id) on delete cascade,
  source_id integer references merchant_sources(id) on delete cascade,
  reason text not null,
  detail text,
  status text not null default 'open',
  created_at text not null default current_timestamp,
  resolved_at text
);

create virtual table if not exists merchant_products_fts using fts5(
  raw_name,
  producer,
  wine_name,
  region,
  raw_text,
  content='merchant_products',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);

create trigger if not exists merchant_products_ai after insert on merchant_products begin
  insert into merchant_products_fts(rowid, raw_name, producer, wine_name, region, raw_text)
  values (new.id, new.raw_name, new.producer, new.wine_name, new.region, new.raw_text);
end;

create trigger if not exists merchant_products_ad after delete on merchant_products begin
  insert into merchant_products_fts(merchant_products_fts, rowid, raw_name, producer, wine_name, region, raw_text)
  values ('delete', old.id, old.raw_name, old.producer, old.wine_name, old.region, old.raw_text);
end;

create trigger if not exists merchant_products_au after update on merchant_products begin
  insert into merchant_products_fts(merchant_products_fts, rowid, raw_name, producer, wine_name, region, raw_text)
  values ('delete', old.id, old.raw_name, old.producer, old.wine_name, old.region, old.raw_text);
  insert into merchant_products_fts(rowid, raw_name, producer, wine_name, region, raw_text)
  values (new.id, new.raw_name, new.producer, new.wine_name, new.region, new.raw_text);
end;

create index if not exists idx_merchants_location on merchants(country, city);
create index if not exists idx_merchants_inventory on merchants(inventory_status, active);
create index if not exists idx_merchant_sources_status on merchant_sources(status, next_crawl_at);
create index if not exists idx_merchant_sources_merchant on merchant_sources(merchant_id);
create index if not exists idx_merchant_products_merchant on merchant_products(merchant_id, active);
create index if not exists idx_merchant_products_vintage on merchant_products(vintage, active);
create index if not exists idx_merchant_products_price on merchant_products(currency, price_value);
create index if not exists idx_merchant_reviews_status on merchant_reviews(status, created_at);
