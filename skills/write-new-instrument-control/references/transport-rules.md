# Transport Rules to Confirm on Hardware

A parser can be correct and still lose data: the transport decides when a
response is finished. Treat the following as a checklist to confirm on the real
interface for every new Skill, and record each item as verified or unconfirmed.
Do not copy one instrument's timings into another Skill.

## One command per write

- Send exactly one command per write; read its response before the next write.
- A multi-command write can be answered for the first command only, with the rest
  silently dropped. It looks like success.
- Writes answer nothing. Measure the settling time before the next command
  (hundreds of milliseconds is common) instead of assuming zero.
- Enforce this in the command encoder: reject a payload that contains a second
  terminator, rather than documenting the rule in a comment.

## Where a line response ends

- A line response ends at the documented terminator. If the read goes idle with
  no terminator, report an unterminated frame; never add a synthetic terminator
  and never join it to the next reply.
- Error replies are the usual unterminated frame: an undefined header may answer
  bare `command error` with no terminator. A reader that waits for the line
  terminator blocks until its timeout, and the bytes must still be reported.
- An empty read is not an empty value. Retry once for an idempotent query and
  record both attempts; never retry a write.
- A silent write can leave a late reply that the next query reads as its own
  answer. Discard pending bytes with a bounded budget before the next command and
  record how many were dropped.

## Where a block response ends

- For a definite-length block, read until the declared length (plus the
  documented terminator) is present or an overall deadline expires.
- Never end a block read on one idle gap. A live 1 152 054-byte transfer stalled
  after 51 200 bytes; an idle-timeout reader truncated it there and the short
  buffer still looked like a block.
- Never resize a block to the bytes received. A short block is `INCOMPLETE` with
  declared and observed lengths.
- Bytes past the declared length are kept and reported. Trimming to a file
  format is a separate, recorded step.
- Use two budgets: a short idle timeout for line reads and a long total deadline
  for blocks.

## Retry policy

| Operation | Retry | Record |
|---|---|---|
| Idempotent query, empty reply | once | both attempts and their raw bytes |
| Slow or block query | never before the deadline | timeout and elapsed time |
| Write | never | readback and error queue |
| Parser | never; reparse the saved bytes | parser version |

A retried read is a second observation, not a repair. Keep both attempts with
separate hashes; never merge them into one "complete" record.

## Bench checklist

Run once per instrument and interface, with read-only queries where possible:

1. One query per write: confirm one response and that it belongs to that query.
2. Two queries in one write: record what comes back.
3. An undefined header: record whether the error frame carries a terminator.
4. A query whose answer is empty or very late: confirm the retry does not shift
   the next reply.
5. A block larger than any internal buffer, read slowly: confirm the reader ends
   on the declared length, not on a gap.
6. A write followed immediately by a query: find the settling time that makes the
   pair reliable.

Each result is `hardware-verified` only with model, firmware, interface, date, and
the raw exchange. Otherwise label the rule `assumed` and say so.

## Where the code lives

Transport rules belong to the session or transport module, not to the parser. The
parser receives bytes as they arrived and reports framing; a fake transport
replays a dialogue (see [Replay testing](replay-testing.md)). A parser that opens
a socket cannot be tested offline and will hide these failures.
