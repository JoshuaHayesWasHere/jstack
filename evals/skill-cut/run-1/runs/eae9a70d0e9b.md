First I find where `Order` is defined: if a schema (OpenAPI, zod, proto) owns that shape, I derive from it rather than hand-roll a validator, per **"Derive types from authoritative schemas."**
I follow **"External data is untyped until parsed."** `as Order` is a cast, not a parse, so `order.items.length` can throw on bad input.
The tool call I'd run first: `Grep pattern="(type|interface|const) Order\b|OrderSchema" glob="**/*.ts"`.
Then I replace the cast with a boundary parse: `const order = OrderSchema.parse(JSON.parse(body));` with `type Order = z.infer<typeof OrderSchema>`.
On parse failure the handler returns 400 instead of crashing downstream. Any ID fields in the schema get branded (`OrderId`) at that same point.
