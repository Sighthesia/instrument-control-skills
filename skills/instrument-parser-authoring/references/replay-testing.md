# Replay Testing

Replay tests make a parser useful without a physical instrument and keep hardware
access out of CI.

## Fixture layout

```text
tests/fixtures/
|-- valid-response.bin
|-- expected-result.json
|-- truncated-response.bin
|-- malformed-header.bin
`-- length-mismatch.bin
```

Use binary files for binary protocols. Store a request or command description next
to the response when it is needed to interpret the fixture. Keep a short README or
JSON provenance record for source, manual revision, and redactions.

## Minimum cases

- one valid response with exact expected metadata and payload
- truncated body
- malformed marker or header
- declared-length mismatch
- unsupported version or data kind
- unknown unit or missing calibration evidence, if relevant
- extra trailing bytes, if the transport can return them

Assert both the extracted value and the integrity status. A test that only checks
that `parse()` returns a number will miss the most dangerous parser failures.

## Test isolation

Tests must call pure parser functions or a local replay transport. They must not
open a socket, enumerate VISA resources, scan a network, or depend on a physical
instrument. Avoid network URLs in test execution; manual links belong in metadata.
