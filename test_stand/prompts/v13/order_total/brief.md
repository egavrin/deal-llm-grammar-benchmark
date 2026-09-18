An order-pricing module for a small shop.

export class LineItem
  A `sku` string, a `unitPrice` int and a `quantity` int.

export function subtotal(item: LineItem): int
  The price of one line: unit price times quantity.

export function orderTotal(items: LineItem[]): int
  The sum of every line's subtotal; zero for an empty order.

export function sampleOrder(): LineItem[]
  A two-line example order built from object literals.
