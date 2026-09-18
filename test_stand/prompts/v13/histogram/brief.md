Bucketing non-negative ints.

export function bucketCounts(values: int[], size: int): int[]
  Bucket i holds the values from i*size up to but excluding (i+1)*size. The
  result has exactly as many buckets as the largest value needs, every count
  filled in; empty for an empty array or a size of 0 or less.

export function largestBucket(values: int[], size: int): int
  The index of the bucket with the most values, the lowest index on a tie;
  -1 when there are no buckets.

export function mode(values: int[]): int
  The value that occurs most often, the smallest such value on a tie; 0 for
  an empty array.
