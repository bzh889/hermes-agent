# Prototype exact-group semantic history retrieval

Type: prototype
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: 02

## Question

How should Restricted Group follow-up context retrieve semantically relevant original Teams messages from only the exact bound conversation, with no time limit and no Hermes memory, Mem0, PKB, private session history, or cross-group content? Prototype retrieval over real-shaped long-history fixtures using the existing Teams MTK exact-conversation fetch primitive, then decide identity binding, pagination, attachment treatment, redaction, relevance thresholds, prompt-cache-safe injection, and forced marker tests that prove zero cross-conversation leakage.

## Comments
