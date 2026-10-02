# Next work for Shorefront

The current product is Shorefront. Keep it separate from KRATIA. Follow
[the migration guide](RENAMING_AND_UPGRADING.md) for existing state and consumers.
Do not infer a completed deployment from source changes or older release notes.

## Commercial release gates still open

1. Resolve the previously identified authorization/demo-reset, atomicity and replay
   concerns. Reproduce and verify them in isolated local fixtures; do not test
   third-party systems or build offensive automation.
2. Define the buyer and first paid workflow with real user evidence. Tenant
   isolation, roles, audit exports, retention and onboarding need explicit product
   requirements and end-to-end acceptance checks.
3. Validate actual feed contracts, data licensing, freshness/error behavior and
   recovery procedures before connecting live operations.
4. Approve Shorefront's distinct colour system and the first representative
   interface. Copper Quay belongs to KRATIA. The current source change is an
   identity migration, not the high-end UI redesign.
5. Verify complete desktop/mobile, keyboard, loading/error/stale and permission
   states; then measure performance and operator task completion.
6. Exercise production-shaped PostgreSQL migrations, backup/restore and rollback
   in an isolated environment before a separately authorized live release.

The vessel runtime remains a separate system. Shorefront accepts privacy-minimized
normalized events and produces advisory coordination. Do not introduce physical
actuation, crew-private records, or a second competing semantic contract here.
