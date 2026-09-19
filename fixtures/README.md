# Demo-mode fixtures

`DEMO=true` swaps every data source for the synthetic data in this directory.
Judges run this. The demo video is recorded against this. Real data never
leaves the VM.

Built in week one on purpose — retrofitting demo mode in week five is where
deadlines die.

## Rules

- No real names, email addresses, domains, or application material. Ever.
- Fixtures must be rich enough to make the timeline look alive on camera.
- Every data source the three ported agents touch needs a fixture:
  inbox, calendar, contacts, memory rows, and a canned Tavily result set.

## Files (to build this week)

- `inbox.json`       — synthetic Gmail threads
- `calendar.json`    — synthetic events across the demo day
- `contacts.json`    — synthetic contact graph
- `memory.json`      — seed pgvector rows, some with external claims for
                       Tavily grounding to mark confirmed / stale / contradicted
- `tavily.json`      — recorded search results, so demo mode needs no API key
