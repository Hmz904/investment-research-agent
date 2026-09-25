# Frozen ingestion table-period provenance audit v0.1

Status: **development audit note; no human approvals**

The frozen ingestion implementation was inspected without modification. It does not compute an exact `period_start` by subtracting `duration_months` from `period_end`. For a header containing only a duration label and end date, it records `period_resolution_source=header`, the exact end, the duration class, and a null start.

Frozen ingestion does contain derived or inferred table period metadata:

- `header_explicit` records dates parsed as explicitly present in the header;
- `header` records incomplete header evidence such as end plus duration class;
- `xbrl_context` fills a start by resolving against filing contexts;
- `xbrl_fact` reconciles or fills period fields from directly attached XBRL facts.

The ingestion artifacts and implementation remain frozen. Temporal catalog v0.1.2 treats only `header_explicit` as authoritative for standalone `table_cell_exact_period_v0.1` rows. It does not trust populated starts from `header`, `xbrl_context`, or `xbrl_fact` as independently exact table evidence.

Direct authoritative linked XBRL facts may independently establish exact dates under `table_xbrl_agreement_v0.1` when their temporal object is unique, all applicable linked contexts and dimensions agree, and table evidence does not contradict them. Otherwise catalog construction fails closed. End-date-plus-duration evidence is retained only as source/audit metadata and never becomes an exact temporal row or Stage-3 temporal key.

This audit uses only frozen ingestion provenance fields and contains no benchmark target information.
