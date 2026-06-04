<!-- Syntax Corporation © 2026 — EBS Contract Renewal PAF -->
# EBS interface contract — PDOI (Import Price Catalogs)

Target: **`PO_HEADERS_INTERFACE` + `PO_LINES_INTERFACE`**, consumed by the
**Import Price Catalogs** concurrent program (Purchasing Documents Open
Interface). Column names + types verified live against EBS_Vision_12214.

## Header — `PO_HEADERS_INTERFACE`
| Column | Type | Value the agent writes |
|--------|------|------------------------|
| `INTERFACE_HEADER_ID` | NUMBER | unique per renewal (sequence in prod) |
| `BATCH_ID` | **NUMBER** | numeric batch id (`YYYYMMDDHHMMSS`) |
| `ORG_ID` | NUMBER | operating unit (204) |
| `ACTION` | VARCHAR2 | `UPDATE` (renew existing agreement) |
| `DOCUMENT_TYPE_CODE` / `DOCUMENT_SUBTYPE` | VARCHAR2 | `BLANKET` / `BLANKET` |
| `PO_HEADER_ID` | NUMBER | **the existing agreement** being renewed |
| `VENDOR_ID`, `VENDOR_SITE_ID` | NUMBER | supplier + purchasing site |
| `VENDOR_DOC_NUM` | VARCHAR2 | supplier quote number |
| `CURRENCY_CODE` | VARCHAR2 | agreement currency |
| `AGENT_ID` | NUMBER | buyer |
| `APPROVAL_STATUS` | VARCHAR2 | `INCOMPLETE` (buyer approves in EBS) |
| `EFFECTIVE_DATE`, `EXPIRATION_DATE` | DATE | new term (bound as DATE objects) |
| `AMOUNT_AGREED`, `AMOUNT_LIMIT` | NUMBER | Σ(line price × qty) |
| `TERMS_ID` | NUMBER | payment terms |
| `PROCESS_CODE` | VARCHAR2 | `PENDING` (import picks up) |
| `ATTRIBUTE1`, `ATTRIBUTE2` | VARCHAR2 | agent run id, confidence |

> There is **no** `BLANKET_TOTAL_AMOUNT` on this interface; `DOCUMENT_NUM` is an
> obsoleted stub (`DOCUMENT_NUM#1`) — renew by `PO_HEADER_ID`, not by number.

## Line — `PO_LINES_INTERFACE`
| Column | Type | Value |
|--------|------|-------|
| `INTERFACE_LINE_ID` | NUMBER | unique per line |
| `INTERFACE_HEADER_ID` | NUMBER | FK to the header |
| `ACTION` | VARCHAR2 | `UPDATE` |
| `LINE_NUM`, `SHIPMENT_NUM` | NUMBER | agreement line / shipment |
| `LINE_TYPE_ID` / `LINE_TYPE` | NUMBER / VARCHAR2 | `1` / `Goods` |
| `ITEM`, `ITEM_ID`, `ITEM_DESCRIPTION` | — | item from the agreement |
| `CATEGORY_ID`, `CATEGORY` | — | purchasing category |
| `UNIT_OF_MEASURE` / `UOM_CODE` | VARCHAR2 | `Each` / **`Ea`** |
| `UNIT_PRICE`, `QUANTITY` | NUMBER | **new** price, estimated annual qty |
| `EFFECTIVE_DATE`, `EXPIRATION_DATE` | DATE | line term |

> `PO_LINES_INTERFACE` has **no ATTRIBUTE columns** — per-line match status /
> exceptions are recorded in `agent_trace.json` + the QA report, not the
> interface. Held lines never reach the interface (the whole batch is held).

## Balancing rule
`AMOUNT_AGREED` (header) = Σ over lines of `UNIT_PRICE × QUANTITY`. Tax is derived
at **release/invoice**, not at the agreement, so there is **no TAX line**.

## Errors
The import reports failures in `PO_INTERFACE_ERRORS` (38 cols) keyed by
`INTERFACE_HEADER_ID` / `INTERFACE_LINE_ID`.

## Idempotency
Before staging, the agent checks for a successor BLANKET agreement for the vendor
with `start_date >=` the proposed effective date; if found, the run is blocked
(`RENEWAL_ALREADY_EXISTS`).
