# Cinema ticket counter

Staff-only module (`/cinema/`) for selling tickets at the box office.

## How a sale works
1. **Dashboard** - today's shows, **Sell Tickets**.
2. **Seat map** - Gold (back) and Silver, aisles as in the real hall, screen at the bottom.
   Seats show one of five states (as in the Khalti app): available, selected, **reserved**
   (another counter is billing them), **sold**, **unavailable** (taken out of sale).
   The map refreshes itself every few seconds when other counters sell or reserve seats.
3. **Billing** - opening this page reserves the seats for you for 7 minutes (countdown shown);
   choose payment method and amount received; the change is shown.
4. **Print** - **one invoice per seat**, each with its own S.No., tax breakdown and QR code.
   A reprint is stamped `COPY OF ORIGINAL (n)`.
5. **Entry gate** (`Verify Entry`) - scan the QR (or type the 12-character code under it).
   Each ticket works once, only on its show date, and never if the invoice was cancelled.
6. **Bookings** - search, reprint, cancel (releases the seat, only before entry/show end).
7. **Daily Report** - collection by payment method, section, movie and cashier, with VAT and local tax totals.

## Prices and taxes (`cinema/pricing.py`)
| | |
|---|---|
| Gold / Silver | Rs 400 / Rs 300 (set per show in Admin, these are the defaults) |
| Local tax | 3% of the base fee |
| VAT | 13% of (base fee + local tax) |

Prices are the full amount paid (taxes inside): Rs 300 -> 257.76 + 34.51 + 7.73.

Optional `settings.py` overrides:

```python
CINEMA_VAT_PERCENT        = 13
CINEMA_LOCAL_TAX_PERCENT  = 3
CINEMA_PRICES_INCLUDE_TAX = True      # False = taxes added on top
CINEMA_HS_CODE            = "00"      # printed on the invoice
CINEMA_DEVICE_NAME        = "BOX OFFICE 1"
CINEMA_HOLD_MINUTES       = 7         # how long seats stay Reserved at billing
```

## Setting up a hall
Either let the module build a simple hall (Admin > Cinema halls: *Total seats* +
*Gold rows*), or give the exact seat map:

```
python manage.py load_layout "Audi 1" cinema/layouts/audi1.txt
```

Layout format (back row first, screen below the last row):

```
GA gold   ooooo..........ooooo     # o = seat, . = empty space
gap                                 # walkway row
A  silver oooooooo...ooooooooo
```

Seats are made when a **show is created**, so add shows after the hall is set up.
Shows that already exist keep the seats they had.

## Taking seats out of sale
Admin > Cinema > Seats: tick seats, choose **Mark selected seats UNAVAILABLE** (broken seat,
owner's seat ...) or **AVAILABLE** again. Sold seats are never changed by this action.

## Migrations
`0008` depends on every earlier cinema migration in the folder, so an extra auto-generated
merge migration can never cause "Conflicting migrations". Just run `python manage.py migrate`.

## Printer
The slip is 72 mm wide (80 mm roll). For a 58 mm roll set 48 mm in `ticket_print.html`
(`@page` and `--paper`). Needs `segno` (`pip install -r requirements.txt`).

## Tests
`python manage.py test cinema`
