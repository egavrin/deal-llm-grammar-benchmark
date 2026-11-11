export class SensorDescription
  Fields value: int | null = null and text: string | null = null.

export function describeSensor(reading: int): SensorDescription
  Return {value: null, text: "sensor error"} for -1; otherwise
  {value: reading, text: null}. This uses a record instead of an int|string union.
