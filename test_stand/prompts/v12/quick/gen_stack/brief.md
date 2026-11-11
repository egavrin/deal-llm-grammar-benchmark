export class IntStack
  Field items: int[] = [].

export function stackPush(stack: IntStack, value: int): null
  Append value to stack.items in place and return null.

export function stackPop(stack: IntStack): int | null
  Remove and return the last item, or null when empty. Preserve the order of
  remaining items. Operations on one stack must not change another stack.
