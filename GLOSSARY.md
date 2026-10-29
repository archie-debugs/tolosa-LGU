# SB Tolosa

Tracks the documents of the Sangguniang Bayan (SB) of Tolosa, the municipal legislative council, as they move between offices and through the legislative process.

## Documents and their movement

**Document**:
Any paper record registered in the system and identified by a tracking number and QR code.
_Avoid_: File, record, item

**Tracking number**:
The identifier a document gets when it is registered, counted separately for each document type: `ORD-000001` for ordinances, `RES-000001` for resolutions, `LTR-000001` for letter requests. A document whose type changes gets the next number in its new series, and its old number still finds it. Not the enacted number: `ORD-000012` is not Ordinance No. 12.
_Avoid_: Reference number, control number

**Document type**:
What a document is: Ordinance, Resolution or Letter Request, and nothing else.

**Office**:
A unit of the LGU that can hold a document, such as the SB Secretariat or the Mayor's Office.
_Avoid_: Department, unit

**Handoff**:
The transfer of a document's paper copy from one office to another, which the receiving office confirms by scanning it.
_Avoid_: Transfer, routing, forwarding

**Status**:
A document's administrative state, such as For information, Approved, Completed or Posted. It is separate from a measure's stage and from the office holding the document.
_Avoid_: Stage, state

**Referred to**:
The person or position a document is referred to, such as the SB Secretary or a council member. Stored as the document's `assigned_to`.
_Avoid_: Assigned to, assignee

**Action required**:
What the SB has to do with a document: None, For Agenda, Approval or Posting.
_Avoid_: Action (a recorded office action is a different thing)

## Legislation

**Measure**:
A proposed ordinance or resolution. Only measures have a stage.
_Avoid_: Bill, legislation, item

**Ordinance**:
A measure that becomes local law once approved by the SB and acted on by the Mayor.

**Resolution**:
A measure expressing the SB's position or decision on a matter, often adopted in a single reading.

**Stage**:
Where a measure is in the legislative process, from Filed through readings, committee, approval and the Mayor's action to provincial review and posting, or ended early as Withdrawn, Tabled or Lost.
_Avoid_: Status, phase, step

**Stage history**:
The dated record of every stage a measure has entered, including who changed it, at which session, and any corrections.

**Enacted number**:
The official number an ordinance or resolution gets when it is approved or adopted, such as Ordinance No. 12, s. 2026.
_Avoid_: Proposed number, document number

**Correction**:
A new entry that fixes an earlier stage change, attendance mark or vote after the session is held, with a reason. The original entry is never removed.
_Avoid_: Edit, amendment, undo

## The council

**Member**:
A person on the SB roster for a term: the Vice Mayor as presiding officer, a regular member, or an ex officio member (Liga/ABC president, SK federation president, IPMR). A member may or may not have a login.
_Avoid_: Councilor, user, SB Member account

**Term**:
The period of one elected SB, such as the 13th Sangguniang Bayan, 2025–2028. Sessions are numbered within a term.

**Committee**:
A standing group of members, led by a chair, to which measures are referred for study.

**Secretariat**:
The SB staff who register documents, run sessions and keep the legislative records.
_Avoid_: Clerk, admin

## Sessions

**Session**:
A meeting of the SB, Regular or Special, identified by its number within the term and its date.
_Avoid_: Meeting, sitting

**Order of business**:
A session's agenda: the measures and other documents to be taken up, in fixed sections from the call to order to adjournment.
_Avoid_: Agenda list, today's documents

**Outcome**:
What the SB did with an item of the order of business, such as referred to committee, passed on second reading or adopted.
_Avoid_: Result, action

**Attendance**:
Whether each member was present, absent, on leave or excused at a session.

**Quorum**:
A majority of all members of the SB, needed for a session to do business.

**Nominal vote**:
A vote where each member's vote is called and recorded by name, as opposed to a voice vote where only the result is recorded.
_Avoid_: Roll call vote

**Minutes**:
The signed written record of a session, approved by the SB at a later session.
