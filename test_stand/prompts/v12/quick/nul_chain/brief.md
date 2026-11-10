export class CityAddress
  Field city: string = "".

export class CityCustomer
  Field address: CityAddress | null = null.

export function customerCity(customer: CityCustomer): string
  Return address.city when address is present, otherwise "unknown".
  Preserve an empty city string.
