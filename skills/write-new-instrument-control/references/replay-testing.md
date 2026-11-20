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
- a documented sentinel or unset value, asserting `null` and `INCOMPLETE`
- extra trailing bytes, if the transport can return them

Assert both the extracted value and the integrity status. A test that only checks
that `parse()` returns a number will miss the most dangerous parser failures.

## Fake transport tests

Parser tests replay bytes; transport tests replay a dialogue. Put a seam between
the session and the connection so a scripted fake can deliver one chunk per
`recv`, raise the library's timeout between chunks, return an empty first read,
and end a reply without a terminator. Then assert:

- the encoder sends one command per write and refuses two terminators;
- a line read ends on the terminator and reports an unterminated frame when none
  arrives;
- an empty reply is retried exactly once for a query and never for a write;
- a block read survives idle gaps and returns exactly the declared length;
- a short block is `INCOMPLETE` with declared and observed lengths;
- leftover bytes are discarded before the next command, not answered by it.

The fake needs no network: a list of chunks plus a timeout is enough. Keep these
tests separate from parser tests so the parser never gains a socket.

## Test isolation

Tests must call pure parser functions or a local replay transport. They must not
open a socket, enumerate VISA resources, scan a network, or depend on a physical
instrument. Avoid network URLs in test execution; manual links belong in metadata.

Offline tests are a submission gate, not evidence of hardware behavior: a passing
run does not re-verify a transport rule or a calibration.
