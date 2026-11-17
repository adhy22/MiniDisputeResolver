MiniDisputeResolver
AI-powered on-chain dispute resolver on GenLayer Studionet.
v1 (rejected 13 Nov 2026)
Contract address: 0x666265743134a2b73a88666b4fc81f5197f98626c8aa
Explorer: https://explorer-studio.genlayer.com/address/0x666265743134a2b73a88666b4fc81f5197f98626c8aa
submit_claim -> decide (AI consensus via gl.vm.run_nondet + gl.nondet.exec_prompt) -> get_ruling
All 3 txs FINALIZED SUCCESS - get_ruling: decided=true, winner=CLAIMANT
v2 (resubmission — fixes the 13 Nov rejection)
Contract address: 0xDB3E19B4f25136d4fFd83c56eD0Db063fF4151DB
Explorer: https://explorer-studio.genlayer.com/address/0xDB3E19B4f25136d4fFd83c56eD0Db063fF4151DB
File: MiniDisputeResolver_v2.py
What changed:
Structured JSON ruling: winner, winner_score, loser_score, evidence_quote, reason.
Independent verification: validator_fn re-runs leader_fn() and only accepts if its winner matches the leader's.
Evidence binding: winner_score > loser_score, evidence_quote must appear in the winning side's claim/evidence only, reason must name the winner.
Reusable multi-dispute contract: create_dispute / submit_claim per side with sender address / decide / one-time appeal().
Test evidence (Studionet, 14 Nov 2026, 10 txs FINALIZED SUCCESS):
Dispute 0 (Rp500,000 logo payment): DECIDED, winner CLAIMANT 85-55, evidence_quote "Email 10 Nov 10.00, lampiran logo-final.zip, balasan klien: terima kasih".
Appeal dispute 0: CONFIRMED_ON_APPEAL, winner still CLAIMANT 85-55.
Dispute 1 (Rp750,000 course refund): DECIDED, winner RESPONDENT 80-40, evidence_quote "log akses: dibuka 6 Nov dan 7 Nov".
v3 (steward action-required response, 16 Nov 2026 — fixes the v2 review)
Contract address: 0xB95a74D1eAAEB0F7C2EA0f9F82D0d92B60f888C7
Explorer: https://explorer-studio.genlayer.com/address/0xB95a74D1eAAEB0F7C2EA0f9F82D0d92B60f888C7
File: MiniDisputeResolver_v3.py
What changed (answers each steward point from Joaquin, 16 Nov 2026):
Parties recorded up front: `create\_dispute(description, respondent\_address)` records claimant (creator) and respondent at creation and rejects an empty respondent or respondent == claimant. `submit\_claim` accepts a claim only from the recorded party for that side — first caller can no longer take a slot. Verified: a third-party CLAIMANT claim on dispute 2 (from 0x365e836701ef8d4d03a2AD34c14D62366e818175, neither party) was rejected — the real claimant claim afterwards still succeeded and the dispute reached READY.
Appeal restricted to recorded parties: `appeal()` rejects anyone who is not the recorded claimant or respondent. Verified: a third-party appeal on dispute 2 (from 0x365e836701ef8d4d03a2AD34c14D62366e818175) was rejected — `appealed` stayed false, status stayed DECIDED.
Appeal ruling assesses the appeal reason and the previous ruling: the appeal prompt includes the full previous ruling (winner, scores, evidence quote, reason) plus the appeal reason, and the panel must judge whether the appeal reason changes the ruling. The previous ruling is also stored on-chain (`prev\_winner`, `prev\_winner\_score`, `prev\_loser\_score`, `prev\_evidence\_quote`, `prev\_ruling\_reason`) and shown by `get\_ruling`. Verified on dispute 2: after appeal, `previous\_winner` RESPONDENT 75-60 with the previous evidence quote and reason preserved, and the appeal ruling reason engages the appeal argument.
Failed consensus does not consume the appeal: `appealed=True` is set only after a successful appeal consensus; on failed consensus nothing is stored, status stays DECIDED and `appealed` stays false, so the appeal can be retried. Verified on dispute 2: the first two authorized appeal attempts failed consensus (appealed stayed false, status DECIDED) and the third attempt succeeded — CONFIRMED_ON_APPEAL. (The same no-store-on-failure behaviour applies to `decide()`: two early decide() calls on dispute 1 stored nothing while the dispute was not READY.)
Test evidence (Studionet, 17 Nov 2026, all txs FINALIZED):
Dispute 1 (Rp750,000 course refund; claimant 0x7ac016A7765c62B1B8AE7b43d8e824a8b9B52049, respondent 0xB090fD854e5ed2E669590738201131e3F6572503): DECIDED, winner RESPONDENT 70-45, evidence_quote "log akses: dibuka 6 Nov dan 7 Nov".
Dispute 2 (Rp300,000 article writing; claimant 0x7ac016A7765c62B1B8AE7b43d8e824a8b9B52049, respondent 0xB090fD854e5ed2E669590738201131e3F6572503): DECIDED, winner RESPONDENT 75-60, evidence_quote "Revisi 1 dan revisi 2, artikel final 1000 kata". Appeal (claimant, reason: word count alone does not prove the revision matched the brief): CONFIRMED_ON_APPEAL, winner still RESPONDENT 75-60, previous ruling preserved.
Note: writes from a connected MetaMask account failed in Studio with a generic "Error writing to contract" (correct network and balance); all v3 tests above used Studio-managed accounts, switching accounts inside Studio.
