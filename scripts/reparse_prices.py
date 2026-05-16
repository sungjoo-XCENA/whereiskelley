import sqlite3

from sync_search_api import DB_PATH, init_db, parse_price_v2


def main():
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            select
              e.id,
              e.raw_text,
              e.price_text,
              e.price_value,
              e.currency,
              coalesce(nullif(e.country, ''), c.name, '') as country
            from wine_entries e
            join venues v on v.id = e.venue_id
            join countries c on c.id = v.country_id
            """
        ).fetchall()

        changed = 0
        needs_review = 0
        for row in rows:
            price_text, price_value, currency = parse_price_v2(row["raw_text"], row["country"])
            if price_value is None:
                needs_review += 1
            current = (row["price_text"] or "", row["price_value"], row["currency"] or "")
            updated = (price_text or "", price_value, currency or "")
            if current == updated:
                continue
            con.execute(
                """
                update wine_entries
                set price_text = ?, price_value = ?, currency = ?
                where id = ?
                """,
                (price_text, price_value, currency, row["id"]),
            )
            changed += 1
        con.commit()

    print(f"Repriced {changed} of {len(rows)} entries. Needs review: {needs_review}.")


if __name__ == "__main__":
    main()
