A byte-buffer packet module.

export class Packet
  An int `tag` and a `payload` of type `bytes` defaulting to an empty buffer.

export function allocate(size: int): bytes
  A buffer of the requested size.

export function makePacket(tag: int, size: int): Packet
  A packet with the given tag whose payload is a freshly allocated buffer of
  the given size.

export function tagOf(packet: Packet): int
