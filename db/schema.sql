pragma journal_mode = wal;
pragma foreign_keys = on;

create table if not exists countries (
  id integer primary key,
  slug text not null unique,
  name text not null,
  venue_count integer,
  first_seen_at text not null default current_timestamp,
  last_seen_at text not null default current_timestamp
);

create table if not exists venues (
  id integer primary key,
  slug text not null unique,
  name text not null,
  type text,
  country_id integer not null references countries(id),
  city text,
  region_slug text,
  lat real,
  lng real,
  address text,
  google_maps_url text,
  starwine_map_url text,
  venue_url text not null,
  first_seen_at text not null default current_timestamp,
  last_seen_at text not null default current_timestamp
);

create table if not exists wine_lists (
  id integer primary key,
  venue_id integer not null references venues(id) on delete cascade,
  starwine_list_id text not null unique,
  label text,
  download_url text not null,
  file_url text,
  file_view_url text,
  local_file_path text,
  text_file_path text,
  updated_text text,
  updated_date text,
  content_type text,
  checksum text,
  downloaded_at text,
  indexed_at text,
  last_error text,
  entry_count integer not null default 0
);

create table if not exists wine_entries (
  id integer primary key,
  source_item_id text,
  wine_list_id integer not null references wine_lists(id) on delete cascade,
  venue_id integer not null references venues(id) on delete cascade,
  raw_text text not null,
  producer text,
  wine_name text,
  vintage text,
  region text,
  country text,
  grape text,
  price_text text,
  price_value real,
  currency text,
  section text,
  page_number integer
);


create virtual table if not exists wine_entries_fts using fts5(
  raw_text,
  producer,
  wine_name,
  vintage,
  region,
  grape,
  content='wine_entries',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);

create trigger if not exists wine_entries_ai after insert on wine_entries begin
  insert into wine_entries_fts(rowid, raw_text, producer, wine_name, vintage, region, grape)
  values (new.id, new.raw_text, new.producer, new.wine_name, new.vintage, new.region, new.grape);
end;

create trigger if not exists wine_entries_ad after delete on wine_entries begin
  insert into wine_entries_fts(wine_entries_fts, rowid, raw_text, producer, wine_name, vintage, region, grape)
  values('delete', old.id, old.raw_text, old.producer, old.wine_name, old.vintage, old.region, old.grape);
end;

create trigger if not exists wine_entries_au after update on wine_entries begin
  insert into wine_entries_fts(wine_entries_fts, rowid, raw_text, producer, wine_name, vintage, region, grape)
  values('delete', old.id, old.raw_text, old.producer, old.wine_name, old.vintage, old.region, old.grape);
  insert into wine_entries_fts(rowid, raw_text, producer, wine_name, vintage, region, grape)
  values (new.id, new.raw_text, new.producer, new.wine_name, new.vintage, new.region, new.grape);
end;

create table if not exists sync_runs (
  id integer primary key,
  started_at text not null,
  finished_at text,
  countries integer not null default 0,
  venues integer not null default 0,
  downloaded integer not null default 0,
  parsed_entries integer not null default 0,
  errors integer not null default 0,
  notes text
);

create table if not exists michelin_places (
  id integer primary key,
  source_key text not null unique,
  name text not null,
  normalized_name text,
  country text,
  city text,
  address text,
  lat real,
  lng real,
  michelin_url text,
  website_url text,
  cuisine text,
  price_text text,
  first_seen_at text not null default current_timestamp,
  last_seen_at text not null default current_timestamp
);

create table if not exists michelin_awards (
  id integer primary key,
  michelin_place_id integer not null references michelin_places(id) on delete cascade,
  guide_year integer not null,
  distinction text not null default '',
  stars integer,
  green_star integer not null default 0,
  bib_gourmand integer not null default 0,
  selected integer not null default 0,
  source text,
  source_url text,
  collected_at text not null default current_timestamp,
  unique(michelin_place_id, guide_year, distinction)
);

create table if not exists michelin_starwine_matches (
  id integer primary key,
  michelin_place_id integer not null references michelin_places(id) on delete cascade,
  venue_id integer not null references venues(id) on delete cascade,
  match_score real,
  match_method text,
  status text not null default 'candidate',
  matched_at text not null default current_timestamp,
  unique(michelin_place_id, venue_id)
);

create table if not exists michelin_sync_runs (
  id integer primary key,
  started_at text not null default current_timestamp,
  finished_at text,
  source text,
  source_url text,
  guide_year_start integer,
  guide_year_end integer,
  places integer not null default 0,
  awards integer not null default 0,
  matches integer not null default 0,
  errors integer not null default 0,
  notes text
);

create table if not exists guide_sources (
  id integer primary key,
  code text not null unique,
  name text not null,
  base_url text,
  notes text,
  first_seen_at text not null default current_timestamp,
  last_seen_at text not null default current_timestamp
);

create table if not exists guide_places (
  id integer primary key,
  source_id integer not null references guide_sources(id) on delete cascade,
  source_key text not null,
  name text not null,
  normalized_name text,
  country text,
  city text,
  address text,
  lat real,
  lng real,
  place_url text,
  website_url text,
  first_seen_at text not null default current_timestamp,
  last_seen_at text not null default current_timestamp,
  unique(source_id, source_key)
);

create table if not exists guide_rankings (
  id integer primary key,
  guide_place_id integer not null references guide_places(id) on delete cascade,
  source_id integer not null references guide_sources(id) on delete cascade,
  guide_year integer,
  list_name text,
  rank integer,
  score real,
  distinction text not null default '',
  stars integer,
  metadata_json text,
  source_url text,
  collected_at text not null default current_timestamp
);

create table if not exists guide_starwine_matches (
  id integer primary key,
  guide_place_id integer not null references guide_places(id) on delete cascade,
  venue_id integer not null references venues(id) on delete cascade,
  match_score real,
  match_method text,
  status text not null default 'candidate',
  matched_at text not null default current_timestamp,
  unique(guide_place_id, venue_id)
);

create table if not exists wine_keyword_watches (
  id integer primary key,
  keyword text not null,
  normalized_keyword text not null,
  vintage text,
  country_filter text,
  city_filter text,
  active integer not null default 1,
  created_at text not null default current_timestamp,
  last_checked_at text
);

create table if not exists wine_keyword_hits (
  id integer primary key,
  watch_id integer not null references wine_keyword_watches(id) on delete cascade,
  wine_entry_id integer references wine_entries(id) on delete set null,
  venue_id integer references venues(id) on delete set null,
  guide_place_id integer references guide_places(id) on delete set null,
  matched_text text not null,
  vintage text,
  price_text text,
  price_value real,
  currency text,
  source text,
  status text not null default 'new',
  first_seen_at text not null default current_timestamp,
  last_seen_at text not null default current_timestamp
);

create table if not exists notification_events (
  id integer primary key,
  event_type text not null,
  title text not null,
  body text,
  payload_json text,
  status text not null default 'pending',
  created_at text not null default current_timestamp,
  sent_at text,
  error text
);

create index if not exists idx_venues_country_city on venues(country_id, city);
create index if not exists idx_wine_lists_venue on wine_lists(venue_id);
create index if not exists idx_wine_lists_updated on wine_lists(updated_date);
create index if not exists idx_wine_entries_list on wine_entries(wine_list_id);
create index if not exists idx_wine_entries_venue on wine_entries(venue_id);
create index if not exists idx_michelin_places_country_city on michelin_places(country, city);
create index if not exists idx_michelin_awards_year on michelin_awards(guide_year);
create index if not exists idx_michelin_matches_place on michelin_starwine_matches(michelin_place_id);
create index if not exists idx_michelin_matches_venue on michelin_starwine_matches(venue_id);
create index if not exists idx_guide_places_source_city on guide_places(source_id, country, city);
create index if not exists idx_guide_rankings_source_year on guide_rankings(source_id, guide_year);
create unique index if not exists idx_guide_rankings_unique on guide_rankings(
  guide_place_id,
  source_id,
  coalesce(guide_year, 0),
  coalesce(list_name, ''),
  coalesce(rank, 0),
  distinction
);
create index if not exists idx_guide_matches_place on guide_starwine_matches(guide_place_id);
create index if not exists idx_guide_matches_venue on guide_starwine_matches(venue_id);
create unique index if not exists idx_wine_keyword_watches_unique on wine_keyword_watches(
  normalized_keyword,
  coalesce(vintage, ''),
  coalesce(country_filter, ''),
  coalesce(city_filter, '')
);
create index if not exists idx_wine_keyword_hits_watch on wine_keyword_hits(watch_id, status);
create unique index if not exists idx_wine_keyword_hits_unique on wine_keyword_hits(
  watch_id,
  coalesce(wine_entry_id, 0),
  coalesce(venue_id, 0),
  matched_text
);
create index if not exists idx_notification_events_status on notification_events(status, created_at);
