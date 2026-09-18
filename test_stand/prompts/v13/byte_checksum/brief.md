Helpers over `bytes` buffers. A byte holds an int from 0 to 255.

export function filled(size: int, value: int): bytes
  A buffer of the given size with every byte set to the value.

export function byteSum(data: bytes): int
  The sum of all bytes.

export function checksum(data: bytes): int
  The sum of all bytes modulo 256.

export function countByte(data: bytes, value: int): int
  How many bytes equal the value.

export function isZero(data: bytes): boolean
  True when every byte is 0, including for an empty buffer.
