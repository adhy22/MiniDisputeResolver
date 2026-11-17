# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
MiniDisputeResolver v3 — steward fixes (action required, 16 Nov 2026)
======================================================================
Answers the steward request (Joaquin, 16 Nov 2026) on submission
7877a08f... (MiniDisputeResolver v2, Pending review, status
"Tindakan diperlukan"). Response deadline: 30 Nov 2026 — without a
response the submission is auto-rejected. This is NOT a rejection yet.

Steward's four findings — and the fix for each (he was right on all four):

  1. CLAIM COULD BE TAKEN BY ANYONE (first-come)
     v2: create_dispute only recorded the creator as claimant;
     submit_claim overwrote dispute.claimant/respondent with whoever
     called first, so any caller could take either slot.
     v3: create_dispute(description, respondent_address) records BOTH
     parties up front. submit_claim now REJECTS any sender who is not
     the recorded party for that side, and never overwrites the
     recorded addresses.

  2. APPEAL COULD BE FILED BY ANYONE
     v2: appeal() never checked the caller — an outsider could appeal.
     v3: appeal() rejects unless sender is the recorded claimant OR
     the recorded respondent.

  3. APPEAL RULING DID NOT ASSESS THE APPEAL REASON OR PRIOR RULING
     v2: the appeal prompt never received appeal_reason or the first
     ruling (winner, scores, reason) — the panel was only told to
     "re-examine", without seeing what was appealed or why.
     v3: the appeal prompt now includes the full previous ruling AND
     the appeal_reason, and instructs the panel to judge whether the
     appeal reason changes the ruling. The previous ruling is also
     snapshotted on-chain (prev_winner / prev_* fields) before any
     overwrite, so get_ruling shows both rulings.

  4. A FAILED APPEAL CONSENSUS PERMANENTLY CONSUMED THE ONE APPEAL
     v2: appeal() set appealed = True BEFORE running consensus. If
     consensus failed (ruling is None), the dispute was stored with
     appealed=True and status still DECIDED — the appeal could never
     be retried, even though no appeal ruling existed.
     v3: appeal() runs consensus FIRST and only sets appealed = True
     (and stores appeal_reason) AFTER a ruling is reached. On failed
     consensus nothing is stored: status stays DECIDED, appealed
     stays False, and the entitled party can appeal again.
     (decide() already had this right in v2 — a failed consensus
     stores no ruling and decide() can be retried.)

  5. FOCUSED TESTS (steward-requested) — run on Studionet after deploy:
     A. Third-party claim: create a dispute with a recorded
        respondent; a third address calls submit_claim for either
        side -> must be rejected, claim NOT stored, status stays OPEN.
     B. Third-party appeal: after decide(), a third address calls
        appeal() -> must be rejected, appealed stays False, status
        stays DECIDED.
     C. Appeal retry after failed consensus: if an appeal call ends
        with status still DECIDED and appealed False (consensus
        failed), the recorded party calls appeal() again -> must
        still be allowed (the allowance was not consumed).
     D. Happy path (re-run of the v2 local tests, now with two
        accounts): dispute 0 (logo Rp500.000) CLAIMANT wins;
        dispute 1 (course refund Rp750.000) RESPONDENT wins;
        appeal on dispute 0 -> CONFIRMED_ON_APPEAL.

  IMPORTANT — v3 needs TWO accounts to test properly:
     In v2 both claims could be submitted from the single deployer
     wallet, because submit_claim overwrote the party addresses.
     In v3 the respondent claim MUST be sent from the recorded
     respondent address, so the deployer wallet alone cannot submit
     both sides. Before testing, have a second address ready (a
     second account in the same wallet / a second connected account
     in Studio) and pass it as respondent_address to
     create_dispute. How to switch the sending account in Studio is
     still to be confirmed in Studio itself — do not assume it works
     the same as v2.

  What v3 keeps from v2 (unchanged):
  - Structured JSON ruling {winner, winner_score, loser_score,
    evidence_quote, reason}; deterministic parse + evidence binding
    (quote must come from the winning side only).
  - Independent re-judgement in validator_fn: the validator runs
    leader_fn() itself and must reach the SAME winner.
  - Reusable multi-dispute contract, per-side submit_claim with
    sender address + evidence, status lifecycle
    OPEN -> READY -> DECIDED -> CONFIRMED_ON_APPEAL / DECIDED_ON_APPEAL.

Deploy / test in GenLayer Studio (Studionet):
  1. Deploy this file (new contract, new address — do NOT reuse v2).
  2. create_dispute("...", "<respondent address>") -> dispute_id
  3. From the CLAIMANT (creator) wallet:
     submit_claim(id, "CLAIMANT", "...claim...", "...evidence...")
  4. From the RESPONDENT wallet (switch account):
     submit_claim(id, "RESPONDENT", "...claim...", "...evidence...")
  5. decide(id) -> get_ruling(id)
  6. From claimant OR respondent wallet only:
     appeal(id, "...why the first ruling was wrong...") -> get_ruling(id)
  7. Run tests A–C above and note the results for the Portal reply.
  8. Update GitHub (code v3 + new address + test results), then in
     the Portal Edit / resubmit submission 7877a08f... with the v3
     repo + explorer links and a note answering each steward point.
"""

from dataclasses import dataclass
import json

from genlayer import *


# ---------------------------------------------------------------------------
# Helpers — deterministic, no LLM. These run the same on every validator.
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return " ".join(str(text).lower().split())


def _parse_ruling(raw) -> dict | None:
    """Parse + deterministically validate a leader/validator JSON ruling.

    Returns the ruling dict, or None if it is not a well-formed ruling.
    This is what makes an opposite label unable to pass: a ruling must
    name exactly one winner, with a higher score, a real evidence quote
    and a real reason — not just contain the word CLAIMANT/RESPONDENT.
    """
    # exec_prompt(response_format="json") may already return a dict,
    # while a plain exec_prompt returns a JSON string — accept both.
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            text = str(raw).strip()
            if text.startswith("```"):
                text = text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
        except Exception:
            return None

    if not isinstance(data, dict):
        return None

    winner = data.get("winner")
    if winner not in ("CLAIMANT", "RESPONDENT"):
        return None

    try:
        winner_score = int(data.get("winner_score"))
        loser_score = int(data.get("loser_score"))
    except Exception:
        return None
    if not (0 <= loser_score < winner_score <= 100):
        return None

    quote = str(data.get("evidence_quote") or "").strip()
    reason = str(data.get("reason") or "").strip()
    if len(quote) < 10 or len(reason) < 20:
        return None
    # The reason must name the side it says won — otherwise it is not
    # bound to the winner at all.
    if winner.lower() not in reason.lower():
        return None

    return {
        "winner": winner,
        "winner_score": winner_score,
        "loser_score": loser_score,
        "evidence_quote": quote,
        "reason": reason,
    }


def _check_evidence_binding(ruling: dict, dispute) -> bool:
    """The evidence quote must come from the WINNING side only.

    This binds the winner to actual evidence. A ruling that says
    CLAIMANT won but quotes only the respondent's text fails here,
    and vice versa. A generic quote that appears in both sides also fails.
    """
    quote = _norm(ruling["evidence_quote"])
    if len(quote) < 10:
        return False

    if ruling["winner"] == "CLAIMANT":
        winning_text = _norm(dispute.claimant_claim + " " + dispute.claimant_evidence)
        losing_text = _norm(dispute.respondent_claim + " " + dispute.respondent_evidence)
    else:
        winning_text = _norm(dispute.respondent_claim + " " + dispute.respondent_evidence)
        losing_text = _norm(dispute.claimant_claim + " " + dispute.claimant_evidence)

    return quote in winning_text and quote not in losing_text


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

@allow_storage
@dataclass
class Dispute:
    description: str
    claimant: str
    respondent: str
    claimant_claim: str
    respondent_claim: str
    claimant_evidence: str
    respondent_evidence: str
    status: str  # OPEN | READY | DECIDED | CONFIRMED_ON_APPEAL | DECIDED_ON_APPEAL
    winner: str
    winner_score: u256
    loser_score: u256
    evidence_quote: str
    ruling_reason: str
    appealed: bool
    appeal_reason: str
    # Snapshot of the first ruling, kept when an appeal succeeds, so the
    # appeal can be shown to have assessed the previous ruling.
    prev_winner: str
    prev_winner_score: u256
    prev_loser_score: u256
    prev_evidence_quote: str
    prev_ruling_reason: str


class MiniDisputeResolver(gl.Contract):
    dispute_counter: u256
    disputes: TreeMap[u256, Dispute]

    def __init__(self):
        self.dispute_counter = u256(0)

    # ------------------------------------------------------------------
    # Create + submit (reusable: one contract, many disputes)
    # FIX 1: both parties are recorded at creation; submit_claim can
    # no longer hand a slot to the first caller.
    # ------------------------------------------------------------------

    @gl.public.write
    def create_dispute(self, description: str, respondent_address: str) -> u256:
        sender = str(gl.message.sender_address)
        respondent = str(respondent_address or "").strip()
        if not respondent:
            print("respondent address must not be empty")
            return self.dispute_counter
        if respondent.lower() == sender.lower():
            print("respondent must be a different address from the claimant")
            return self.dispute_counter
        dispute_id = self.dispute_counter
        self.dispute_counter = self.dispute_counter + u256(1)
        self.disputes[dispute_id] = Dispute(
            description=description,
            claimant=sender,
            respondent=respondent,
            claimant_claim="",
            respondent_claim="",
            claimant_evidence="",
            respondent_evidence="",
            status="OPEN",
            winner="",
            winner_score=u256(0),
            loser_score=u256(0),
            evidence_quote="",
            ruling_reason="",
            appealed=False,
            appeal_reason="",
            prev_winner="",
            prev_winner_score=u256(0),
            prev_loser_score=u256(0),
            prev_evidence_quote="",
            prev_ruling_reason="",
        )
        return dispute_id

    @gl.public.write
    def submit_claim(self, dispute_id: u256, side: str, claim: str, evidence: str) -> None:
        dispute = self.disputes[dispute_id]
        if dispute.status != "OPEN":
            print("dispute is not open for submissions")
            return
        if side not in ("CLAIMANT", "RESPONDENT"):
            print("side must be CLAIMANT or RESPONDENT")
            return
        if len(claim.strip()) < 10 or len(evidence.strip()) < 5:
            print("claim and evidence must not be empty")
            return

        # FIX 1: only the RECORDED party for that side may submit.
        # The recorded addresses are never overwritten here.
        sender = str(gl.message.sender_address)
        if side == "CLAIMANT":
            if sender.lower() != dispute.claimant.lower():
                print("only the recorded claimant may submit the CLAIMANT claim")
                return
            if dispute.claimant_claim:
                print("claimant already submitted")
                return
            dispute.claimant_claim = claim
            dispute.claimant_evidence = evidence
        else:
            if sender.lower() != dispute.respondent.lower():
                print("only the recorded respondent may submit the RESPONDENT claim")
                return
            if dispute.respondent_claim:
                print("respondent already submitted")
                return
            dispute.respondent_claim = claim
            dispute.respondent_evidence = evidence

        if dispute.claimant_claim and dispute.respondent_claim:
            dispute.status = "READY"
        self.disputes[dispute_id] = dispute

    # ------------------------------------------------------------------
    # Judging — the fixed part
    # FIX 3: the appeal prompt now receives the previous ruling and the
    # appeal reason, and must judge whether the appeal reason changes it.
    # ------------------------------------------------------------------

    def _judge_prompt(self, dispute, is_appeal: bool, appeal_reason: str = "") -> str:
        if is_appeal:
            role = (
                "You are an appeal panel re-examining a disputed ruling. "
                "You must assess the appeal reason below against the "
                "previous ruling: decide whether the appeal reason shows "
                "the previous ruling was wrong, or whether the previous "
                "ruling stands. Do not copy the first ruling blindly and "
                "do not ignore the appeal reason."
            )
            previous = (
                "\nPREVIOUS RULING (the ruling being appealed):\n"
                "Winner: " + dispute.winner + "\n"
                "Score: " + str(int(dispute.winner_score)) + " vs "
                + str(int(dispute.loser_score)) + "\n"
                "Evidence quoted: " + dispute.evidence_quote + "\n"
                "Reason given: " + dispute.ruling_reason + "\n"
                "APPEAL REASON (why the appellant says the ruling was wrong):\n"
                + appeal_reason + "\n"
            )
        else:
            role = "You are a fair, impartial judge for a small on-chain dispute."
            previous = ""
        return (
            role + "\n"
            "Dispute: " + dispute.description + "\n"
            "CLAIMANT says: " + dispute.claimant_claim[:1500] + "\n"
            "CLAIMANT evidence: " + dispute.claimant_evidence[:1000] + "\n"
            "RESPONDENT says: " + dispute.respondent_claim[:1500] + "\n"
            "RESPONDENT evidence: " + dispute.respondent_evidence[:1000] + "\n"
            + previous +
            "Decide who should win based on the stronger, more consistent "
            "argument AND the evidence quoted.\n"
            "Return ONLY valid JSON, no markdown, no extra text:\n"
            '{"winner": "CLAIMANT" or "RESPONDENT", '
            '"winner_score": 0-100, "loser_score": 0-100, '
            '"evidence_quote": "an exact short quote (at least 10 characters) '
            'copied from the WINNING side\'s claim or evidence", '
            '"reason": "1-2 sentences naming the winner and the evidence that '
            'made them win"}\n'
            "Rules: winner_score must be greater than loser_score. "
            "evidence_quote must be copied from the winning side only."
        )

    def _run_judgement(self, dispute, is_appeal: bool, appeal_reason: str = "") -> dict | None:
        """One full nondet round: leader proposes, validators independently
        re-judge and must agree on the winner. Returns the agreed ruling,
        or None if consensus / validation fails (dispute stays undecided,
        so decide() can be retried instead of storing a bad ruling)."""

        def leader_fn():
            return gl.nondet.exec_prompt(
                self._judge_prompt(dispute, is_appeal, appeal_reason),
                response_format="json",
            )

        def validator_fn(leader_result) -> bool:
            # Layer 1: leader must be a real Return, not an error.
            if not isinstance(leader_result, gl.vm.Return):
                return False
            # Layer 2: deterministic parse + evidence binding of the leader.
            leader_ruling = _parse_ruling(leader_result.calldata)
            if leader_ruling is None:
                return False
            if not _check_evidence_binding(leader_ruling, dispute):
                return False
            # Layer 3: INDEPENDENT re-judgement. The validator runs the
            # same prompt itself and must reach the SAME winner.
            my_raw = leader_fn()
            my_ruling = _parse_ruling(my_raw)
            if my_ruling is None:
                return False
            if not _check_evidence_binding(my_ruling, dispute):
                return False
            return my_ruling["winner"] == leader_ruling["winner"]

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        # run_nondet_unsafe may return a gl.vm.Return wrapping the
        # leader output, or the leader output itself — handle both.
        raw = result.calldata if isinstance(result, gl.vm.Return) else result
        ruling = _parse_ruling(raw)
        if ruling is None:
            return None
        if not _check_evidence_binding(ruling, dispute):
            return None
        return ruling

    @gl.public.write
    def decide(self, dispute_id: u256) -> None:
        dispute = self.disputes[dispute_id]
        if dispute.status != "READY":
            print("dispute must be READY (both sides submitted) before decide")
            return

        ruling = self._run_judgement(dispute, is_appeal=False)
        if ruling is None:
            # Do NOT store a ruling on failed consensus/validation.
            print("consensus or validation failed, ruling not stored — retry decide")
            return

        dispute.winner = ruling["winner"]
        dispute.winner_score = u256(ruling["winner_score"])
        dispute.loser_score = u256(ruling["loser_score"])
        dispute.evidence_quote = ruling["evidence_quote"]
        dispute.ruling_reason = ruling["reason"]
        dispute.status = "DECIDED"
        self.disputes[dispute_id] = dispute

    @gl.public.write
    def appeal(self, dispute_id: u256, appeal_reason: str) -> None:
        dispute = self.disputes[dispute_id]
        if dispute.status != "DECIDED":
            print("only a DECIDED dispute can be appealed")
            return
        if dispute.appealed:
            print("this dispute has already been appealed once")
            return
        if len(appeal_reason.strip()) < 10:
            print("appeal needs a reason of at least 10 characters")
            return

        # FIX 2: only a RECORDED party may appeal — outsiders rejected.
        sender = str(gl.message.sender_address)
        if sender.lower() != dispute.claimant.lower() and sender.lower() != dispute.respondent.lower():
            print("only the recorded claimant or respondent may appeal")
            return

        # FIX 4: run consensus FIRST. appealed is only set after a
        # ruling is reached, so a failed consensus does not consume
        # the one allowed appeal — the party can appeal again.
        ruling = self._run_judgement(dispute, is_appeal=True, appeal_reason=appeal_reason)
        if ruling is None:
            print("appeal consensus failed, original ruling stands — appeal not used, you may retry")
            return

        # Consensus succeeded: snapshot the previous ruling, then store
        # the appeal ruling and mark the appeal as used.
        dispute.prev_winner = dispute.winner
        dispute.prev_winner_score = dispute.winner_score
        dispute.prev_loser_score = dispute.loser_score
        dispute.prev_evidence_quote = dispute.evidence_quote
        dispute.prev_ruling_reason = dispute.ruling_reason
        dispute.appealed = True
        dispute.appeal_reason = appeal_reason

        if ruling["winner"] != dispute.winner:
            dispute.winner = ruling["winner"]
            dispute.winner_score = u256(ruling["winner_score"])
            dispute.loser_score = u256(ruling["loser_score"])
            dispute.evidence_quote = ruling["evidence_quote"]
            dispute.ruling_reason = ruling["reason"]
            dispute.status = "DECIDED_ON_APPEAL"
        else:
            dispute.status = "CONFIRMED_ON_APPEAL"
        self.disputes[dispute_id] = dispute

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    @gl.public.view
    def get_dispute(self, dispute_id: u256) -> dict:
        d = self.disputes[dispute_id]
        return {
            "id": int(dispute_id),
            "description": d.description,
            "claimant": d.claimant,
            "respondent": d.respondent,
            "status": d.status,
            "winner": d.winner,
            "appealed": d.appealed,
        }

    @gl.public.view
    def get_ruling(self, dispute_id: u256) -> dict:
        d = self.disputes[dispute_id]
        return {
            "description": d.description,
            "decided": d.status in ("DECIDED", "CONFIRMED_ON_APPEAL", "DECIDED_ON_APPEAL"),
            "status": d.status,
            "winner": d.winner,
            "winner_score": int(d.winner_score),
            "loser_score": int(d.loser_score),
            "evidence_quote": d.evidence_quote,
            "ruling_reason": d.ruling_reason,
            "appealed": d.appealed,
            "appeal_reason": d.appeal_reason,
            "previous_winner": d.prev_winner,
            "previous_winner_score": int(d.prev_winner_score),
            "previous_loser_score": int(d.prev_loser_score),
            "previous_evidence_quote": d.prev_evidence_quote,
            "previous_ruling_reason": d.prev_ruling_reason,
        }
