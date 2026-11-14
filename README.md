# MiniDisputeResolver

AI-powered on-chain dispute resolver on GenLayer Studionet.

## v1 (rejected 13 Nov 2026)

- Contract address: 0x666265743134a2b73a88666b4fc81f5197f98626c8aa
- Explorer: https://explorer-studio.genlayer.com/address/0x666265743134a2b73a88666b4fc81f5197f98626c8aa
- submit_claim -> decide (AI consensus via gl.vm.run_nondet + gl.nondet.exec_prompt) -> get_ruling
- All 3 txs FINALIZED SUCCESS - get_ruling: decided=true, winner=CLAIMANT

## v2 (resubmission — fixes the 13 Nov rejection)

- Contract address: 0xDB3E19B4f25136d4fFd83c56eD0Db063fF4151DB
- Explorer: https://explorer-studio.genlayer.com/address/0xDB3E19B4f25136d4fFd83c56eD0Db063fF4151DB
- File: MiniDisputeResolver_v2.py

What changed:
- Structured JSON ruling: winner, winner_score, loser_score, evidence_quote, reason.
- Independent verification: validator_fn re-runs leader_fn() and only accepts if its winner matches the leader's.
- Evidence binding: winner_score > loser_score, evidence_quote must appear in the winning side's claim/evidence only, reason must name the winner.
- Reusable multi-dispute contract: create_dispute / submit_claim per side with sender address / decide / one-time appeal().

Test evidence (Studionet, 14 Nov 2026, 10 txs FINALIZED SUCCESS):
- Dispute 0 (Rp500,000 logo payment): DECIDED, winner CLAIMANT 85-55, evidence_quote "Email 10 Nov 10.00, lampiran logo-final.zip, balasan klien: terima kasih".
- Appeal dispute 0: CONFIRMED_ON_APPEAL, winner still CLAIMANT 85-55.
- Dispute 1 (Rp750,000 course refund): DECIDED, winner RESPONDENT 80-40, evidence_quote "log akses: dibuka 6 Nov dan 7 Nov".
