# A measure's stage is separate from its status and its office, and the stages are fixed in code

A measure's legislative stage (Filed, First Reading, In Committee … Posted) is its own field, with its own history. It is not derived from or merged into the document's status or the office holding the paper: a measure In Committee can physically sit at the Secretariat, and status stays an administrative label. The stages are fixed in code, not an editable list, because the order of business suggests agenda items by stage and the deadlines in #10 are tied to specific stages (the Mayor's 10 days, provincial review's 30 days). Renamed or admin-added stages would quietly break both.

## Considered Options

- **Reuse status for stages.** Rejected: status is a free-text lookup used by every document, so legislative meaning would leak into letters and communications, and an admin could rename a value that deadlines depend on.
- **Infer the stage from handoffs** (e.g. at the Mayor's Office means "Sent to the Mayor"). Rejected: where the paper is and where the measure is legislatively diverge too often.

## Consequences

A measure shows two labels, stage and status. Screens show the stage as the main label for measures. Changing the stage list needs a code change and a migration.
