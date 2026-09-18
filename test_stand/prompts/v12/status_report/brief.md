A service status reporter that writes to the console.

export function headline(service: string, healthy: boolean): string
  `<service>: healthy` or `<service>: DEGRADED`.

export function severity(failed: int): string
  `info` for no failures, `warning` for fewer than five, `critical` otherwise.

export function summary(service: string, failed: int): string
  One line in the form `[<severity>] <service> -- <headline>`, where the
  headline is the healthy one exactly when there are no failures.

export function publish(service: string, failed: int): null
  Logs the summary, and additionally writes the degraded headline to the error
  stream when there is at least one failure.

Constraints: `headline` builds its result with a template literal.
